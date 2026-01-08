from pathlib import Path
from typing import Dict, Any, List
import json
import yaml
from claude_migrate.models import ClaudeConfig, Agent, Command
from claude_migrate.utils import ensure_dir, global_stats, backup_file


class OpenCodeConverter:
    def __init__(self, config: ClaudeConfig):
        self.config = config

    def _should_write_file(
        self, file_path: Path, entity_name: str, merge: bool
    ) -> bool:
        if not merge:
            return True
        if not file_path.exists():
            return True
        return False

    def save(self, target_dir: Path, format: str = "dir", merge: bool = False):
        ensure_dir(target_dir)

        if format == "dir":
            self._save_directory_format(target_dir, merge=merge)
        else:
            self._save_json_format(target_dir, merge=merge)

    def _save_directory_format(self, target_dir: Path, merge: bool = False):
        self._save_agents(target_dir / "agent", merge=merge)
        self._save_commands(target_dir / "command", merge=merge)
        self._save_mcp(target_dir, merge=merge)

    def _save_json_format(self, target_dir: Path, merge: bool = False):
        # Implementation for monolithic JSONC file if needed
        # For now, let's focus on directory format as it's cleaner and preferred
        # But per plan, we keep it simple. If json format is complex, I might skip it for MVP
        # unless strictly required. The plan says "Convert... to OpenCode format (both dir and json)".
        # I'll implement a basic version.

        data = {"agent": {}, "command": {}, "mcp": {}}

        # Convert Agents
        for agent in self.config.agents:
            data["agent"][agent.name] = self._convert_agent_to_dict(agent)

        # Convert Commands
        for cmd in self.config.commands:
            data["command"][cmd.name] = self._convert_command_to_dict(cmd)

        # Convert MCP
        for name, mcp in self.config.mcp_servers.items():
            if not mcp.disabled:
                data["mcp"][name] = mcp.model_dump(exclude_none=True)

        # Note: Skills are typically not in the JSONC config in the same way,
        # or require conversion to commands/agents. For simplicity,
        # let's assume JSON export focuses on core config.

        output_file = target_dir / "opencode.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Saved monolithic config to {output_file}")

    def _save_agents(self, agents_dir: Path, merge: bool = False):
        ensure_dir(agents_dir)
        for agent in self.config.agents:
            safe_name = agent.name.replace("/", "_").replace(":", "_")
            file_path = agents_dir / f"{safe_name}.md"

            if merge and file_path.exists():
                global_stats.record("Agents", "skipped")
                continue

            backup_file(file_path)

            fm = {
                "mode": "subagent",  # Default for converted agents
                "description": agent.description,
            }
            if agent.model:
                fm["model"] = agent.model
            if agent.temperature:
                fm["temperature"] = agent.temperature
            if agent.maxSteps:
                fm["maxSteps"] = agent.maxSteps

            if agent.tools:
                # OpenCode expects tools as specific format or dict
                if isinstance(agent.tools, list):
                    fm["tools"] = {t: True for t in agent.tools}
                elif isinstance(agent.tools, dict):
                    fm["tools"] = agent.tools
                elif isinstance(agent.tools, str):
                    fm["tools"] = {
                        t.strip(): True for t in agent.tools.split(",") if t.strip()
                    }

            fm_str = yaml.dump(fm, sort_keys=False, allow_unicode=True).strip()
            content = f"---\n{fm_str}\n---\n{agent.prompt}\n"

            file_path.write_text(content, encoding="utf-8")
            global_stats.record("Agents", "converted")

    def _save_commands(self, commands_dir: Path, merge: bool = False):
        ensure_dir(commands_dir)
        for cmd in self.config.commands:
            safe_name = cmd.name.replace("/", "_").replace(":", "_")
            file_path = commands_dir / f"{safe_name}.md"

            if merge and file_path.exists():
                global_stats.record("Commands", "skipped")
                continue

            backup_file(file_path)

            fm = {}
            if cmd.description:
                fm["description"] = cmd.description
            if cmd.agent:
                fm["agent"] = cmd.agent
            if cmd.model:
                fm["model"] = cmd.model
            if cmd.subtask:
                fm["subtask"] = True
            if cmd.argument_hint:
                fm["argumentHint"] = cmd.argument_hint

            # OpenCode Template Format
            template = (
                f"<command-instruction>\n{cmd.body}\n</command-instruction>\n\n"
                f"<user-request>\n$ARGUMENTS\n</user-request>"
            )

            fm_str = yaml.dump(fm, sort_keys=False).strip()
            content = f"---\n{fm_str}\n---\n{template}\n"

            file_path.write_text(content, encoding="utf-8")
            global_stats.record("Commands", "converted")

    def _save_mcp(self, target_dir: Path, merge: bool = False):
        if not self.config.mcp_servers:
            return

        mcp_file = target_dir / "opencode.jsonc"

        existing_config = {}
        if merge and mcp_file.exists():
            try:
                with open(mcp_file, "r", encoding="utf-8") as f:
                    existing_config = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        existing_mcp = existing_config.get("mcp", {})
        mcp_data = {**existing_mcp}
        for name, mcp in self.config.mcp_servers.items():
            if mcp.disabled:
                mcp_data.pop(name, None)
                continue

            transformed: Dict[str, Any] = {}

            if mcp.type in ["http", "sse"]:
                transformed["type"] = "remote"
                transformed["url"] = mcp.url
            elif mcp.type == "stdio":
                transformed["type"] = "local"
                cmd_list: List[str] = []
                if mcp.command:
                    if isinstance(mcp.command, str):
                        cmd_list.append(mcp.command)
                    else:
                        cmd_list.extend(mcp.command)
                if mcp.args:
                    cmd_list.extend(mcp.args)
                transformed["command"] = cmd_list
            else:
                transformed["type"] = mcp.type
                if mcp.command:
                    transformed["command"] = mcp.command

            if mcp.env:
                transformed["environment"] = mcp.env

            if mcp.headers:
                transformed["headers"] = mcp.headers

            transformed["enabled"] = True
            mcp_data[name] = transformed

        if mcp_data:
            output_config = {
                "$schema": "https://opencode.ai/config.json",
                "mcp": mcp_data,
            }
            backup_file(mcp_file)
            with open(mcp_file, "w", encoding="utf-8") as f:
                json.dump(output_config, f, indent=2)
            global_stats.record("MCP", "converted", len(mcp_data))

    def _convert_agent_to_dict(self, agent: Agent) -> Dict[str, Any]:
        d = agent.model_dump(
            exclude={"name", "original_description", "prompt"}, exclude_none=True
        )
        d["mode"] = "subagent"
        d["prompt"] = agent.prompt
        # Handle tools conversion for dict format same as file format
        if agent.tools:
            if isinstance(agent.tools, list):
                d["tools"] = {t: True for t in agent.tools}
            elif isinstance(agent.tools, str):
                d["tools"] = {
                    t.strip(): True for t in agent.tools.split(",") if t.strip()
                }
        return d

    def _convert_command_to_dict(self, cmd: Command) -> Dict[str, Any]:
        d = cmd.model_dump(exclude={"name", "body"}, exclude_none=True)
        d["template"] = (
            f"<command-instruction>\n{cmd.body}\n</command-instruction>\n\n"
            f"<user-request>\n$ARGUMENTS\n</user-request>"
        )
        return d
