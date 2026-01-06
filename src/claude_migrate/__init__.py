"""Claude Migrate - Convert Claude Code configurations to OpenCode and Copilot formats."""

__version__ = "0.1.0"
from claude_migrate.models import ClaudeConfig, Agent, Command, Skill, MCPServer
from claude_migrate.utils import (
    Statistics,
    expand_vars,
    parse_frontmatter,
    strip_jsonc_comments,
    load_jsonc,
)

__all__ = [
    "__version__",
    "ClaudeConfig",
    "Agent",
    "Command",
    "Skill",
    "MCPServer",
    "Statistics",
    "expand_vars",
    "parse_frontmatter",
    "strip_jsonc_comments",
    "load_jsonc",
]
