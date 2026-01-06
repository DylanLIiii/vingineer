# Claude Migrate

Convert Claude Code configurations (agents, commands, skills, MCPs) to OpenCode and Copilot formats.

## Quick Start with uvx (Recommended)

Run directly from Git without installing:

```bash
# Use latest version
uvx --from git+https://github.com/YOUR_ORG/YOUR_REPO.git claude-migrate convert opencode

# Pin to specific version (recommended for production)
uvx --from git+https://github.com/YOUR_ORG/YOUR_REPO.git@v0.1.0 claude-migrate convert opencode

# With options
uvx --from git+https://github.com/YOUR_ORG/YOUR_REPO.git claude-migrate convert opencode --output ./my-configs
```

**Note**: Replace `YOUR_ORG/YOUR_REPO` with the actual GitHub organization and repository name.

### Persistent Installation from Git

If you want to install the tool permanently and use it without `--from`:

```bash
# Install latest from main branch
uv tool install git+https://github.com/YOUR_ORG/YOUR_REPO.git

# Install specific version
uv tool install git+https://github.com/YOUR_ORG/YOUR_REPO.git@v0.1.0

# Now you can use it directly (add to PATH if needed)
claude-migrate convert opencode
```

To use after installation, you may need to run:
```bash
uv tool update-shell  # or restart your terminal
```

## Installation

### uvx (Run without installation)

```bash
uvx --from git+https://github.com/YOUR_ORG/YOUR_REPO.git claude-migrate convert opencode
```

### uv tool install (Install persistently)

```bash
uv tool install git+https://github.com/YOUR_ORG/YOUR_REPO.git

# May need to update PATH
uv tool update-shell

# Then use directly
claude-migrate convert opencode
```

### From Cloned Repository (Development)

```bash
git clone https://github.com/YOUR_ORG/YOUR_REPO.git
cd YOUR_REPO
pip install -e .
```

### Via PyPI (For persistent installation)

```bash
pip install claude-migrate
```

Use this if you want to install the tool permanently on your system.

### From Source

```bash
pip install -e .
```

## Quick Start

### Convert to OpenCode

```bash
# Auto-detects config scope:
# - If ./.claude exists, uses project config (outputs to ./.opencode)
# - Otherwise uses ~/.claude (outputs to ~/.config/opencode)
claude-migrate convert opencode

# Custom output directory (overrides default)
claude-migrate convert opencode --output ./my-configs

# JSON format (single opencode.json file instead of directories)
claude-migrate convert opencode --format json

# Include installed Claude plugins
claude-migrate convert opencode --plugins
```

### Convert to Copilot

```bash
# Auto-detects config scope:
# - If ./.claude exists, uses project config (writes .github/... into CWD)
# - Otherwise uses ~/.claude (writes to ./copilot_export)
claude-migrate convert copilot

# Custom output directory (overrides default)
claude-migrate convert copilot --output ./my-configs
```

### Advanced Usage

```bash
# Preview changes without writing files
claude-migrate convert opencode --dry-run

# Force overwrite existing files (automatic backups are always created)
claude-migrate convert opencode --force

# Verbose output
claude-migrate convert opencode --verbose

# Explicitly specify config source (overrides auto-detection)
claude-migrate convert opencode --source ~/.claude

# Include installed Claude plugins (project scope only)
claude-migrate convert opencode --plugins
```

## What Gets Converted

| Type | Claude Code Location | OpenCode | Copilot |
|------|---------------------|------------|----------|
| **Agents** | `~/.claude/agents/*.md` or `./.claude/agents/*.md`<br/>(or plugins, namespaced as `pluginName:agent`) | `agent/*.md` | `.github/agents/*.agent.md` (with `infer: true`, `target: vscode`) |
| **Commands** | `~/.claude/commands/*.md` or `./.claude/commands/*.md`<br/>(or plugins, namespaced as `pluginName:command`) | `command/*.md` | `.github/prompts/*.prompt.md` |
| **Skills** | `~/.claude/skills/*/SKILL.md` or `./.claude/skills/*/SKILL.md`<br/>(or plugins, namespaced as `pluginName:skill`) | `skill/*/SKILL.md` | `.github/skills/*/SKILL.md` |
| **MCP Servers** | `~/.claude/.mcp.json` or `./.claude/.mcp.json`<br/>(or plugins, namespaced as `pluginName:server`) | `mcp.json` | `mcp.json` |

**Note**: Use `--plugins` flag to include installed Claude plugins (agents, commands, skills, MCPs from `~/.claude/plugins/`).

## VS Code Copilot Compliance

When converting to Copilot format, the tool generates configurations compatible with VS Code's [Copilot customization specification](https://code.visualstudio.com/docs/copilot/customization/overview).

### Generated Features

| Feature | Status | Notes |
|---------|--------|-------|
| **Prompt Files** | ✅ Full support | Generates `.github/prompts/*.prompt.md` with `name`, `description`, `model`, `agent` fields |
| **Custom Agents** | ✅ Full support | Generates `.github/agents/*.agent.md` with `infer: true` and `target: vscode` defaults |
| **Agent Skills** | ✅ Full support | Generates `.github/skills/*/SKILL.md` following Agent Skills standard |
| **MCP Servers** | ✅ Full support | Generates `mcp.json` with type mapping (`local`→`stdio`, `remote`→`sse`) |

### Known Limitations

The following VS Code Copilot features are not currently supported because Claude Code doesn't provide equivalent fields:
- `envFile` for MCP servers (use `env` field instead)
- `inputs` section for MCP server variables (use environment variables directly)
- Custom agent `handoffs` (manual configuration required)
- `.github/copilot-instructions.md` (create manually if needed)

## Using the Output

### OpenCode

**Directory Format** (default):
```bash
# Copy to OpenCode config location
cp -r opencode_export/* ~/.config/opencode/

# Or use project-level config
cp -r opencode_export/* .opencode/
```

**JSON Format**:
```bash
# Copy the monolithic opencode.json file
cp opencode_export/opencode.json ~/.config/opencode/

# Or use project-level
cp opencode_export/opencode.json .opencode/
```

### Copilot

```bash
# Copy to your GitHub workspace
cp -r copilot_export/.github .github/

# Copy mcp.json
cp copilot_export/mcp.json mcp.json

# Or merge with existing mcp.json
jq -s '.mcpServers += input.mcpServers' mcp.json < copilot_export/mcp.json > mcp.json
```

## Backup Behavior

Files are automatically backed up before overwriting to prevent data loss.

- **Location**: `~/.claude-migrate/backups/`
- **Structure**: Maintains relative directory structure
- **Format**: `<filename>.backup_YYYYMMDD_HHMMSS`
- **Retention**: Last 5 backups per file (older ones automatically deleted)
- **Always active**: Backups are created even with `--force` flag

### Example Backup Structure

```
~/.claude-migrate/backups/
├── agent/
│   ├── test-agent.md.backup_20250106_142530
│   └── test-agent.md.backup_20250106_153000
├── command/
│   └── deploy.md.backup_20250106_140000
└── skill/
    └── review/SKILL.md.backup_20250106_130000
```

### Restoring from Backup

To restore a file from backup:

```bash
# Find backups
ls ~/.claude-migrate/backups/agent/

# Copy backup back
cp ~/.claude-migrate/backups/agent/test-agent.md.backup_20250106_142530 \
   ~/.config/opencode/agent/test-agent.md
```

## Configuration

The tool auto-detects config scope as follows:

- **Project scope**: If `./.claude/` exists in the current working directory, the tool loads project-level config only.
- **User scope**: Otherwise, the tool loads from `~/.claude/`.

You can override auto-detection with `--source PATH`.

**Plugins** are loaded from `~/.claude/plugins/installed_plugins.json` when you pass `--plugins`. Plugin items are namespaced as `pluginName:itemId` to avoid collisions.

## Versioning

When using uvx from Git, you can pin to specific versions using git tags:

| Command | Description |
|---------|-------------|
| `uvx --from git+https://github.com/YOUR_ORG/YOUR_REPO.git claude-migrate ...` | Latest on main branch |
| `uvx --from git+https://github.com/YOUR_ORG/YOUR_REPO.git@v0.1.0 claude-migrate ...` | Specific version (recommended) |
| `uvx --from git+https://github.com/YOUR_ORG/YOUR_REPO.git@main claude-migrate ...` | Latest on main branch (explicit) |
| `uv tool install git+https://github.com/YOUR_ORG/YOUR_REPO.git` | Install persistently to system |

**Tip**: Always pin to a specific version tag in production scripts for reproducibility.

### Persistent Installation

To install the tool permanently and use it like any other CLI command:

```bash
# Install latest version
uv tool install git+https://github.com/YOUR_ORG/YOUR_REPO.git

# Install specific version
uv tool install git+https://github.com/YOUR_ORG/YOUR_REPO.git@v0.1.0

# Run directly (may need to restart terminal or run `uv tool update-shell`)
claude-migrate convert opencode
```

### Creating Releases

To create a new release tag:

```bash
# Tag the release
git tag -a v0.2.0 -m "Release v0.2.0"

# Push the tag
git push origin v0.2.0
```

The CI/CD workflow will verify the build for the tagged version.

## CLI Reference

### `claude-migrate convert`

Convert Claude Code configurations to target format.

**Arguments:**
- `TARGET` - Target format: `opencode` or `copilot`

**Options:**
- `-o, --output PATH` - Output directory (default depends on target and scope)
- `--source PATH` - Claude config directory to read from (overrides auto-detection)
- `--plugins` - Include installed Claude plugins (only honored in project scope)
- `-f, --format [dir\|json]` - Output format (only for OpenCode, default: `dir`)
- `-n, --dry-run` - Preview changes without writing files
- `--force` - Overwrite existing files (automatic backups are always created)
- `-v, --verbose` - Enable verbose output
- `--version` - Show version and exit
- `--help` - Show help message and exit

**Default output directories** (when `--output` is not specified):

| Target | Scope | Default Output |
|--------|-------|---------------|
| opencode | project | `./.opencode` |
| opencode | user | `~/.config/opencode` |
| copilot | project | `./` (writes `.github/...` into workspace) |
| copilot | user | `./copilot_export` |

## Examples

### Migrate to OpenCode with JSON format

```bash
claude-migrate convert opencode --format json --output ./opencode-configs
```

### Preview what would be converted

```bash
claude-migrate convert copilot --dry-run --verbose
```

### Convert user-level config explicitly

```bash
claude-migrate convert opencode --source ~/.claude
```

### Convert project config with plugins

```bash
# Must be run in a directory with ./.claude
claude-migrate convert opencode --plugins
```

### Force overwrite existing directory

```bash
claude-migrate convert opencode --force
```

## Troubleshooting

### "No Claude Code configuration found"

Ensure at least one of the following exists:
- `./.claude/` (for project scope)
- `~/.claude/` (for user scope)

If neither exists, run Claude Code at least once to create the configuration.

### "Output directory already exists"

Use the `--force` flag to overwrite existing files (automatic backups created):

```bash
claude-migrate convert opencode --force
```

**Important**: Files are always backed up before overwriting. Backups are stored at `~/.claude-migrate/backups/` and the last 5 backups per file are retained.

### "No agents/commands/skills found"

Ensure your Claude Code configuration exists:

```bash
ls ~/.claude/agents/
ls ~/.claude/commands/
ls ~/.claude/skills/
```

If using project-level configs, ensure `.claude/` exists in your project directory.

### "--plugins requested but ignored (user scope)"

The `--plugins` flag only works in project scope. If you want to include plugins for user-level conversion, use `--source ~/.claude` and move to a directory with a `./.claude` folder first, or copy the plugin contents manually.

### "Failed to load MCP config"

Check that your `.mcp.json` is valid JSON:

```bash
cat ~/.claude/.mcp.json | python -m json.tool
```

### Conversions but no files in output

Check for conversion errors in the statistics summary. Files with errors are skipped.

Use `--verbose` to see detailed detection information. If using plugins, check that plugin directory paths are valid and contain the expected `.claude/agents`, `.claude/commands`, etc. subdirectories.

## Development

### Running Tests

```bash
# Install in development mode
pip install -e .

# Run all tests
pytest

# Run with coverage
pytest --cov=claude_migrate --cov-report=html

# Run specific test file
pytest tests/test_utils.py
```

### Code Style

```bash
# Lint code
ruff check src/claude_migrate

# Format code
ruff format src/claude_migrate

# Type check
mypy src/claude_migrate
```

### Project Structure

```
claude_migrate/
├── src/
│   └── claude_migrate/
│       ├── __init__.py
│       ├── cli.py
│       ├── models.py
│       ├── utils.py
│       └── formats/
│           ├── __init__.py
│           ├── claude_code.py
│           ├── opencode.py
│           └── copilot.py
├── tests/
│   ├── fixtures/
│   │   ├── claude_minimal/
│   │   ├── claude_typical/
│   │   └── claude_edge_cases/
│   ├── test_cli.py
│   ├── test_formats.py
│   └── test_utils.py
├── pyproject.toml
└── README.md
```

## License

MIT

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
