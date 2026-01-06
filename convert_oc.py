import os
import json
import re
import yaml
import sys
import argparse
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional

# --- 默认路径配置 ---
USER_HOME = Path.home()
CLAUDE_BASE_DIR = USER_HOME / ".claude"
PLUGINS_DB_PATH = CLAUDE_BASE_DIR / "plugins" / "installed_plugins.json"
PROJECT_DIR = Path.cwd() / ".claude"
PROJECT_ROOT = Path.cwd()

# OpenCode 默认配置路径
OPENCODE_GLOBAL_DIR = USER_HOME / ".config" / "opencode"
OPENCODE_PROJECT_DIR = Path.cwd() / ".opencode"
DEFAULT_EXPORT_DIR = Path.cwd() / "opencode_export"
EXPORT_FORMAT_CHOICES = ["dir", "json"]


# --- 统计类 ---
class Statistics:
    def __init__(self):
        self.stats = {
            "Plugins": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Commands": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
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

# --- 辅助函数 ---


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
    stripped = content.lstrip()
    if stripped.startswith("---"):
        try:
            parts = stripped.split("---", 2)
            if len(parts) >= 3:
                # Try to parse YAML, if it fails due to complex description,
                # try to extract just the YAML structure we need
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                    return frontmatter, parts[2]
                except yaml.YAMLError:
                    # If YAML fails, try a simpler approach:
                    # Just extract the fields we need manually
                    import re

                    frontmatter = {}
                    # Extract name
                    name_match = re.search(r"name:\s*(.+?)(?:\n|$)", parts[1])
                    if name_match:
                        frontmatter["name"] = name_match.group(1).strip()
                    # Extract description (everything until next field or end)
                    desc_match = re.search(
                        r"description:\s*(.+?)(?:\n(?:mode|model|temperature)|$)",
                        parts[1],
                        re.DOTALL,
                    )
                    if desc_match:
                        frontmatter["description"] = desc_match.group(1).strip()
                    else:
                        # Try getting description from name line onwards
                        lines = parts[1].split("\n")
                        for i, line in enumerate(lines):
                            if line.strip().startswith("name:"):
                                # Description is everything after name until next field
                                desc_lines = []
                                for j in range(i + 1, len(lines)):
                                    next_line = lines[j].strip()
                                    if next_line and not next_line.startswith(
                                        ("mode:", "model:", "temperature:")
                                    ):
                                        desc_lines.append(lines[j])
                                    else:
                                        break
                                if desc_lines:
                                    frontmatter["description"] = "\n".join(
                                        desc_lines
                                    ).strip()
                                break
                    return frontmatter, parts[2]
        except Exception:
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
    raw_text = file_path.read_text(encoding="utf-8")
    cleaned = strip_jsonc_comments(raw_text)
    return json.loads(cleaned) if cleaned.strip() else {}


def extract_leading_comments(raw_text: str) -> str:
    """Capture leading // or /* */ comment block to preserve on write."""
    pattern = r"^(?:\s*(?://[^\n]*|/\*.*?\*/)+\s*\n?)+"
    match = re.match(pattern, raw_text, re.DOTALL)
    return match.group(0) if match else ""


# --- 转换逻辑 (Recursive) ---


def convert_commands(
    base_dir: Path, scope: str, namespace_prefix: str = ""
) -> Dict[str, Any]:
    commands_dir = base_dir / "commands"
    result = {}
    if not commands_dir.exists():
        return result

    files = list(commands_dir.rglob("*.md"))  # Recursive
    global_stats.record("Commands", "detected", len(files))

    for file_path in files:
        if file_path.name.startswith("."):
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            data, body = parse_frontmatter(content)
            base_name = file_path.stem
            full_name = (
                f"{namespace_prefix}:{base_name}" if namespace_prefix else base_name
            )

            if not body.strip():
                global_stats.record("Commands", "failed")
                continue

            # OpenCode Template Format
            wrapped_template = (
                f"<command-instruction>\n{body.strip()}\n</command-instruction>\n\n"
                f"<user-request>\n$ARGUMENTS\n</user-request>"
            )

            desc_prefix = (
                f"(plugin: {namespace_prefix})" if namespace_prefix else f"({scope})"
            )
            rel_path = file_path.relative_to(commands_dir).parent
            if str(rel_path) != ".":
                desc_prefix += f" [{rel_path}]"

            definition = {
                "name": full_name,
                "description": f"{desc_prefix} {data.get('description', '')}",
                "template": wrapped_template,
                "agent": data.get("agent"),
                "model": data.get("model"),
                "subtask": data.get("subtask"),
                "argumentHint": data.get("argument-hint"),
            }
            result[full_name] = {k: v for k, v in definition.items() if v is not None}
            global_stats.record("Commands", "converted")
        except Exception:
            global_stats.record("Commands", "failed")
    return result


def convert_agents(
    base_dir: Path, scope: str, namespace_prefix: str = ""
) -> Dict[str, Any]:
    agents_dir = base_dir / "agents"
    result = {}
    if not agents_dir.exists():
        return result

    files = list(agents_dir.rglob("*.md"))  # Recursive
    global_stats.record("Agents", "detected", len(files))

    for file_path in files:
        if file_path.name.startswith("."):
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
            data, body = parse_frontmatter(content)
            base_name = data.get("name", file_path.stem)
            full_name = (
                f"{namespace_prefix}:{base_name}" if namespace_prefix else base_name
            )

            desc_prefix = (
                f"(plugin: {namespace_prefix})" if namespace_prefix else f"({scope})"
            )
            rel_path = file_path.relative_to(agents_dir).parent
            if str(rel_path) != ".":
                desc_prefix += f" [{rel_path}]"

            tools_config = None
            if data.get("tools"):
                t_list = [
                    t.strip().lower()
                    for t in data.get("tools", "").split(",")
                    if t.strip()
                ]
                if t_list:
                    tools_config = {t: True for t in t_list}

            # Store original description for dir export
            config = {
                "description": f"{desc_prefix} {data.get('description', '')}",
                "mode": "subagent",
                "prompt": body.strip(),
                "_original_description": data.get("description", ""),
            }
            if tools_config:
                config["tools"] = tools_config

            result[full_name] = config
            global_stats.record("Agents", "converted")
        except Exception:
            global_stats.record("Agents", "failed")
    return result


def convert_skills_to_commands(
    base_dir: Path, scope: str, namespace_prefix: str = ""
) -> Dict[str, Any]:
    skills_dir = base_dir / "skills"
    result = {}
    if not skills_dir.exists():
        return result

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
            content = skill_md_path.read_text(encoding="utf-8")
            data, body = parse_frontmatter(content)
            base_name = data.get("name", skill_path.name)
            full_name = (
                f"{namespace_prefix}:{base_name}" if namespace_prefix else base_name
            )

            wrapped_template = (
                f"<skill-instruction>\nBase directory for this skill: {skill_path.resolve()}/\n"
                f"File references (@path) in this skill are relative to this directory.\n\n"
                f"{body.strip()}\n</skill-instruction>\n\n"
                f"<user-request>\n$ARGUMENTS\n</user-request>"
            )

            desc = (
                f"(plugin: {namespace_prefix} - Skill)"
                if namespace_prefix
                else f"({scope} - Skill)"
            )
            definition = {
                "name": full_name,
                "description": f"{desc} {data.get('description', '')}",
                "template": wrapped_template,
                "model": data.get("model"),
            }
            result[full_name] = {k: v for k, v in definition.items() if v is not None}
            global_stats.record("Skills", "converted")
        except Exception:
            global_stats.record("Skills", "failed")
    return result


def convert_skills_to_skills(
    base_dir: Path, scope: str, namespace_prefix: str = ""
) -> Dict[str, Any]:
    """Convert Claude skills to OpenCode skill format (for directory export)."""
    skills_dir = base_dir / "skills"
    result = {}
    if not skills_dir.exists():
        return result

    potential_skills = [
        d for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    ]

    for skill_path in potential_skills:
        skill_md_path = skill_path / "SKILL.md"
        if not skill_md_path.exists():
            continue
        try:
            content = skill_md_path.read_text(encoding="utf-8")
            data, body = parse_frontmatter(content)
            base_name = data.get("name", skill_path.name)
            full_name = (
                f"{namespace_prefix}_{base_name}" if namespace_prefix else base_name
            )

            desc_prefix = (
                f"(plugin: {namespace_prefix})" if namespace_prefix else f"({scope})"
            )

            result[full_name] = {
                "name": full_name,
                "description": f"{desc_prefix} {data.get('description', '')}",
                "license": data.get("license"),
                "body": body.strip(),
                "content": body.strip(),
            }
        except Exception:
            global_stats.record("Skills", "failed")
    return result


def convert_mcp(
    config_path: Path, scope: str, namespace_prefix: str = "", plugin_root: str = ""
) -> Dict[str, Any]:
    result = {}
    if not config_path.exists():
        return result

    try:
        raw_config = load_jsonc(config_path)
        extra_vars = {"CLAUDE_PLUGIN_ROOT": str(plugin_root)} if plugin_root else {}
        raw_config = expand_vars(raw_config, extra_vars)

        mcp_servers = raw_config.get("mcpServers", {})
        global_stats.record("MCP", "detected", len(mcp_servers))

        for name, cfg in mcp_servers.items():
            if cfg.get("disabled"):
                global_stats.record("MCP", "skipped")
                continue

            full_name = f"{namespace_prefix}:{name}" if namespace_prefix else name
            server_type = cfg.get("type", "stdio")

            transformed = {}
            if server_type in ["http", "sse"]:
                if not cfg.get("url"):
                    continue
                transformed = {"type": "remote", "url": cfg["url"], "enabled": True}
                if cfg.get("headers"):
                    transformed["headers"] = cfg["headers"]
            else:
                if not cfg.get("command"):
                    continue
                args = [cfg["command"]] + cfg.get("args", [])
                transformed = {"type": "local", "command": args, "enabled": True}
                if cfg.get("env"):
                    transformed["environment"] = cfg["env"]

            result[full_name] = transformed
            global_stats.record("MCP", "converted")
    except Exception:
        print(f"  [ERR] MCP Config: {config_path}")
        global_stats.record("MCP", "failed")
    return result


def process_plugins() -> dict:
    out = {"commands": {}, "agents": {}, "mcp": {}, "skills": {}}
    if not PLUGINS_DB_PATH.exists():
        return out

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
            out["commands"].update(convert_commands(path, "plugin", name))
            out["agents"].update(convert_agents(path, "plugin", name))
            out["commands"].update(convert_skills_to_commands(path, "plugin", name))
            out["skills"].update(convert_skills_to_skills(path, "plugin", name))
            out["mcp"].update(
                convert_mcp(path / ".mcp.json", "plugin", name, str(path))
            )
            global_stats.record("Plugins", "converted")
    except Exception as e:
        print(f"Error reading plugin DB: {e}")
    return out


# --- Merge & Save 逻辑 ---


def resolve_config_path(target_dir: Path) -> Path:
    """Prefer existing opencode.jsonc/json; default to opencode.jsonc."""
    jsonc_path = target_dir / "opencode.jsonc"
    json_path = target_dir / "opencode.json"
    if jsonc_path.exists():
        return jsonc_path
    if json_path.exists():
        return json_path
    return jsonc_path


def merge_and_save_config(target_dir: Path, new_sections: Dict[str, Dict[str, Any]]):
    """Merge command/agent/mcp sections into opencode config (JSONC-safe)."""
    file_path = resolve_config_path(target_dir)
    existing_data: Dict[str, Any] = {}
    leading_comments = ""

    if file_path.exists():
        try:
            raw_text = file_path.read_text(encoding="utf-8")
            leading_comments = extract_leading_comments(raw_text)
            existing_data = load_jsonc(file_path)
            print(f"  Merging into existing {file_path.name}...")
        except json.JSONDecodeError:
            print(
                f"  [WARN] Existing {file_path.name} is corrupted or has invalid comments. Overwriting."
            )
            existing_data = {}
    else:
        print(f"  Creating new {file_path.name}...")

    # Merge per-section dictionaries without dropping other keys
    for section, payload in new_sections.items():
        if not payload:
            continue
        if isinstance(existing_data.get(section), dict):
            existing_data[section].update(payload)
        else:
            existing_data[section] = payload

    # Write back with comment preamble + header
    header = "// Auto-generated by convert_oc.py. You can keep comments; they will be preserved on merge.\n"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(header)
            if leading_comments:
                f.write(leading_comments)
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        print(f"  -> Saved to {file_path}")
    except Exception as e:
        print(f"  [ERR] Failed to save {file_path.name}: {e}")


def format_tools_for_frontmatter(tools: Dict[str, bool] = None) -> str:
    """Format tools dict as YAML block for frontmatter."""
    if not tools:
        return ""
    lines = [
        "  " + k + ": " + ("true" if v else "false") for k, v in sorted(tools.items())
    ]
    return "\n" + "\n".join(lines) + "\n"


def save_agents_to_dir(agents: Dict[str, Any], target_dir: Path):
    """Save agents as individual markdown files in agent/ directory."""
    agents_dir = target_dir / "agent"
    ensure_dir(agents_dir)

    for name, config in agents.items():
        safe_name = name.replace("/", "_").replace(":", "_")
        file_path = agents_dir / f"{safe_name}.md"

        frontmatter = {}
        if config.get("mode"):
            frontmatter["mode"] = config["mode"]
        if config.get("model"):
            frontmatter["model"] = config["model"]
        if config.get("temperature") is not None:
            frontmatter["temperature"] = config["temperature"]
        if config.get("maxSteps") is not None:
            frontmatter["maxSteps"] = config["maxSteps"]
        if config.get("disable"):
            frontmatter["disable"] = True
        if config.get("tools"):
            frontmatter["tools"] = config["tools"]
        if config.get("permission"):
            frontmatter["permission"] = config["permission"]
        if config.get("_original_description"):
            frontmatter["description"] = config["_original_description"]

        prompt = config.get("prompt", "")
        frontmatter_str = yaml.dump(
            frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False
        ).strip()
        content = f"---\n{frontmatter_str}\n---\n{prompt}\n"

        try:
            file_path.write_text(content, encoding="utf-8")
            print(f"  -> Saved {file_path.name}")
        except Exception as e:
            print(f"  [ERR] Failed to save {file_path.name}: {e}")


def save_commands_to_dir(commands: Dict[str, Any], target_dir: Path):
    """Save commands as individual markdown files in command/ directory."""
    commands_dir = target_dir / "command"
    ensure_dir(commands_dir)

    for name, config in commands.items():
        safe_name = name.replace("/", "_").replace(":", "_")
        file_path = commands_dir / f"{safe_name}.md"

        frontmatter = {}
        if config.get("description"):
            frontmatter["description"] = config["description"]
        if config.get("agent"):
            frontmatter["agent"] = config["agent"]
        if config.get("model"):
            frontmatter["model"] = config["model"]
        if config.get("subtask"):
            frontmatter["subtask"] = True
        if config.get("argumentHint"):
            frontmatter["argumentHint"] = config["argumentHint"]

        template = config.get("template", "")
        frontmatter_str = yaml.dump(frontmatter, default_flow_style=False).strip()
        content = f"---\n{frontmatter_str}\n---\n{template}\n"

        try:
            file_path.write_text(content, encoding="utf-8")
            print(f"  -> Saved {file_path.name}")
        except Exception as e:
            print(f"  [ERR] Failed to save {file_path.name}: {e}")


def save_skills_to_dir(skills: Dict[str, Any], target_dir: Path):
    """Save skills as SKILL.md files in skill/<name>/ directories."""
    skills_dir = target_dir / "skill"
    ensure_dir(skills_dir)

    for name, config in skills.items():
        skill_folder = skills_dir / name
        ensure_dir(skill_folder)
        file_path = skill_folder / "SKILL.md"

        frontmatter = {}
        if config.get("name"):
            frontmatter["name"] = config["name"]
        if config.get("description"):
            frontmatter["description"] = config["description"]

        body = config.get("body", config.get("content", ""))
        frontmatter_str = yaml.dump(frontmatter, default_flow_style=False).strip()
        content = f"---\n{frontmatter_str}\n---\n{body}\n"

        try:
            file_path.write_text(content, encoding="utf-8")
            print(f"  -> Saved {name}/SKILL.md")
        except Exception as e:
            print(f"  [ERR] Failed to save {name}/SKILL.md: {e}")


def save_mcp_to_json(mcp: Dict[str, Any], target_dir: Path):
    """Save MCP servers to mcp.json file."""
    if not mcp:
        return
    file_path = target_dir / "mcp.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(mcp, f, indent=2, ensure_ascii=False)
        print(f"  -> Saved {file_path.name}")
    except Exception as e:
        print(f"  [ERR] Failed to save {file_path.name}: {e}")


# --- 主程序 ---


def main():
    parser = argparse.ArgumentParser(
        description="Convert Claude Code configurations to OpenCode format."
    )
    parser.add_argument(
        "--target",
        choices=["export", "global", "project"],
        default="export",
        help="Target location: 'export' (folder), 'global' (~/.config/opencode), or 'project' (./.opencode)",
    )
    parser.add_argument(
        "--format",
        choices=EXPORT_FORMAT_CHOICES,
        default="dir",
        help="Export format: 'dir' (separate files in directories) or 'json' (single JSON config file)",
    )
    args = parser.parse_args()

    # 确定输出目录
    target_dir = DEFAULT_EXPORT_DIR
    if args.target == "global":
        target_dir = OPENCODE_GLOBAL_DIR
    elif args.target == "project":
        target_dir = OPENCODE_PROJECT_DIR

    print(f"Target Directory: {target_dir}")
    print("Scanning and converting...")

    # 1. 收集所有数据 (内存中)
    all_commands = {}
    all_agents = {}
    all_skills = {}
    all_mcp = {}

    # User Level
    all_commands.update(convert_commands(CLAUDE_BASE_DIR, "user"))
    all_agents.update(convert_agents(CLAUDE_BASE_DIR, "user"))
    all_commands.update(convert_skills_to_commands(CLAUDE_BASE_DIR, "user"))
    all_skills.update(convert_skills_to_skills(CLAUDE_BASE_DIR, "user"))
    all_mcp.update(convert_mcp(CLAUDE_BASE_DIR / ".mcp.json", "user"))

    # Plugins
    p_data = process_plugins()
    all_commands.update(p_data["commands"])
    all_agents.update(p_data["agents"])
    all_skills.update(p_data.get("skills", {}))
    all_mcp.update(p_data["mcp"])

    # Project Level
    all_commands.update(convert_commands(PROJECT_DIR, "project"))
    all_agents.update(convert_agents(PROJECT_DIR, "project"))
    all_commands.update(convert_skills_to_commands(PROJECT_DIR, "project"))
    all_skills.update(convert_skills_to_skills(PROJECT_DIR, "project"))
    all_mcp.update(convert_mcp(PROJECT_DIR / ".mcp.json", "local"))
    all_mcp.update(convert_mcp(PROJECT_ROOT / ".mcp.json", "project"))

    # 2. 执行保存/合并
    print("\nProcessing Output...")
    ensure_dir(target_dir)

    if args.format == "dir":
        print(f"Using directory format (separate files)...")
        if all_agents:
            print(f"\n[Agents] Saving {len(all_agents)} agent(s)...")
            save_agents_to_dir(all_agents, target_dir)
        if all_commands:
            print(f"\n[Commands] Saving {len(all_commands)} command(s)...")
            save_commands_to_dir(all_commands, target_dir)
        if all_skills:
            print(f"\n[Skills] Saving {len(all_skills)} skill(s)...")
            save_skills_to_dir(all_skills, target_dir)
        if all_mcp:
            print(f"\n[MCP] Saving {len(all_mcp)} MCP server(s)...")
            save_mcp_to_json(all_mcp, target_dir)
    else:
        print(f"Using JSON format (single config file)...")
        merge_and_save_config(
            target_dir,
            {
                "command": all_commands,
                "agent": all_agents,
                "mcp": all_mcp,
            },
        )

    global_stats.print_summary()


if __name__ == "__main__":
    main()
