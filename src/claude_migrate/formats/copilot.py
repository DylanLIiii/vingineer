from pathlib import Path
import json
import yaml
from claude_migrate.models import ClaudeConfig
from claude_migrate.utils import (
    ensure_dir,
    global_stats,
    clean_description,
    sanitize_filename,
    backup_file,
    is_plugin_entity,
)


class CopilotConverter:
    def __init__(self, config: ClaudeConfig):
        self.config = config

    def save(self, target_dir: Path, merge: bool = False):
        github_dir = target_dir / ".github"
        ensure_dir(github_dir)

        self._save_prompts(github_dir / "prompts", merge=merge)
        self._save_agents(github_dir / "agents", merge=merge)
        self._save_mcp(target_dir, merge=merge)

    def _save_prompts(self, prompts_dir: Path, merge: bool = False):
        ensure_dir(prompts_dir)
        for cmd in self.config.commands:
            safe_name = sanitize_filename(cmd.name)
            file_path = prompts_dir / f"{safe_name}.prompt.md"

            if merge and file_path.exists() and not is_plugin_entity(cmd.name):
                global_stats.record("Prompts", "skipped")
                continue

            backup_file(file_path)

            fm = {
                "name": cmd.name,
                "description": clean_description(
                    cmd.description or f"Converted from {cmd.name}"
                ),
            }
            if cmd.model:
                fm["model"] = cmd.model
            if cmd.agent:
                fm["agent"] = cmd.agent

            # Copilot format uses ${input:arguments} instead of $ARGUMENTS
            converted_body = cmd.body.replace("$ARGUMENTS", "${input:arguments}")

            fm_str = yaml.dump(fm, sort_keys=False).strip()
            content = f"---\n{fm_str}\n---\n\n{converted_body}\n"

            file_path.write_text(content, encoding="utf-8")
            global_stats.record("Prompts", "converted")

    def _save_agents(self, agents_dir: Path, merge: bool = False):
        ensure_dir(agents_dir)
        for agent in self.config.agents:
            safe_name = sanitize_filename(agent.name)
            file_path = agents_dir / f"{safe_name}.agent.md"

            if merge and file_path.exists() and not is_plugin_entity(agent.name):
                global_stats.record("Agents", "skipped")
                continue

            backup_file(file_path)

            fm = {
                "name": agent.name,
                "description": clean_description(agent.description or ""),
            }
            if agent.model:
                fm["model"] = agent.model

            # Add VS Code Copilot defaults for full spec compliance
            fm["infer"] = True
            fm["target"] = "vscode"

            # Tools
            if agent.tools:
                tools = []
                if isinstance(agent.tools, list):
                    tools = agent.tools
                elif isinstance(agent.tools, str):
                    tools = [t.strip() for t in agent.tools.split(",") if t.strip()]
                elif isinstance(agent.tools, dict):
                    tools = list(agent.tools.keys())

                if tools:
                    fm["tools"] = tools

            fm_str = yaml.dump(fm, sort_keys=False).strip()
            content = f"---\n{fm_str}\n---\n\n{agent.prompt}\n"

            file_path.write_text(content, encoding="utf-8")
            global_stats.record("Agents", "converted")

    def _save_mcp(self, target_dir: Path, merge: bool = False):
        if not self.config.mcp_servers:
            return

        file_path = target_dir / "mcp.json"

        existing_servers = {}
        if merge and file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    existing_servers = existing_data.get("mcpServers", {})
            except (json.JSONDecodeError, IOError):
                pass

        mcp_data = {**existing_servers}
        for name, mcp in self.config.mcp_servers.items():
            transformed = mcp.model_dump(
                exclude={"disabled", "environment"}, exclude_none=True
            )

            if mcp.environment and not mcp.env:
                transformed["env"] = mcp.environment

            if mcp.type == "local":
                transformed["type"] = "stdio"
            elif mcp.type == "remote":
                transformed["type"] = "sse"

            mcp_data[name] = transformed

        if mcp_data:
            backup_file(file_path)
            config = {"mcpServers": mcp_data}
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            global_stats.record("MCP", "converted", len(mcp_data))
