import pytest
from typer.testing import CliRunner

from claude_migrate.cli import app

runner = CliRunner()


@pytest.fixture
def sample_claude_home(tmp_path):
    # Setup mock Claude home directory
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()

    (claude_dir / "agents").mkdir()
    (claude_dir / "commands").mkdir()
    (claude_dir / "skills").mkdir()

    # Create sample agent
    (claude_dir / "agents" / "test-agent.md").write_text(
        "---\nname: test-agent\ndescription: Test Agent\n---\nAgent prompt",
        encoding="utf-8",
    )

    # Create sample command
    (claude_dir / "commands" / "test-cmd.md").write_text(
        "---\nname: test-cmd\ndescription: Test Command\n---\nCommand body",
        encoding="utf-8",
    )

    return claude_dir


def test_cli_convert_opencode(tmp_path, sample_claude_home):
    import uuid

    # Use unique output directory
    unique_id = str(uuid.uuid4())[:8]
    custom_output = tmp_path / f"opencode_test_{unique_id}"

    # Run CLI
    result = runner.invoke(
        app,
        [
            "convert",
            "opencode",
            "--source",
            str(sample_claude_home),
            "--output",
            str(custom_output),
        ],
    )

    assert result.exit_code == 0
    assert "Converting to OPENCODE format" in result.stdout
    assert "Conversion complete!" in result.stdout

    # Check output was created
    assert custom_output.exists()
    assert (custom_output / "agent").exists()
    assert (custom_output / "command").exists()


def test_cli_convert_copilot(tmp_path, sample_claude_home):
    import uuid

    # Use unique output directory
    unique_id = str(uuid.uuid4())[:8]
    custom_output = tmp_path / f"copilot_test_{unique_id}"

    result = runner.invoke(
        app,
        [
            "convert",
            "copilot",
            "--source",
            str(sample_claude_home),
            "--output",
            str(custom_output),
        ],
    )

    assert result.exit_code == 0
    assert "Converting to COPILOT format" in result.stdout
    assert "Conversion complete!" in result.stdout

    assert custom_output.exists()
    assert (custom_output / ".github" / "agents").exists()
    assert (custom_output / ".github" / "prompts").exists()


def test_cli_convert_with_output_flag(tmp_path, sample_claude_home):
    import uuid

    # Use unique output directory
    unique_id = str(uuid.uuid4())[:8]
    custom_output = tmp_path / f"output_test_{unique_id}"

    result = runner.invoke(
        app,
        [
            "convert",
            "opencode",
            "--source",
            str(sample_claude_home),
            "--output",
            str(custom_output),
        ],
    )

    assert result.exit_code == 0
    assert custom_output.exists()
    assert (custom_output / "agent").exists()


def test_cli_convert_dry_run(tmp_path, sample_claude_home):
    import uuid

    # Use unique output directory
    unique_id = str(uuid.uuid4())[:8]
    custom_output = tmp_path / f"dryrun_test_{unique_id}"

    result = runner.invoke(
        app,
        [
            "convert",
            "opencode",
            "--source",
            str(sample_claude_home),
            "--output",
            str(custom_output),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "DRY RUN - No files will be written" in result.stdout

    # Verify no files were created
    assert not custom_output.exists()


def test_cli_verbose(tmp_path, sample_claude_home):
    import uuid

    # Use unique output directory
    unique_id = str(uuid.uuid4())[:8]
    custom_output = tmp_path / f"verbose_test_{unique_id}"

    result = runner.invoke(
        app,
        [
            "convert",
            "opencode",
            "--source",
            str(sample_claude_home),
            "--output",
            str(custom_output),
            "--verbose",
        ],
    )

    assert result.exit_code == 0
    assert "Found 1 agent(s)" in result.stdout
    assert "Found 1 command(s)" in result.stdout
