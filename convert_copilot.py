import os
import json
import re
import yaml
import sys
import argparse
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

# --- Default Path Configuration ---
USER_HOME = Path.home()
CLAUDE_BASE_DIR = USER_HOME / ".claude"
PLUGINS_DB_PATH = CLAUDE_BASE_DIR / "plugins" / "installed_plugins.json"
PROJECT_DIR = Path.cwd() / ".claude"
PROJECT_ROOT = Path.cwd()

# Copilot Default Export Paths
DEFAULT_EXPORT_DIR = Path.cwd() / "copilot_export"


# --- Statistics Class ---
class Statistics:
    def __init__(self):
        self.stats = {
            "Plugins": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Prompts": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Agents": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Skills": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "MCP": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
        }

    def record(self, category: str, type_: str, count: int = 1):
        self.stats[category][type_] += count

    def print_summary(self):
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


global_stats = Statistics()

# --- Helper Functions ---


def expand_vars(value: Any, extra_vars: Dict[str, str] = {}) -> Any:
    if isinstance(value, str):
        for k, v in extra_vars.items():
            value = value.replace(f"${{{k}}}", v)
        pattern = r"\$\{([^}:]+)(?::-([^}]*))?\}"

        def replace(match):
            var_name = match.group(1)
            default = match.group(2)
            val = extra_vars.get(var_name) or os.environ.get(var_name)
            return val if val is not None else (default if default is not None else "")

        return re.sub(pattern, replace, value)
    if isinstance(value, list):
        return [expand_vars(item, extra_vars) for item in value]
    if isinstance(value, dict):
        return {k: expand_vars(v, extra_vars) for k, v in value.items()}
    return value


def parse_frontmatter(content: str):
    """
    Parse YAML frontmatter from a string.
    Handles leading whitespace and standard --- delimiters.
    Includes fallback for invalid YAML (e.g. unquoted colons in descriptions).
    """
    content = content.lstrip()
    if content.startswith("---"):
        try:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                yaml_text = parts[1]
                body = parts[2].lstrip()

                try:
                    fm_data = yaml.safe_load(yaml_text) or {}
                    return fm_data, body
                except yaml.YAMLError:
                    # Fallback: Simple Regex Extraction for name/description
                    # This handles cases where description has unquoted colons
                    fm_data = {}

                    # Extract name
                    name_match = re.search(r"^name:\s*(.+)$", yaml_text, re.MULTILINE)
                    if name_match:
                        fm_data["name"] = name_match.group(1).strip()

                    # Extract description (simple single line or until next key)
                    # This is a heuristic; it might not capture full multiline descriptions perfectly
                    # but it's better than failing.
                    desc_match = re.search(
                        r"^description:\s*(.+)$", yaml_text, re.MULTILINE
                    )
                    if desc_match:
                        fm_data["description"] = desc_match.group(1).strip()

                    # Extract tools (simple list format)
                    tools_match = re.search(
                        r"^tools:\s*\[(.*?)\]", yaml_text, re.MULTILINE
                    )
                    if tools_match:
                        tools_str = tools_match.group(1)
                        fm_data["tools"] = [
                            t.strip().strip("'\"")
                            for t in tools_str.split(",")
                            if t.strip()
                        ]

                    return fm_data, body

        except Exception as e:
            print(f"Warning: Failed to parse frontmatter: {e}")
            pass
    return {}, content


def ensure_dir(directory: Path):
    if not directory.exists():
        os.makedirs(directory)


def strip_jsonc_comments(text: str) -> str:
    """Remove // and /* */ comments while keeping comment-like sequences inside strings."""
    in_str = False
    in_line_comment = False
    in_block_comment = False
    escaped = False
    result_chars = []
    i = 0
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

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
    """Read a JSON/JSONC file safely."""
    if not file_path.exists():
        return {}
    raw_text = file_path.read_text(encoding="utf-8")
    cleaned = strip_jsonc_comments(raw_text)
    return json.loads(cleaned) if cleaned.strip() else {}


def sanitize_filename(name: str) -> str:
    """Sanitize string to be safe for filenames."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip()


def clean_description(desc: str) -> str:
    """Ensure description is a single line to avoid YAML parsing issues in VS Code."""
    if not desc:
        return ""
    # Replace newlines with spaces and strip quotes if they were captured by regex
    cleaned = desc.replace("\n", " ").strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1]
    return cleaned


# --- Conversion Logic ---


def convert_commands_to_prompts(
    base_dir: Path, target_dir: Path, namespace_prefix: str = ""
):
    """
    Convert Claude 'commands' (*.md) to Copilot Prompt Files (.github/prompts/*.prompt.md).
    """
    commands_dir = base_dir / "commands"
    if not commands_dir.exists():
        return

    prompts_dir = target_dir / ".github" / "prompts"
    ensure_dir(prompts_dir)

    files = list(commands_dir.rglob("*.md"))
    global_stats.record("Prompts", "detected", len(files))

    for file_path in files:
        if file_path.name.startswith("."):
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            data, body = parse_frontmatter(content)

            base_name = file_path.stem
            # Create a unique name if namespaced
            full_name = (
                f"{namespace_prefix}-{base_name}" if namespace_prefix else base_name
            )
            full_name = sanitize_filename(full_name)

            if not body.strip():
                global_stats.record("Prompts", "failed")
                continue

            # Convert variables: $ARGUMENTS -> ${input:arguments}
            # Copilot uses ${input:variableName}
            converted_body = body.replace("$ARGUMENTS", "${input:arguments}")

            # Construct Copilot Frontmatter
            copilot_fm = {
                "name": full_name,
                "description": clean_description(
                    data.get("description", f"Converted from {base_name}")
                ),
            }

            if data.get("model"):
                copilot_fm["model"] = data.get("model")

            # Map 'agent' if present, though Copilot agents are different
            if data.get("agent"):
                copilot_fm["agent"] = data.get("agent")

            # Write to .prompt.md
            target_file = prompts_dir / f"{full_name}.prompt.md"

            with open(target_file, "w", encoding="utf-8") as f:
                f.write("---\n")
                yaml.dump(copilot_fm, f, sort_keys=False)
                f.write("---\n\n")
                f.write(converted_body)

            global_stats.record("Prompts", "converted")
        except Exception as e:
            print(f"Failed to convert command {file_path}: {e}")
            global_stats.record("Prompts", "failed")


def convert_agents_to_custom_agents(
    base_dir: Path, target_dir: Path, namespace_prefix: str = ""
):
    """
    Convert Claude 'agents' (*.md) to Copilot Custom Agents (.github/agents/*.agent.md).
    """
    agents_dir = base_dir / "agents"
    if not agents_dir.exists():
        return

    copilot_agents_dir = target_dir / ".github" / "agents"
    ensure_dir(copilot_agents_dir)

    files = list(agents_dir.rglob("*.md"))
    global_stats.record("Agents", "detected", len(files))

    for file_path in files:
        if file_path.name.startswith("."):
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            data, body = parse_frontmatter(content)

            base_name = data.get("name", file_path.stem)
            full_name = (
                f"{namespace_prefix}-{base_name}" if namespace_prefix else base_name
            )
            full_name = sanitize_filename(full_name)

            # Construct Copilot Frontmatter
            copilot_fm = {
                "name": full_name,
                "description": clean_description(data.get("description", "")),
            }

            # Handle tools
            tools = []
            if data.get("tools"):
                # Claude tools might be comma-separated string or list
                raw_tools = data.get("tools")
                if isinstance(raw_tools, str):
                    tools = [t.strip() for t in raw_tools.split(",") if t.strip()]
                elif isinstance(raw_tools, list):
                    tools = raw_tools

            if tools:
                copilot_fm["tools"] = tools

            if data.get("model"):
                copilot_fm["model"] = data.get("model")

            # Write to .agent.md
            target_file = copilot_agents_dir / f"{full_name}.agent.md"

            with open(target_file, "w", encoding="utf-8") as f:
                f.write("---\n")
                yaml.dump(copilot_fm, f, sort_keys=False)
                f.write("---\n\n")
                f.write(body)  # The system prompt

            global_stats.record("Agents", "converted")
        except Exception as e:
            print(f"Failed to convert agent {file_path}: {e}")
            global_stats.record("Agents", "failed")


def convert_skills(base_dir: Path, target_dir: Path, namespace_prefix: str = ""):
    """
    Convert Claude 'skills' (directories) to Copilot Agent Skills (.github/skills/).
    """
    skills_dir = base_dir / "skills"
    if not skills_dir.exists():
        return

    copilot_skills_dir = target_dir / ".github" / "skills"
    ensure_dir(copilot_skills_dir)

    potential_skills = [
        d for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]
    global_stats.record("Skills", "detected", len(potential_skills))

    for skill_path in potential_skills:
        skill_md_path = skill_path / "SKILL.md"
        if not skill_md_path.exists():
            global_stats.record("Skills", "skipped")
            continue

        try:
            skill_name = skill_path.name
            if namespace_prefix:
                skill_name = f"{namespace_prefix}-{skill_name}"

            target_skill_path = copilot_skills_dir / skill_name

            # Copy the entire directory
            if target_skill_path.exists():
                shutil.rmtree(target_skill_path)
            shutil.copytree(skill_path, target_skill_path)

            # Update SKILL.md frontmatter if needed (ensure 'name' exists)
            target_md = target_skill_path / "SKILL.md"
            content = target_md.read_text(encoding="utf-8")
            data, body = parse_frontmatter(content)

            # Ensure description is clean in SKILL.md too
            if "description" in data:
                data["description"] = clean_description(data["description"])

            if "name" not in data or namespace_prefix:
                data["name"] = skill_name
                # Rewrite file
                with open(target_md, "w", encoding="utf-8") as f:
                    f.write("---\n")
                    yaml.dump(data, f, sort_keys=False)
                    f.write("---\n")
                    f.write(body)

            global_stats.record("Skills", "converted")
        except Exception as e:
            print(f"Failed to convert skill {skill_path}: {e}")
            global_stats.record("Skills", "failed")


def collect_mcp_config(config_path: Path, plugin_root: str = "") -> Dict[str, Any]:
    """
    Read a Claude .mcp.json and return the 'mcpServers' dictionary,
    adapted for VS Code mcp.json format.
    """
    if not config_path.exists():
        return {}

    try:
        raw_config = load_jsonc(config_path)
        extra_vars = {"CLAUDE_PLUGIN_ROOT": str(plugin_root)} if plugin_root else {}
        raw_config = expand_vars(raw_config, extra_vars)

        mcp_servers = raw_config.get("mcpServers", {})
        return mcp_servers
    except Exception:
        return {}


def process_plugins(target_dir: Path) -> Dict[str, Any]:
    """
    Process all installed plugins and convert their components.
    Returns aggregated MCP servers configuration.
    """
    aggregated_mcp = {}

    if not PLUGINS_DB_PATH.exists():
        return aggregated_mcp

    try:
        db = json.loads(PLUGINS_DB_PATH.read_text(encoding="utf-8"))
        plugins = db.get("plugins", {})
        entries = []
        if db.get("version") == 2:
            entries = [(k, v[0]) for k, v in plugins.items() if v]
        else:
            entries = list(plugins.items())

        global_stats.record("Plugins", "detected", len(entries))
        print(f"[Plugins] Processing {len(entries)} plugins...")

        for p_key, info in entries:
            path = Path(info["installPath"])
            name = p_key.split("@")[0]
            if not path.exists():
                global_stats.record("Plugins", "failed")
                continue

            print(f"  > {name}")
            convert_commands_to_prompts(path, target_dir, namespace_prefix=name)
            convert_agents_to_custom_agents(path, target_dir, namespace_prefix=name)
            convert_skills(path, target_dir, namespace_prefix=name)

            # Collect MCP
            plugin_mcp = collect_mcp_config(path / ".mcp.json", str(path))
            # Prefix MCP server names to avoid collisions
            for srv_name, srv_config in plugin_mcp.items():
                full_srv_name = f"{name}-{srv_name}"
                aggregated_mcp[full_srv_name] = srv_config
                global_stats.record("MCP", "detected")

            global_stats.record("Plugins", "converted")
    except Exception as e:
        print(f"Error reading plugin DB: {e}")

    return aggregated_mcp


def save_mcp_config(target_dir: Path, mcp_servers: Dict[str, Any]):
    """
    Save the aggregated MCP configuration to mcp.json in the target root.
    """
    if not mcp_servers:
        return

    mcp_file = target_dir / "mcp.json"

    # VS Code mcp.json structure
    config = {"mcpServers": mcp_servers}

    try:
        with open(mcp_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"Saved MCP configuration to {mcp_file}")
        global_stats.record("MCP", "converted", len(mcp_servers))
    except Exception as e:
        print(f"Failed to save MCP config: {e}")
        global_stats.record("MCP", "failed")


# --- Main Program ---


def main():
    parser = argparse.ArgumentParser(
        description="Convert Claude Code configurations to GitHub Copilot format."
    )
    parser.add_argument(
        "--target",
        default=str(DEFAULT_EXPORT_DIR),
        help="Target directory for export (default: ./copilot_export)",
    )
    args = parser.parse_args()

    target_dir = Path(args.target).resolve()
    print(f"Target Directory: {target_dir}")
    print("Scanning and converting...")

    ensure_dir(target_dir)

    # 1. User Level
    print("Processing User Level configurations...")
    convert_commands_to_prompts(CLAUDE_BASE_DIR, target_dir, namespace_prefix="user")
    convert_agents_to_custom_agents(
        CLAUDE_BASE_DIR, target_dir, namespace_prefix="user"
    )
    convert_skills(CLAUDE_BASE_DIR, target_dir, namespace_prefix="user")
    user_mcp = collect_mcp_config(CLAUDE_BASE_DIR / ".mcp.json")

    # 2. Project Level
    print("Processing Project Level configurations...")
    convert_commands_to_prompts(PROJECT_DIR, target_dir, namespace_prefix="project")
    convert_agents_to_custom_agents(PROJECT_DIR, target_dir, namespace_prefix="project")
    convert_skills(PROJECT_DIR, target_dir, namespace_prefix="project")

    project_mcp_local = collect_mcp_config(PROJECT_DIR / ".mcp.json")
    project_mcp_root = collect_mcp_config(PROJECT_ROOT / ".mcp.json")

    # 3. Plugins
    plugin_mcp = process_plugins(target_dir)

    # 4. Merge and Save MCP
    all_mcp = {}
    all_mcp.update(user_mcp)
    all_mcp.update(plugin_mcp)
    all_mcp.update(project_mcp_local)
    all_mcp.update(project_mcp_root)

    save_mcp_config(target_dir, all_mcp)

    global_stats.print_summary()
    print(f"Conversion complete. Check {target_dir} for results.")
    print("To use these with GitHub Copilot:")
    print(
        f"1. Copy the contents of '{target_dir}/.github' to your workspace's '.github' folder."
    )
    print(
        f"2. Copy '{target_dir}/mcp.json' to your workspace root (or merge with existing)."
    )


if __name__ == "__main__":
    main()
