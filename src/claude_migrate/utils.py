import os
import json
import re
import shutil
import textwrap
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Literal


class Statistics:
    """Track conversion statistics."""

    def __init__(self) -> None:
        self.stats: Dict[str, Dict[str, int]] = {
            "Plugins": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Commands": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Prompts": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Agents": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Skills": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "MCP": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Backups": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
        }

    def record(self, category: str, type_: str, count: int = 1) -> None:
        """Record a statistic event."""
        if category not in self.stats:
            self.stats[category] = {
                "detected": 0,
                "converted": 0,
                "skipped": 0,
                "failed": 0,
            }
        # Ensure all required keys exist
        if type_ not in self.stats[category]:
            self.stats[category][type_] = 0
        self.stats[category][type_] += count

    def print_summary(self) -> None:
        """Print a summary table of statistics."""
        print("\n" + "=" * 65)
        print(
            f"{'CATEGORY':<15} | {'DETECTED':<10} | {'SUCCESS':<10} | {'SKIPPED':<10} | {'FAILED':<10}"
        )
        print("-" * 65)
        for cat, data in self.stats.items():
            print(
                f"{cat:<15} | {data['detected']:<10} | {data['converted']:<10} | {data['skipped']:<10} | {data['failed']:<10}"
            )
        print("=" * 65 + "\n")


# Global statistics instance
global_stats = Statistics()

# Ensure Backups category exists (for backward compatibility during development)
if "Backups" not in global_stats.stats:
    global_stats.stats["Backups"] = {
        "detected": 0,
        "converted": 0,
        "skipped": 0,
        "failed": 0,
    }


ClaudeScope = Literal["project", "user"]


def get_claude_setup_instructions() -> str:
    return textwrap.dedent(
        """
        No Claude Code configuration found.

        Expected one of:
          - Project config: ./.claude/
          - User config:    ~/.claude/

        To create a config, install and run Claude Code at least once.
        """
    ).strip()


def detect_claude_config(
    cwd: Optional[Path] = None, home: Optional[Path] = None
) -> tuple[Path, ClaudeScope]:
    """Detect Claude config directory and scope.

    Rules:
    - If a `.claude/` directory exists in the current working directory, use it
      and scope is `project`.
    - Otherwise, fall back to `~/.claude` and scope is `user`.

    Raises FileNotFoundError if neither exists.
    """

    if cwd is None:
        cwd = Path.cwd()
    if home is None:
        home = Path.home()

    project_dir = cwd / ".claude"
    if project_dir.exists():
        return project_dir, "project"

    user_dir = home / ".claude"
    if user_dir.exists():
        return user_dir, "user"

    raise FileNotFoundError(get_claude_setup_instructions())


def get_claude_config_for_scope(
    scope: ClaudeScope,
    cwd: Optional[Path] = None,
    home: Optional[Path] = None,
) -> Path:
    """Get Claude config directory for a specific scope.

    Unlike detect_claude_config(), this does not fall back to another scope
    if the requested one doesn't exist - it raises an error instead.

    Args:
        scope: Either "project" or "user"
        cwd: Current working directory (defaults to Path.cwd())
        home: Home directory (defaults to Path.home())

    Returns:
        Path to the Claude config directory

    Raises:
        FileNotFoundError: If the config directory for the requested scope doesn't exist
    """
    if cwd is None:
        cwd = Path.cwd()
    if home is None:
        home = Path.home()

    if scope == "project":
        config_dir = cwd / ".claude"
        if not config_dir.exists():
            raise FileNotFoundError(
                f"Project scope requested but {config_dir} directory not found.\n"
                "Create it first or use --scope user to use your user-level config."
            )
        return config_dir

    # scope == "user"
    config_dir = home / ".claude"
    if not config_dir.exists():
        raise FileNotFoundError(
            f"User scope requested but {config_dir} directory not found.\n"
            "Run Claude Code at least once to create your user config."
        )
    return config_dir


def get_default_output_dir(
    target: Literal["opencode", "copilot"], scope: ClaudeScope
) -> Path:
    if target == "opencode":
        if scope == "project":
            return Path.cwd() / ".opencode"
        return Path.home() / ".config" / "opencode"

    # copilot
    if scope == "project":
        return Path.cwd()

    # user-level Copilot export: keep it out of the profile by default
    return Path.cwd() / "copilot_export"


def ensure_dir(directory: Path) -> None:
    """Ensure a directory exists, creating it if necessary."""
    if not directory.exists():
        os.makedirs(directory)


def expand_vars(value: Any, extra_vars: Dict[str, str] = {}) -> Any:
    """
    Expand shell-style variables like ${VAR} and ${VAR:-default} in strings.
    Recursively handles lists and dictionaries.
    """
    if isinstance(value, str):
        for k, v in extra_vars.items():
            value = value.replace(f"${{{k}}}", v)
        pattern = r"\$\{([^}:]+)(?::-([^}]*))?\}"

        def replace(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            val = extra_vars.get(var_name) or os.environ.get(var_name)
            if val is not None:
                return str(val)
            if default is not None:
                return default
            return ""

        return re.sub(pattern, replace, value)
    if isinstance(value, list):
        return [expand_vars(item, extra_vars) for item in value]
    if isinstance(value, dict):
        return {k: expand_vars(v, extra_vars) for k, v in value.items()}
    return value


def strip_jsonc_comments(text: str) -> str:
    """
    Remove // and /* */ comments from JSONC text while preserving
    comment-like sequences inside strings.
    """
    in_str = False
    in_line_comment = False
    in_block_comment = False
    escaped = False
    result_chars = []
    i = 0
    length = len(text)

    while i < length:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < length else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                result_chars.append(ch)
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_str:
            result_chars.append(ch)
            if ch == "\\" and not escaped:
                escaped = True
            elif ch == '"' and not escaped:
                in_str = False
            else:
                escaped = False
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_str = True
            result_chars.append(ch)
            i += 1
            continue

        result_chars.append(ch)
        i += 1

    return "".join(result_chars)


def load_jsonc(file_path: Path) -> Dict[str, Any]:
    """Read a JSON/JSONC file safely, stripping comments."""
    if not file_path.exists():
        return {}
    raw_text = file_path.read_text(encoding="utf-8")
    cleaned = strip_jsonc_comments(raw_text)
    return json.loads(cleaned) if cleaned.strip() else {}


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse YAML frontmatter from a string.
    Returns a tuple of (frontmatter_dict, body_content).
    Handles invalid YAML with fallback regex parsing.
    """
    stripped = content.lstrip()
    if stripped.startswith("---"):
        try:
            parts = stripped.split("---", 2)
            if len(parts) >= 3:
                # Try standard YAML parsing
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    return frontmatter, parts[2]
                except yaml.YAMLError:
                    # Fallback: Regex extraction for common fields
                    frontmatter = {}

                    # Extract name
                    name_match = re.search(r"name:\s*(.+?)(?:\n|$)", parts[1])
                    if name_match:
                        frontmatter["name"] = name_match.group(1).strip()

                    # Extract description
                    # Try heuristic: description is everything after "description:"
                    # until the next known field or end of block
                    lines = parts[1].split("\n")
                    for i, line in enumerate(lines):
                        if line.strip().startswith("description:"):
                            desc_val = line.split(":", 1)[1].strip()
                            desc_lines = [desc_val] if desc_val else []

                            for j in range(i + 1, len(lines)):
                                next_line = lines[j].strip()
                                # Stop at known keys or start of new key
                                if next_line and (
                                    next_line.startswith(
                                        (
                                            "mode:",
                                            "model:",
                                            "temperature:",
                                            "tools:",
                                            "agent:",
                                        )
                                    )
                                    or (re.match(r"^[a-zA-Z0-9_-]+:", next_line))
                                ):
                                    break
                                desc_lines.append(lines[j])

                            if desc_lines:
                                frontmatter["description"] = "\n".join(
                                    desc_lines
                                ).strip()
                            break

                    # Extract tools
                    tools_match = re.search(r"tools:\s*\[(.*?)\]", parts[1], re.DOTALL)
                    if tools_match:
                        tools_str = tools_match.group(1)
                        frontmatter["tools"] = [
                            t.strip().strip("'\"")
                            for t in tools_str.split(",")
                            if t.strip()
                        ]
                    else:
                        # Try line-based tools extraction if not list format
                        tools_line_match = re.search(
                            r"tools:\s*(.+?)(?:\n|$)", parts[1]
                        )
                        if tools_line_match and not tools_line_match.group(
                            1
                        ).strip().startswith("["):
                            tools_str = tools_line_match.group(1)
                            frontmatter["tools"] = [
                                t.strip() for t in tools_str.split(",") if t.strip()
                            ]

                    return frontmatter, parts[2]
        except Exception:
            pass
    return {}, content


def sanitize_filename(name: str) -> str:
    """Sanitize string to be safe for filenames."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def clean_description(desc: str) -> str:
    """Ensure description is a single line and clean of quotes."""
    if not desc:
        return ""
    # Replace newlines with spaces
    cleaned = desc.replace("\n", " ").strip()
    # Strip surrounding quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1]
    return cleaned


def get_backup_dir() -> Path:
    """Get centralized backup directory."""
    backup_dir = Path.home() / ".claude-migrate" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def backup_file(file_path: Path) -> Optional[Path]:
    """Backup a file before overwriting.

    Returns backup path or None if file doesn't exist.
    Backups stored centrally at ~/.claude-migrate/backups/<relative_path>/
    """
    if not file_path.exists():
        return None

    backup_dir = get_backup_dir()

    # Create relative path structure for organization
    if file_path.is_relative_to(Path.cwd()):
        rel_path = file_path.relative_to(Path.cwd())
    else:
        # Use user_ prefix for files not in CWD
        rel_path = Path(f"user_{file_path.name}")

    backup_subdir = backup_dir / rel_path.parent
    backup_subdir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_name = f"{file_path.stem}.backup_{timestamp}{file_path.suffix}"
    backup_path = backup_subdir / backup_name

    try:
        shutil.copy2(file_path, backup_path)
        global_stats.record("Backups", "created")
        cleanup_old_backups(backup_subdir, file_path.stem, keep=5)
        return backup_path
    except Exception as e:
        print(f"Warning: Failed to backup {file_path}: {e}")
        return None


def cleanup_old_backups(backup_dir: Path, file_stem: str, keep: int = 5) -> None:
    """Keep only most recent N backups for a file."""
    backups = list(backup_dir.glob(f"{file_stem}.backup_*"))
    backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for old_backup in backups[keep:]:
        try:
            old_backup.unlink()
        except Exception as e:
            print(f"Warning: Failed to delete old backup {old_backup}: {e}")


def is_plugin_entity(name: str) -> bool:
    """Check if an entity name is from a plugin (contains colon separator).

    Plugin entities are namespaced as "pluginName:entityName" to avoid collisions.
    """
    return ":" in name
