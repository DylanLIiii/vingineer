import typer
from pathlib import Path
from typing import Optional, Literal
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
import shutil

from claude_migrate.formats.claude_code import ClaudeLoader
from claude_migrate.formats.opencode import OpenCodeConverter
from claude_migrate.formats.copilot import CopilotConverter
from claude_migrate.utils import (
    global_stats,
    ensure_dir,
    detect_claude_config,
    get_default_output_dir,
)
from claude_migrate.models import ClaudeConfig

app = typer.Typer(
    help="Convert Claude Code configurations to OpenCode and Copilot formats"
)


@app.command()
def convert(
    target: Literal["opencode", "copilot"] = typer.Argument(
        ..., help="Target format (opencode or copilot)"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory (default depends on target and scope)",
    ),
    source: Optional[Path] = typer.Option(
        None,
        "--source",
        help="Claude config directory to read from (overrides auto-detection)",
    ),
    plugins: bool = typer.Option(
        False,
        "--plugins",
        help="Include installed Claude plugins (project scope only)",
    ),
    format: Literal["dir", "json"] = typer.Option(
        "dir",
        "--format",
        "-f",
        help="Output format (only for opencode: dir or json, default: dir)",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Preview changes without writing files"
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing output directory"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose output"
    ),
):
    """
    Convert Claude Code configurations to target format.

    Example usage:
        claude-migrate convert opencode
        claude-migrate convert copilot --output ./my-configs
        claude-migrate convert opencode --format json --dry-run
    """
    # Setup
    console = Console()

    try:
        if source is not None:
            claude_base = source.expanduser().resolve()
            scope = "project" if claude_base == (Path.cwd() / ".claude") else "user"
        else:
            claude_base, scope = detect_claude_config()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    # Determine output directory
    if output is None:
        output = get_default_output_dir(target, scope)
    output = output.expanduser().resolve()

    # Load Claude Code configuration
    console.print(
        f"[cyan]Loading Claude Code configuration from {claude_base}...[/cyan]"
    )
    if plugins and scope != "project":
        console.print("[yellow]--plugins requested but ignored (user scope).[/yellow]")

    loader = ClaudeLoader(claude_base, include_plugins=(plugins and scope == "project"))
    config = loader.load()

    if verbose:
        console.print(f"[dim]  Found {len(config.agents)} agent(s)[/dim]")
        console.print(f"[dim]  Found {len(config.commands)} command(s)[/dim]")
        console.print(f"[dim]  Found {len(config.skills)} skill(s)[/dim]")
        console.print(f"[dim]  Found {len(config.mcp_servers)} MCP server(s)[/dim]")

    # Check output directory
    if output.exists():
        if not force:
            console.print(
                f"[red]Error: Output directory '{output}' already exists.[/red]"
            )
            console.print("[yellow]Use --force to overwrite.[/yellow]")
            raise typer.Exit(code=1)

        if not dry_run:
            console.print(
                f"[yellow]Removing existing output directory: {output}[/yellow]"
            )
            shutil.rmtree(output)

    # Display conversion summary
    console.print(f"\n[cyan]Converting to {target.upper()} format...[/cyan]")

    if target == "opencode":
        converter = OpenCodeConverter(config)
    else:  # copilot
        converter = CopilotConverter(config)

    # Execute conversion
    if dry_run:
        console.print("\n[yellow]DRY RUN - No files will be written.[/yellow]")
        _preview_changes(console, converter, output, target, format)
    else:
        ensure_dir(output)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Converting...", total=None)

            if target == "opencode":
                converter.save(output, format=format)
            else:
                converter.save(output)

            progress.update(task, completed=True)

    # Print statistics and instructions
    console.print("[green]Conversion complete![/green]")
    console.print(f"[dim]Output written to: {output}[/dim]")
    console.print("\n")
    global_stats.print_summary()
    _print_instructions(console, target, output)


def _preview_changes(
    console: Console, converter, output: Path, target: str, format: str
):
    """Preview what would be converted without writing files."""

    # Get the config from converter
    config: ClaudeConfig = converter.config

    console.print("\n[dim]Files that would be created:[/dim]")

    if target == "opencode":
        if config.agents:
            console.print(f"  [dim]-[/dim] agent/*.md ({len(config.agents)} files)")
        if config.commands:
            console.print(f"  [dim]-[/dim] command/*.md ({len(config.commands)} files)")
        if config.skills:
            console.print(
                f"  [dim]-[/dim] skill/*/SKILL.md ({len(config.skills)} files)"
            )
        if config.mcp_servers:
            console.print("  [dim]-[/dim] mcp.json")
    else:  # copilot
        if config.agents:
            console.print(
                f"  [dim]-[/dim] .github/agents/*.agent.md ({len(config.agents)} files)"
            )
        if config.commands:
            console.print(
                f"  [dim]-[/dim] .github/prompts/*.prompt.md ({len(config.commands)} files)"
            )
        if config.skills:
            console.print(
                f"  [dim]-[/dim] .github/skills/*/SKILL.md ({len(config.skills)} files)"
            )
        if config.mcp_servers:
            console.print("  [dim]-[/dim] mcp.json")


def _print_instructions(console, target: str, output: Path):
    """Print post-conversion usage instructions."""
    console.print("\n[cyan]Next steps:[/cyan]")

    if target == "opencode":
        console.print("  To use with OpenCode:")
        console.print(f"    1. Use config at: {output}")
        console.print("       (expected locations: ./.opencode or ~/.config/opencode)")
        return

    # copilot
    if output == Path.cwd().resolve():
        console.print("  To use with GitHub Copilot in this workspace:")
        console.print("    1. Ensure Copilot Chat is enabled")
        console.print("    2. Reload your VS Code window")
    else:
        console.print("  To use with GitHub Copilot:")
        console.print(f"    1. Copy '{output}/.github' into a workspace root")
        console.print("    2. Merge MCP config as needed")
        console.print(
            "       (VS Code workspace MCP file is typically .vscode/mcp.json)"
        )


def _version_callback(value: bool):
    if value:
        from claude_migrate import __version__

        typer.echo(f"claude-migrate version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True
    ),
):
    pass


if __name__ == "__main__":
    app()
