# Coding Agents Configuration

Instructions for AI agents working on the `claude-migrate` repository.

## Project Overview

**Type**: Python CLI application
**Purpose**: Convert Claude Code configurations to OpenCode and Copilot formats
**Python Version**: 3.11+
**Dependencies**: typer, pydantic, pyyaml, rich, pytest, ruff, mypy

## Design Decisions

*   **OpenCode Skills**: OpenCode natively supports Claude skills in `.claude/skills` and `~/.claude/skills`. Therefore, `claude-migrate` intentionally does *not* convert skills to OpenCode format to avoid redundancy. Agents should not re-implement skill conversion for OpenCode.

## Build Commands

```bash
pip install -e .[dev]
ruff check --fix src/claude_migrate tests && ruff format src/claude_migrate tests
mypy src/claude_migrate/
pytest -q
pytest tests/test_cli.py::test_cli_convert_opencode -vv
pytest tests/test_utils.py -q
pytest -x tests/test_utils.py -v --showlocals
pytest --lf
```

## Code Style Guidelines

```python
# 1. Standard library, 2. Third-party, 3. Local
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Literal
import typer
from pydantic import BaseModel
from claude_migrate.models import ClaudeConfig

# Line length: 88 (ruff format)

# Classes: PascalCase, Functions/variables: snake_case, Constants: UPPER_SNAKE_CASE
class Statistics: pass
def parse_frontmatter(content: str): pass
USER_HOME = Path.home()

# Type hints and Optional fields
def expand_vars(value: Any, extra_vars: Dict[str, str] = {}) -> Any: pass
output_dir: Optional[Path] = None
target: Literal["opencode", "copilot"]
```

### Error Handling

```python
import typer
from claude_migrate.utils import global_stats

def convert_file(file_path: Path):
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    try:
        content = file_path.read_text()
    except PermissionError as e:
        raise typer.Exit(code=1, message=f"Permission denied: {e}")

try:
    risky_operation()
except Exception as e:
    print(f"Operation failed: {e}")
    global_stats.record("Category", "failed")
```

### Pydantic Models & CLI Commands

```python
from pydantic import BaseModel, Field
import typer
from rich.console import Console

class Agent(BaseModel):
    """Agent Configuration"""
    name: str
    description: Optional[str] = None
    tools: Optional[Union[List[str], Dict[str, bool]]] = None
    model: Optional[str] = Field(None, description="The model to use")

app = typer.Typer(help="Application description")

@app.command()
def convert(
    target: str = typer.Argument(..., help="Target format"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    console = Console()
    if verbose:
        console.print(f"[dim]Starting conversion to {target}...[/dim]")
```

## Key Patterns

```python
from pathlib import Path
import os
import pytest
from typer.testing import CliRunner
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

# Path operations
base_dir = Path.home() / ".claude"
file_path = base_dir / "agents" / "test-agent.md"
output = Path.cwd() / "export"

if not file_path.exists():
    raise FileNotFoundError(f"File not found: {file_path}")
if not output_dir.exists():
    os.makedirs(output_dir)

# Configuration loading
def load_jsonc(file_path: Path) -> Dict[str, Any]:
    """Read a JSON/JSONC file safely."""
    if not file_path.exists():
        return {}
    raw_text = file_path.read_text(encoding="utf-8")
    cleaned = strip_jsonc_comments(raw_text)
    return json.loads(cleaned) if cleaned.strip() else {}

# Statistics
class Statistics:
    def __init__(self) -> None:
        self.stats: Dict[str, Dict[str, int]] = {
            "Agents": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
            "Commands": {"detected": 0, "converted": 0, "skipped": 0, "failed": 0},
        }
    def record(self, category: str, type_: str, count: int = 1) -> None:
        self.stats[category][type_] += count

global_stats = Statistics()

# Test fixtures and HOME override
@pytest.fixture
def sample_config(tmp_path):
    config_dir = tmp_path / ".claude"
    config_dir.mkdir()
    return config_dir

def test_with_home_override(tmp_path, sample_config):
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    try:
        pass
    finally:
        if old_home:
            os.environ["HOME"] = old_home

# Rich console
console = Console()
console.print("[cyan]Loading configuration...[/cyan]")
console.print("[red]Error: File not found[/red]")
console.print("[yellow]Warning: Using default values[/yellow]")

with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    console=console,
    transient=True,
) as progress:
    task = progress.add_task("Processing...", total=None)
    progress.update(task, completed=True)
```

## Common Issues

```bash
mypy src/claude_migrate/
pytest tests/test_cli.py::test_cli_convert_opencode -vv --showlocals
pytest -x tests/

from claude_migrate.models import ClaudeConfig

# Lazy imports to avoid circular dependencies
def function():
    from claude_migrate.formats.opencode import OpenCodeConverter
    return OpenCodeConverter(config)
```

## File Structure

```
claude_migrate/
├── src/claude_migrate/
│   ├── __init__.py
│   ├── cli.py
│   ├── models.py
│   ├── utils.py
│   └── formats/
│       ├── __init__.py
│       ├── claude_code.py
│       ├── opencode.py
│       └── copilot.py
├── tests/
│   ├── test_cli.py
│   ├── test_formats.py
│   └── test_utils.py
├── conftest.py
├── pyproject.toml
└── README.md
```

No `.cursorrules` or `.github/copilot-instructions.md` found.

CI/CD: GitHub Actions runs ruff, mypy, pytest with 60% coverage minimum, uploads to Codecov.


