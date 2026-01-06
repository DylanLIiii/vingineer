from pathlib import Path
from typing import Dict, Any, List

import json

from claude_migrate.models import ClaudeConfig, Agent, Command, Skill, MCPServer
from claude_migrate.utils import (
    parse_frontmatter,
    expand_vars,
    load_jsonc,
    global_stats,
)


class ClaudeLoader:
    def __init__(self, base_dir: Path, include_plugins: bool = False):
        self.base_dir = base_dir
        self.include_plugins = include_plugins

    def load(self) -> ClaudeConfig:
        """Load all configuration from the base directory."""
        config = ClaudeConfig()

        config.agents = self.load_agents()
        config.commands = self.load_commands()
        config.skills = self.load_skills()
        config.mcp_servers = self.load_mcp()

        if self.include_plugins:
            plugin_config = self.load_plugins()
            config.agents.extend(plugin_config.agents)
            config.commands.extend(plugin_config.commands)
            config.skills.extend(plugin_config.skills)
            config.mcp_servers.update(plugin_config.mcp_servers)

        return config

    def load_agents(self) -> List[Agent]:
        agents = []
        agents_dir = self.base_dir / "agents"
        if not agents_dir.exists():
            return agents

        for file_path in agents_dir.rglob("*.md"):
            if file_path.name.startswith("."):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                fm, body = parse_frontmatter(content)

                name = fm.get("name", file_path.stem)
                agents.append(
                    Agent(
                        name=name,
                        description=fm.get("description"),
                        model=fm.get("model"),
                        tools=fm.get("tools"),
                        prompt=body.strip(),
                        temperature=fm.get("temperature"),
                        maxSteps=fm.get("maxSteps"),
                    )
                )
                global_stats.record("Agents", "detected")
            except Exception as e:
                print(f"Failed to load agent {file_path}: {e}")
                global_stats.record("Agents", "failed")

        return agents

    def load_commands(self) -> List[Command]:
        commands = []
        commands_dir = self.base_dir / "commands"
        if not commands_dir.exists():
            return commands

        for file_path in commands_dir.rglob("*.md"):
            if file_path.name.startswith("."):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                fm, body = parse_frontmatter(content)

                if not body.strip():
                    global_stats.record("Commands", "skipped")
                    continue

                name = fm.get("name", file_path.stem)
                commands.append(
                    Command(
                        name=name,
                        description=fm.get("description"),
                        body=body.strip(),
                        model=fm.get("model"),
                        agent=fm.get("agent"),
                        argument_hint=fm.get("argument-hint"),
                        subtask=fm.get("subtask"),
                    )
                )
                global_stats.record("Commands", "detected")
            except Exception as e:
                print(f"Failed to load command {file_path}: {e}")
                global_stats.record("Commands", "failed")

        return commands

    def load_skills(self) -> List[Skill]:
        skills = []
        skills_dir = self.base_dir / "skills"
        if not skills_dir.exists():
            return skills

        potential_skills = [
            d for d in skills_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
        ]

        for skill_path in potential_skills:
            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                content = skill_md.read_text(encoding="utf-8")
                fm, body = parse_frontmatter(content)

                name = fm.get("name", skill_path.name)
                skills.append(
                    Skill(
                        name=name,
                        description=fm.get("description"),
                        body=body.strip(),
                        license=fm.get("license"),
                        path=str(skill_path.resolve()),
                    )
                )
                global_stats.record("Skills", "detected")
            except Exception as e:
                print(f"Failed to load skill {skill_path}: {e}")
                global_stats.record("Skills", "failed")

        return skills

    def load_mcp(self) -> Dict[str, MCPServer]:
        mcp_servers = {}
        mcp_file = self.base_dir / ".mcp.json"

        if not mcp_file.exists():
            return mcp_servers

        try:
            raw_config = load_jsonc(mcp_file)
            raw_config = expand_vars(raw_config, {})

            servers_dict = raw_config.get("mcpServers", {})
            for name, config in servers_dict.items():
                try:
                    mcp_servers[name] = MCPServer(**config)
                    global_stats.record("MCP", "detected")
                except Exception as e:
                    print(f"Invalid MCP server config '{name}': {e}")
                    global_stats.record("MCP", "failed")

        except Exception as e:
            print(f"Failed to load MCP config: {e}")
            global_stats.record("MCP", "failed")

        return mcp_servers

    def load_plugins(self) -> ClaudeConfig:
        """Load installed plugins from ~/.claude/plugins/installed_plugins.json.

        Plugin items are namespaced as `pluginName:<name>` to avoid collisions.
        """

        base = Path.home() / ".claude" / "plugins"
        installed = base / "installed_plugins.json"
        if not installed.exists():
            return ClaudeConfig()

        try:
            raw = json.loads(installed.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to read installed_plugins.json: {e}")
            global_stats.record("Plugins", "failed")
            return ClaudeConfig()

        plugin_entries: list[dict[str, Any]]
        if isinstance(raw, dict) and isinstance(raw.get("plugins"), list):
            plugin_entries = raw["plugins"]
        elif isinstance(raw, list):
            plugin_entries = raw
        else:
            plugin_entries = []

        config = ClaudeConfig()
        for plugin in plugin_entries:
            plugin_name = plugin.get("name") or plugin.get("id") or plugin.get("slug")
            plugin_dir = plugin.get("directory") or plugin.get("path")

            if not plugin_name or not plugin_dir:
                global_stats.record("Plugins", "skipped")
                continue

            plugin_path = Path(plugin_dir)
            if not plugin_path.exists():
                global_stats.record("Plugins", "skipped")
                continue

            global_stats.record("Plugins", "detected")

            plugin_loader = ClaudeLoader(plugin_path, include_plugins=False)
            plugin_config = plugin_loader.load()

            for agent in plugin_config.agents:
                agent.name = f"{plugin_name}:{agent.name}"
                config.agents.append(agent)

            for cmd in plugin_config.commands:
                cmd.name = f"{plugin_name}:{cmd.name}"
                if cmd.agent:
                    cmd.agent = f"{plugin_name}:{cmd.agent}"
                config.commands.append(cmd)

            for skill in plugin_config.skills:
                skill.name = f"{plugin_name}:{skill.name}"
                config.skills.append(skill)

            for name, server in plugin_config.mcp_servers.items():
                config.mcp_servers[f"{plugin_name}:{name}"] = server

            global_stats.record("Plugins", "converted")

        return config
