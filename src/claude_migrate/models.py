from typing import Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field

# --- Common Models ---


class MCPServer(BaseModel):
    """MCP Server Configuration"""

    type: Literal["stdio", "sse", "http", "local", "remote"] = "stdio"
    command: Optional[Union[str, List[str]]] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    environment: Optional[Dict[str, str]] = None  # Alias for env
    headers: Optional[Dict[str, str]] = None
    enabled: bool = True
    disabled: Optional[bool] = None


class Agent(BaseModel):
    """Agent Configuration"""

    name: str
    description: Optional[str] = None
    model: Optional[str] = None
    tools: Optional[Union[List[str], Dict[str, bool], str]] = None
    prompt: Optional[str] = None
    temperature: Optional[float] = None
    maxSteps: Optional[int] = None

    # Internal fields for conversion
    original_description: Optional[str] = None


class Command(BaseModel):
    """Command/Prompt Configuration"""

    name: str
    description: Optional[str] = None
    body: str  # The actual prompt/template
    model: Optional[str] = None
    agent: Optional[str] = None
    argument_hint: Optional[str] = Field(None, alias="argument-hint")
    subtask: Optional[bool] = None


class Skill(BaseModel):
    """Skill Configuration"""

    name: str
    description: Optional[str] = None
    body: str
    content: Optional[str] = None  # Alias for body
    license: Optional[str] = None
    path: Optional[str] = None  # Path to the skill directory


class ClaudeConfig(BaseModel):
    """Container for loaded Claude Code Configuration"""

    agents: List[Agent] = Field(default_factory=list)
    commands: List[Command] = Field(default_factory=list)
    skills: List[Skill] = Field(default_factory=list)
    mcp_servers: Dict[str, MCPServer] = Field(default_factory=dict)
