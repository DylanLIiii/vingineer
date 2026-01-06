import pytest
import json
from claude_migrate.utils import (
    expand_vars,
    parse_frontmatter,
    strip_jsonc_comments,
    clean_description,
    sanitize_filename,
    detect_claude_config,
    get_default_output_dir,
    get_claude_setup_instructions,
    backup_file,
    get_backup_dir,
)


def test_expand_vars_string():
    assert expand_vars("Hello ${NAME}", {"NAME": "World"}) == "Hello World"
    assert expand_vars("No var here") == "No var here"
    assert expand_vars("${MISSING}") == ""
    assert expand_vars("${MISSING:-default}") == "default"


def test_expand_vars_list():
    input_list = ["${VAR1}", "static", "${VAR2:-def}"]
    vars = {"VAR1": "val1"}
    assert expand_vars(input_list, vars) == ["val1", "static", "def"]


def test_expand_vars_dict():
    input_dict = {"key1": "${VAR1}", "key2": "static"}
    vars = {"VAR1": "val1"}
    assert expand_vars(input_dict, vars) == {"key1": "val1", "key2": "static"}


def test_strip_jsonc_comments():
    text = """
    {
        // This is a line comment
        "key": "value", 
        /* This is a block
           comment */
        "url": "http://example.com"
    }
    """
    cleaned = strip_jsonc_comments(text)
    data = json.loads(cleaned)
    assert data["key"] == "value"
    assert data["url"] == "http://example.com"


def test_parse_frontmatter_valid():
    content = """---
name: Test
description: A test description
---
Body content here
"""
    fm, body = parse_frontmatter(content)
    assert fm["name"] == "Test"
    assert fm["description"] == "A test description"
    assert body.strip() == "Body content here"


def test_parse_frontmatter_invalid_yaml():
    # Unquoted colon in description typically breaks YAML parsing
    content = """---
name: Test
description: This: breaks yaml
---
Body
"""
    fm, body = parse_frontmatter(content)
    assert fm["name"] == "Test"
    # The regex fallback should catch this
    assert "description" in fm
    assert fm["description"] == "This: breaks yaml"
    assert body.strip() == "Body"


def test_sanitize_filename():
    assert sanitize_filename("normal_file.txt") == "normal_file.txt"
    assert sanitize_filename("bad/file:name?.txt") == "bad_file_name_.txt"


def test_clean_description():
    assert clean_description(' "Quoted" ') == "Quoted"
    assert clean_description("Multi\nLine") == "Multi Line"


def test_detect_claude_config_prefers_project(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".claude").mkdir()

    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()

    base, scope = detect_claude_config(cwd=project, home=home)
    assert base == project / ".claude"
    assert scope == "project"


def test_detect_claude_config_falls_back_to_user(tmp_path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()

    base, scope = detect_claude_config(cwd=cwd, home=home)
    assert base == home / ".claude"
    assert scope == "user"


def test_detect_claude_config_raises_helpful_error(tmp_path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(FileNotFoundError) as exc:
        detect_claude_config(cwd=cwd, home=home)

    assert get_claude_setup_instructions() in str(exc.value)


def test_get_default_output_dir_opencode_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert get_default_output_dir("opencode", "project") == tmp_path / ".opencode"


def test_get_default_output_dir_copilot_user(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert get_default_output_dir("copilot", "user") == tmp_path / "copilot_export"


@pytest.fixture
def backup_test_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("original content")
    return test_file


def test_backup_file(backup_test_file, tmp_path):
    """Test that backup is created correctly."""

    backup_path = backup_file(backup_test_file)

    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.name.startswith("test.backup_")
    assert backup_path.read_text() == "original content"
    assert get_backup_dir().exists()


def test_backup_nonexistent_file(tmp_path):
    """Test that backup returns None for nonexistent file."""

    nonexistent = tmp_path / "nonexistent.txt"
    backup_path = backup_file(nonexistent)

    assert backup_path is None


def test_backup_cleanup(backup_test_file, tmp_path):
    """Test that old backups are cleaned up (keep 5)."""
    from claude_migrate.utils import get_backup_dir

    # Clean up any existing backups from previous tests
    backup_dir = get_backup_dir()
    for old_backup in backup_dir.glob("test.backup_*"):
        old_backup.unlink()

    # Create 7 backups
    backups = []
    for i in range(7):
        backup_test_file.write_text(f"content {i}")
        backup_path = backup_file(backup_test_file)
        backups.append(backup_path)

    # Only last 5 should remain
    backup_dir = backups[0].parent
    remaining_backups = list(backup_dir.glob("test.backup_*"))

    assert len(remaining_backups) == 5
    # Oldest 2 should be deleted
    assert backups[0] not in remaining_backups
    assert backups[1] not in remaining_backups
