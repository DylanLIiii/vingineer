from pathlib import Path
import json
import yaml
import shutil
from claude_migrate.models import ClaudeConfig
from claude_migrate.utils import (
    ensure_dir,
    global_stats,
    clean_description,
    sanitize_filename,
    backup_file,
)


class CopilotConverter:
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

    def save(self, target_dir: Path, merge: bool = False):
        github_dir = target_dir / ".github"
        ensure_dir(github_dir)

        self._save_prompts(github_dir / "prompts", merge=merge)
        self._save_agents(github_dir / "agents", merge=merge)
        self._save_skills(github_dir / "skills", merge=merge)
        self._save_mcp(target_dir, merge=merge)

    def _save_prompts(self, prompts_dir: Path, merge: bool = False):
        ensure_dir(prompts_dir)
        for cmd in self.config.commands:
            safe_name = sanitize_filename(cmd.name)
            file_path = prompts_dir / f"{safe_name}.prompt.md"

            if merge and file_path.exists():
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

            if merge and file_path.exists():
                global_stats.record("Agents", "skipped")
                continue

            backup_file(file_path)

            fm = {
                "name": agent.name,
                "description": clean_description(agent.description or ""),
            }
            if agent.model:
                fm["model"] = agent.model

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

    def _save_skills(self, skills_dir: Path, merge: bool = False):
        ensure_dir(skills_dir)
        for skill in self.config.skills:
            safe_name = sanitize_filename(skill.name)
            target_skill_path = skills_dir / safe_name

            if merge and target_skill_path.exists():
                global_stats.record("Skills", "skipped")
                continue

            if skill.path and Path(skill.path).exists():
                # Backup existing SKILL.md if it exists
                target_md = target_skill_path / "SKILL.md"
                backup_file(target_md)

                # Copy whole directory, excluding existing .backups
                if target_skill_path.exists():
                    # Remove old directory first (but backups are already made)
                    shutil.rmtree(target_skill_path)
                shutil.copytree(skill.path, target_skill_path)

                # Update SKILL.md to ensure consistency
                if target_md.exists():
                    # We might want to ensure description/name are clean, but let's trust copy for now
                    # unless we want to enforce frontmatter updates.
                    # The original script updated frontmatter, so let's do a light pass if needed.
                    pass
            else:
                # Recreate from data
                ensure_dir(target_skill_path)
                target_md = target_skill_path / "SKILL.md"

                backup_file(target_md)

                fm = {"name": skill.name}
                if skill.description:
                    fm["description"] = clean_description(skill.description)
                if skill.license:
                    fm["license"] = skill.license

                fm_str = yaml.dump(fm, sort_keys=False).strip()
                content = f"---\n{fm_str}\n---\n\n{skill.body}\n"
                target_md.write_text(content, encoding="utf-8")

            global_stats.record("Skills", "converted")

    def _save_mcp(self, target_dir: Path, merge: bool = False):
        if not self.config.mcp_servers:
            return

        file_path = target_dir / "mcp.json"
        backup_file(file_path)

        mcp_data = {}
        for name, mcp in self.config.mcp_servers.items():
            # Copilot/VS Code format
            # Use original structure mostly
            transformed = mcp.model_dump(
                exclude={"disabled", "environment"}, exclude_none=True
            )

            # Map 'environment' back to 'env' if needed, though model has 'env' alias
            if mcp.environment and not mcp.env:
                transformed["env"] = mcp.environment

            # Types
            if mcp.type == "local":
                transformed["type"] = "stdio"
            elif mcp.type == "remote":
                # Guess based on URL
                transformed["type"] = (
                    "sse"  # Default assumption for remote in VS Code often
                )

            mcp_data[name] = transformed

        if mcp_data:
            config = {"mcpServers": mcp_data}
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            global_stats.record("MCP", "converted", len(mcp_data))
