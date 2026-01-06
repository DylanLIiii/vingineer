import pytest
import json
from claude_migrate.formats.claude_code import ClaudeLoader
from claude_migrate.formats.opencode import OpenCodeConverter
from claude_migrate.formats.copilot import CopilotConverter
from claude_migrate.models import ClaudeConfig, Agent, Command, Skill, MCPServer


@pytest.fixture
def sample_claude_dir(tmp_path):
    # Setup a mock Claude config directory
    base = tmp_path / ".claude"
    base.mkdir()

    (base / "agents").mkdir()
    (base / "commands").mkdir()
    (base / "skills").mkdir()

    # Create an agent
    (base / "agents" / "test-agent.md").write_text(
        "---\nname: test-agent\ndescription: Test Agent\ntools: tool1, tool2\n---\nSystem prompt here",
        encoding="utf-8",
    )

    # Create a command
    (base / "commands" / "test-cmd.md").write_text(
        "---\nname: test-cmd\ndescription: Test Command\n---\nCommand body $ARGUMENTS",
        encoding="utf-8",
    )

    # Create a skill
    skill_dir = base / "skills" / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\n---\nSkill body", encoding="utf-8"
    )

    # Create MCP config
    (base / ".mcp.json").write_text(
        json.dumps(
            {"mcpServers": {"test-server": {"command": "echo", "args": ["hello"]}}}
        ),
        encoding="utf-8",
    )

    return base


def test_claude_loader(sample_claude_dir):
    loader = ClaudeLoader(sample_claude_dir)
    config = loader.load()

    assert len(config.agents) == 1
    assert config.agents[0].name == "test-agent"
    assert config.agents[0].description == "Test Agent"
    assert config.agents[0].prompt == "System prompt here"

    assert len(config.commands) == 1
    assert config.commands[0].name == "test-cmd"
    assert config.commands[0].body == "Command body $ARGUMENTS"

    assert len(config.skills) == 1
    assert config.skills[0].name == "test-skill"

    assert len(config.mcp_servers) == 1
    assert "test-server" in config.mcp_servers


def test_opencode_converter(tmp_path):
    # Create config in memory
    config = ClaudeConfig(
        agents=[
            Agent(name="test-agent", description="Desc", prompt="Prompt", tools=["t1"])
        ],
        commands=[Command(name="test-cmd", body="Body $ARGUMENTS")],
        skills=[Skill(name="test-skill", body="Skill body")],
        mcp_servers={"srv": MCPServer(command="echo")},
    )

    converter = OpenCodeConverter(config)
    output_dir = tmp_path / "opencode_out"
    converter.save(output_dir, format="dir")

    # Verify Agent
    agent_file = output_dir / "agent" / "test-agent.md"
    assert agent_file.exists()
    content = agent_file.read_text(encoding="utf-8")
    assert "mode: subagent" in content
    assert "tools:" in content
    assert "Prompt" in content

    # Verify Command
    cmd_file = output_dir / "command" / "test-cmd.md"
    assert cmd_file.exists()
    content = cmd_file.read_text(encoding="utf-8")
    assert "<command-instruction>" in content

    # Verify Skill
    skill_file = output_dir / "skill" / "test-skill" / "SKILL.md"
    assert skill_file.exists()

    # Verify MCP
    mcp_file = output_dir / "mcp.json"
    assert mcp_file.exists()
    data = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert "srv" in data


def test_copilot_converter(tmp_path):
    config = ClaudeConfig(
        agents=[Agent(name="test-agent", prompt="Prompt")],
        commands=[Command(name="test-cmd", body="Body $ARGUMENTS")],
        skills=[Skill(name="test-skill", body="Skill body")],
        mcp_servers={"srv": MCPServer(command="echo", type="local")},
    )

    converter = CopilotConverter(config)
    output_dir = tmp_path / "copilot_out"
    converter.save(output_dir)

    # Verify Structure
    assert (output_dir / ".github" / "agents" / "test-agent.agent.md").exists()
    assert (output_dir / ".github" / "prompts" / "test-cmd.prompt.md").exists()
    assert (output_dir / ".github" / "skills" / "test-skill" / "SKILL.md").exists()


def test_copilot_converter_sanitizes_filenames(tmp_path):
    config = ClaudeConfig(
        agents=[Agent(name="bad/agent:name", prompt="Prompt")],
        commands=[Command(name="bad/command:name", body="Body $ARGUMENTS")],
        skills=[Skill(name="bad/skill:name", body="Skill body")],
        mcp_servers={"srv": MCPServer(command="echo", type="local")},
    )

    converter = CopilotConverter(config)
    output_dir = tmp_path / "copilot_out"
    converter.save(output_dir)

    assert (output_dir / ".github" / "agents" / "bad_agent_name.agent.md").exists()
    assert (output_dir / ".github" / "prompts" / "bad_command_name.prompt.md").exists()
    assert (output_dir / ".github" / "skills" / "bad_skill_name" / "SKILL.md").exists()

    # Verify Prompt Replacement
    cmd_content = (
        output_dir / ".github" / "prompts" / "bad_command_name.prompt.md"
    ).read_text(encoding="utf-8")
    assert "${input:arguments}" in cmd_content

    # Verify MCP
    assert (output_dir / "mcp.json").exists()
    mcp_data = json.loads((output_dir / "mcp.json").read_text(encoding="utf-8"))
    assert mcp_data["mcpServers"]["srv"]["type"] == "stdio"


def test_copilot_agent_defaults(tmp_path):
    """Test that agent files include VS Code Copilot default fields."""
    config = ClaudeConfig(
        agents=[
            Agent(
                name="test-agent",
                description="Test Description",
                prompt="Agent prompt",
                model="claude-3-opus-20240229",
                tools=["search", "fetch"],
            )
        ],
        commands=[Command(name="test-cmd", body="Body")],
        skills=[Skill(name="test-skill", body="Skill body")],
        mcp_servers={"srv": MCPServer(command="echo", type="local")},
    )

    converter = CopilotConverter(config)
    output_dir = tmp_path / "copilot_out"
    converter.save(output_dir)

    # Verify agent file exists
    agent_file = output_dir / ".github" / "agents" / "test-agent.agent.md"
    assert agent_file.exists()

    # Verify content includes VS Code defaults
    content = agent_file.read_text(encoding="utf-8")

    # Check for required fields
    assert "name: test-agent" in content
    assert "description: Test Description" in content
    assert "model: claude-3-opus-20240229" in content

    # Check for VS Code Copilot default fields
    assert "infer: true" in content
    assert "target: vscode" in content

    # Check for tools
    assert "tools:" in content
    assert "- search" in content
    assert "- fetch" in content

    # Verify YAML frontmatter structure
    assert content.startswith("---")
    assert "Agent prompt" in content


@pytest.fixture
def plugin_v2_installed(tmp_path):
    """Create mock installed_plugins.json with version 2 format."""
    plugins_dir = tmp_path / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)

    plugin_base = tmp_path / "plugin_cache"
    plugin_base.mkdir()

    installed = plugins_dir / "installed_plugins.json"
    installed.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "test-plugin@marketplace": [
                        {
                            "name": "test-plugin",
                            "scope": "project",
                            "directory": str(plugin_base / "test-plugin"),
                        }
                    ],
                    "mgrep@Mixedbread-Grep": [
                        {
                            "name": "mgrep",
                            "scope": "project",
                            "directory": str(plugin_base / "mgrep"),
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    # Create plugin directories
    for plugin_name in ["test-plugin", "mgrep"]:
        plugin_dir = plugin_base / plugin_name
        plugin_dir.mkdir()
        (plugin_dir / "agents").mkdir()
        (plugin_dir / "commands").mkdir()
        (plugin_dir / "skills").mkdir()

        (plugin_dir / "agents" / f"{plugin_name}-agent.md").write_text(
            f"---\nname: {plugin_name}-agent\n---\nPrompt",
            encoding="utf-8",
        )
        (plugin_dir / "commands" / f"{plugin_name}-cmd.md").write_text(
            f"---\nname: {plugin_name}-cmd\n---\nBody",
            encoding="utf-8",
        )
        skill_dir = plugin_dir / "skills" / f"{plugin_name}-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test-skill\n---\nSkill body", encoding="utf-8"
        )

    return tmp_path


def test_plugin_loading_v2_format(plugin_v2_installed, monkeypatch):
    """Test loading plugins with version 2 JSON format."""
    # Mock Path.home() to use test directory
    monkeypatch.setattr("pathlib.Path.home", lambda: plugin_v2_installed)

    loader = ClaudeLoader(
        plugin_v2_installed / ".claude", include_plugins=True, scope="project"
    )
    config = loader.load()

    assert len(config.agents) == 2
    assert config.agents[0].name == "test-plugin:test-plugin-agent"
    assert config.agents[1].name == "mgrep:mgrep-agent"

    assert len(config.commands) == 2
    assert config.commands[0].name == "test-plugin:test-plugin-cmd"
    assert config.commands[1].name == "mgrep:mgrep-cmd"

    assert len(config.skills) == 2


def test_plugin_skip_invalid(tmp_path, monkeypatch):
    """Test that plugins without name/directory are skipped."""
    plugins_dir = tmp_path / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)

    installed = plugins_dir / "installed_plugins.json"
    installed.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "valid@marketplace": [
                        {
                            "name": "valid-plugin",
                            "scope": "project",
                            "directory": str(tmp_path / "valid"),
                        }
                    ],
                    "invalid-missing-name@marketplace": [
                        {"scope": "project", "directory": str(tmp_path / "invalid1")}
                    ],
                    "invalid-missing-dir@marketplace": [
                        {"name": "invalid2", "scope": "project"}
                    ],
                    "invalid-no-path@marketplace": [
                        {
                            "name": "no-path",
                            "scope": "project",
                            "directory": str(tmp_path / "nonexistent"),
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    # Create only valid plugin
    (tmp_path / "valid").mkdir()
    (tmp_path / "valid" / "agents").mkdir()
    (tmp_path / "valid" / "agents" / "agent.md").write_text(
        "---\nname: agent\n---\nPrompt"
    )

    # Mock Path.home() to use test directory
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    loader = ClaudeLoader(tmp_path / ".claude", include_plugins=True, scope="project")
    config = loader.load()

    assert len(config.agents) == 1
    assert config.agents[0].name == "valid-plugin:agent"


def test_plugin_v1_format(tmp_path, monkeypatch):
    """Test backward compatibility with version 1 format."""
    plugins_dir = tmp_path / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)

    plugin_base = tmp_path / "plugin_cache"
    plugin_base.mkdir()

    installed = plugins_dir / "installed_plugins.json"
    installed.write_text(
        json.dumps(
            {
                "version": 1,
                "plugins": [
                    {
                        "name": "old-plugin",
                        "scope": "project",
                        "directory": str(plugin_base / "old"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    (plugin_base / "old").mkdir()
    (plugin_base / "old" / "agents").mkdir()
    (plugin_base / "old" / "agents" / "agent.md").write_text(
        "---\nname: agent\n---\nPrompt"
    )

    # Mock Path.home() to use test directory
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    loader = ClaudeLoader(tmp_path / ".claude", include_plugins=True, scope="project")
    config = loader.load()

    assert len(config.agents) == 1
    assert config.agents[0].name == "old-plugin:agent"


def test_plugin_derive_name_from_key(tmp_path, monkeypatch):
    """Test deriving plugin name from key when name field is missing."""
    plugins_dir = tmp_path / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)

    plugin_base = tmp_path / "plugin_cache"
    plugin_base.mkdir()

    installed = plugins_dir / "installed_plugins.json"
    installed.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "compound-engineering@every-marketplace": [
                        {
                            "scope": "user",
                            "installPath": str(plugin_base / "compound-eng"),
                        }
                    ],
                    "mgrep@Mixedbread-Grep": [
                        {
                            "scope": "user",
                            "installPath": str(plugin_base / "mgrep"),
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    # Create plugin directories
    (plugin_base / "compound-eng").mkdir()
    (plugin_base / "compound-eng" / "agents").mkdir()
    (plugin_base / "compound-eng" / "agents" / "agent.md").write_text(
        "---\nname: agent\n---\nPrompt"
    )

    (plugin_base / "mgrep").mkdir()
    (plugin_base / "mgrep" / "commands").mkdir()
    (plugin_base / "mgrep" / "commands" / "cmd.md").write_text(
        "---\nname: cmd\n---\nBody"
    )

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    loader = ClaudeLoader(tmp_path / ".claude", include_plugins=True)
    config = loader.load()

    # Should derive name from key when name field is missing
    assert len(config.agents) == 1
    assert config.agents[0].name == "compound-engineering:agent"

    assert len(config.commands) == 1
    assert config.commands[0].name == "mgrep:cmd"


def test_plugin_user_scope_skipped(tmp_path, monkeypatch):
    """Test that user-scope plugins are skipped when scope is project (DEPRECATED)."""
    plugins_dir = tmp_path / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)

    plugin_base = tmp_path / "plugin_cache"
    plugin_base.mkdir()

    installed = plugins_dir / "installed_plugins.json"
    installed.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "user-plugin@marketplace": [
                        {
                            "name": "user-plugin",
                            "scope": "user",
                            "directory": str(plugin_base / "user"),
                        }
                    ],
                    "project-plugin@marketplace": [
                        {
                            "name": "project-plugin",
                            "scope": "project",
                            "directory": str(plugin_base / "project"),
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    # Create both plugin directories
    (plugin_base / "user").mkdir()
    (plugin_base / "user" / "agents").mkdir()
    (plugin_base / "user" / "agents" / "agent.md").write_text(
        "---\nname: agent\n---\nUser Prompt"
    )

    (plugin_base / "project").mkdir()
    (plugin_base / "project" / "agents").mkdir()
    (plugin_base / "project" / "agents" / "agent.md").write_text(
        "---\nname: agent\n---\nProject Prompt"
    )

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    # Scope filtering is no longer enforced - all plugins with scope are loaded
    loader = ClaudeLoader(tmp_path / ".claude", include_plugins=True)
    config = loader.load()

    # Both plugins should be loaded (scope filtering removed)
    assert len(config.agents) == 2
    assert config.agents[0].name == "user-plugin:agent"
    assert config.agents[1].name == "project-plugin:agent"


def test_plugin_user_scope_loads_when_user_scope(tmp_path, monkeypatch):
    """Test that user-scope plugins are loaded regardless of scope setting."""
    plugins_dir = tmp_path / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)

    plugin_base = tmp_path / "plugin_cache"
    plugin_base.mkdir()

    installed = plugins_dir / "installed_plugins.json"
    installed.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "user-plugin@marketplace": [
                        {
                            "name": "user-plugin",
                            "scope": "user",
                            "directory": str(plugin_base / "user"),
                        }
                    ],
                    "project-plugin@marketplace": [
                        {
                            "name": "project-plugin",
                            "scope": "project",
                            "directory": str(plugin_base / "project"),
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    # Create both plugin directories
    (plugin_base / "user").mkdir()
    (plugin_base / "user" / "agents").mkdir()
    (plugin_base / "user" / "agents" / "agent.md").write_text(
        "---\nname: agent\n---\nUser Prompt"
    )

    (plugin_base / "project").mkdir()
    (plugin_base / "project" / "agents").mkdir()
    (plugin_base / "project" / "agents" / "agent.md").write_text(
        "---\nname: agent\n---\nProject Prompt"
    )

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    # Scope filtering is no longer enforced - all plugins are loaded
    loader = ClaudeLoader(tmp_path / ".claude", include_plugins=True)
    config = loader.load()

    # Both plugins should be loaded
    assert len(config.agents) == 2


def test_plugin_mcp_from_plugin_json(tmp_path, monkeypatch):
    """Test loading MCP servers from plugin's .claude-plugin/plugin.json."""
    plugins_dir = tmp_path / ".claude" / "plugins"
    plugins_dir.mkdir(parents=True)

    plugin_base = tmp_path / "plugin_cache"
    plugin_base.mkdir()

    installed = plugins_dir / "installed_plugins.json"
    installed.write_text(
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "test-plugin@marketplace": [
                        {
                            "name": "test-plugin",
                            "scope": "project",
                            "installPath": str(plugin_base / "test-plugin"),
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    plugin_dir = plugin_base / "test-plugin"
    plugin_dir.mkdir()

    claude_plugin_dir = plugin_dir / ".claude-plugin"
    claude_plugin_dir.mkdir()

    plugin_json = claude_plugin_dir / "plugin.json"
    plugin_json.write_text(
        json.dumps(
            {
                "name": "test-plugin",
                "mcpServers": {
                    "test-server": {
                        "type": "stdio",
                        "command": "echo",
                        "args": ["hello"],
                    },
                    "disabled-server": {
                        "type": "stdio",
                        "command": "disabled",
                        "args": [],
                        "disabled": True,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    loader = ClaudeLoader(tmp_path / ".claude", include_plugins=True)
    config = loader.load()

    assert len(config.mcp_servers) == 1
    assert "test-plugin:test-server" in config.mcp_servers


def test_opencode_mcp_merge(tmp_path):
    """Test that MCP servers are merged when merge=True."""
    existing_mcp = {
        "existing-server": {
            "command": "echo",
            "args": ["existing"],
        }
    }
    output_dir = tmp_path / "opencode_out"
    output_dir.mkdir()
    mcp_file = output_dir / "mcp.json"
    mcp_file.write_text(json.dumps(existing_mcp), encoding="utf-8")

    config = ClaudeConfig(
        mcp_servers={
            "new-server": MCPServer(command="python", args=["server.py"]),
        }
    )

    converter = OpenCodeConverter(config)
    converter.save(output_dir, merge=True)

    result = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert "existing-server" in result
    assert "new-server" in result


def test_opencode_mcp_merge_disabled_removes(tmp_path):
    """Test that disabled MCP servers are removed during merge."""
    existing_mcp = {
        "to-remove": {
            "command": "echo",
            "args": ["remove"],
        },
        "to-keep": {
            "command": "echo",
            "args": ["keep"],
        },
    }
    output_dir = tmp_path / "opencode_out"
    output_dir.mkdir()
    mcp_file = output_dir / "mcp.json"
    mcp_file.write_text(json.dumps(existing_mcp), encoding="utf-8")

    config = ClaudeConfig(
        mcp_servers={
            "new-server": MCPServer(command="python", args=["server.py"]),
            "to-remove": MCPServer(command="echo", disabled=True),
        }
    )

    converter = OpenCodeConverter(config)
    converter.save(output_dir, merge=True)

    result = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert "to-keep" in result
    assert "new-server" in result
    assert "to-remove" not in result


def test_copilot_mcp_merge(tmp_path):
    """Test that MCP servers are merged for Copilot when merge=True."""
    existing_mcp = {
        "mcpServers": {
            "existing-server": {
                "command": "echo",
                "args": ["existing"],
            }
        }
    }
    output_dir = tmp_path / "copilot_out"
    output_dir.mkdir()
    mcp_file = output_dir / "mcp.json"
    mcp_file.write_text(json.dumps(existing_mcp), encoding="utf-8")

    config = ClaudeConfig(
        mcp_servers={
            "new-server": MCPServer(command="python", args=["server.py"], type="local"),
        }
    )

    converter = CopilotConverter(config)
    converter.save(output_dir, merge=True)

    result = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert "existing-server" in result["mcpServers"]
    assert "new-server" in result["mcpServers"]
    assert result["mcpServers"]["new-server"]["type"] == "stdio"
