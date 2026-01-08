import typer
from pathlib import Path
from typing import Optional, Literal
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from claude_migrate.formats.claude_code import ClaudeLoader
from claude_migrate.formats.opencode import OpenCodeConverter
from claude_migrate.formats.copilot import CopilotConverter
from claude_migrate.utils import (
    global_stats,
    ensure_dir,
    detect_claude_config,
    get_claude_config_for_scope,
    get_default_output_dir,
    sanitize_filename,
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
    scope: Optional[Literal["user", "project"]] = typer.Option(
        None,
        "--scope",
        "-s",
        help="Config scope: 'user' (~/.claude) or 'project' (./.claude). "
             "Default: auto-detect (project takes precedence).",
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
        False,
        "--force",
        help="Overwrite existing files (automatic backups are always created)",
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
            # Explicit source path provided
            claude_base = source.expanduser().resolve()
            # Infer scope from path for output directory defaults
            detected_scope = (
                "project" if claude_base == (Path.cwd() / ".claude") else "user"
            )

            if scope is not None:
                console.print(
                    "[yellow]Warning: --scope ignored when --source is provided[/yellow]"
                )
        elif scope is not None:
            # Explicit scope requested
            claude_base = get_claude_config_for_scope(scope)
            detected_scope = scope
        else:
            # Auto-detect (default behavior)
            claude_base, detected_scope = detect_claude_config()
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    # Determine output directory
    if output is None:
        output = get_default_output_dir(target, detected_scope)
    output = output.expanduser().resolve()

    # Load Claude Code configuration
    console.print(
        f"[cyan]Loading Claude Code configuration from {claude_base}...[/cyan]"
    )

    loader = ClaudeLoader(claude_base, include_plugins=plugins, scope=detected_scope)
    config = loader.load()

    if verbose:
        console.print(f"[dim]  Found {len(config.agents)} agent(s)[/dim]")
        console.print(f"[dim]  Found {len(config.commands)} command(s)[/dim]")
        console.print(f"[dim]  Found {len(config.skills)} skill(s)[/dim]")
        console.print(f"[dim]  Found {len(config.mcp_servers)} MCP server(s)[/dim]")

    merge_mode = output.exists() and not force

    if merge_mode:
        console.print("[cyan]Merge mode: Selective overwrite existing files[/cyan]")

    if force and output.exists():
        console.print(
            "[yellow]Force mode: Overwriting all matching files (backups will be created).[/yellow]"
        )

    merge = output.exists() and not force

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
                converter.save(output, format=format, merge=merge)
            else:
                converter.save(output, merge=merge)

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

    config: ClaudeConfig = converter.config

    console.print("\n[dim]Files that would be:[/dim]")

    merge = output.exists()
    if merge:
        console.print(
            "  [yellow](Merge mode: existing files with matching names will be overwritten)[/yellow]"
        )
    else:
        console.print("  [green](New directory: all files will be created)[/green]")

    def count_status(items, get_path, suffix=""):
        if not items:
            return 0, 0
        created = 0
        overwritten = 0
        for item in items:
            path = get_path(item)
            if merge and path.exists():
                overwritten += 1
            else:
                created += 1
        return created, overwritten

    if target == "opencode":
        created, overwritten = count_status(
            config.agents,
            lambda a: output
            / "agent"
            / f"{a.name.replace('/', '_').replace(':', '_')}.md",
        )
        if config.agents:
            status = []
            if created:
                status.append(f"[green]{created} new[/green]")
            if overwritten:
                status.append(f"[yellow]{overwritten} overwrite[/yellow]")
            console.print(
                f"  agent/*.md ({len(config.agents)} total): {', '.join(status)}"
            )

        created, overwritten = count_status(
            config.commands,
            lambda c: output
            / "command"
            / f"{c.name.replace('/', '_').replace(':', '_')}.md",
        )
        if config.commands:
            status = []
            if created:
                status.append(f"[green]{created} new[/green]")
            if overwritten:
                status.append(f"[yellow]{overwritten} overwrite[/yellow]")
            console.print(
                f"  command/*.md ({len(config.commands)} total): {', '.join(status)}"
            )

        if config.mcp_servers:
            mcp_path = output / "mcp.json"
            if mcp_path.exists():
                console.print(
                    "  mcp.json: [yellow]overwrite (MCP servers exist)[/yellow]"
                )
            else:
                console.print("  mcp.json: [green]new[/green]")
    else:
        created, overwritten = count_status(
            config.agents,
            lambda a: output
            / ".github"
            / "agents"
            / f"{sanitize_filename(a.name)}.agent.md",
        )
        if config.agents:
            status = []
            if created:
                status.append(f"[green]{created} new[/green]")
            if overwritten:
                status.append(f"[yellow]{overwritten} overwrite[/yellow]")
            console.print(
                f"  .github/agents/*.agent.md ({len(config.agents)} total): {', '.join(status)}"
            )

        created, overwritten = count_status(
            config.commands,
            lambda c: output
            / ".github"
            / "prompts"
            / f"{sanitize_filename(c.name)}.prompt.md",
        )
        if config.commands:
            status = []
            if created:
                status.append(f"[green]{created} new[/green]")
            if overwritten:
                status.append(f"[yellow]{overwritten} overwrite[/yellow]")
            console.print(
                f"  .github/prompts/*.prompt.md ({len(config.commands)} total): {', '.join(status)}"
            )

        if config.mcp_servers:
            mcp_path = output / "mcp.json"
            if mcp_path.exists():
                console.print(
                    "  mcp.json: [yellow]overwrite (MCP servers exist)[/yellow]"
                )
            else:
                console.print("  mcp.json: [green]new[/green]")


def _print_instructions(console, target: str, output: Path):
    """Print post-conversion usage instructions."""
    console.print("\n[cyan]Next steps:[/cyan]")

    if target == "opencode":
        console.print("  To use with OpenCode:")
        console.print(f"    1. Use config at: {output}")
        console.print("       (expected locations: ./.opencode or ~/.config/opencode)")
        console.print(
            "    2. Note: Skills are natively supported via .claude/skills and do not need conversion."
        )
        return

    # copilot
    if output == Path.cwd().resolve():
        console.print("  To use with GitHub Copilot in this workspace:")
        console.print("    1. Ensure Copilot Chat is enabled")
        console.print("    2. Reload your VS Code window")
    else:
        console.print("  To use with GitHub Copilot:")
        console.print(f"    1. Copy '{output}/.github' into a workspace root")
        console.print(
            "    2. Note: Skills are natively supported via .claude/skills and do not need conversion."
        )
        console.print("    3. Merge MCP config as needed")
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
