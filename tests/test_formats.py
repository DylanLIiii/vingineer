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
