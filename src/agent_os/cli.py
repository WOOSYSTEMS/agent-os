"""
Agent OS Command Line Interface.

Usage:
    agent-os agent "your goal"    Run an agent with a goal
    agent-os info                 Show system information
    agent-os tools                List available tools
"""

import asyncio
import os
import click
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.markdown import Markdown
from rich import print as rprint

from . import __version__
from .core import AgentConfig, AgentState
from .runtime import AgentRuntime
from .tools import BUILTIN_TOOLS

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="Agent OS")
def main():
    """Agent OS - An operating system for AI agents."""
    pass


@main.command()
@click.argument("goal")
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Model to use")
@click.option("--tools", "-t", multiple=True, help="Tools to enable (default: all)")
@click.option("--max-iterations", default=50, help="Maximum tool calls")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
def agent(goal: str, model: str, tools: tuple, max_iterations: int, verbose: bool):
    """Run an agent with a goal.

    Example:
        agent-os agent "List all Python files in the current directory"
    """
    console.print(f"\n[bold green]Agent OS v{__version__}[/bold green]")
    console.print(f"[dim]Model: {model}[/dim]\n")

    # Validate API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[red]Error: ANTHROPIC_API_KEY environment variable not set[/red]")
        console.print("[dim]Set it with: export ANTHROPIC_API_KEY=your-key[/dim]")
        return

    # Create config
    config = AgentConfig(
        goal=goal,
        model=model,
        tools=list(tools) if tools else BUILTIN_TOOLS,
        capabilities=[
            "shell:*:execute",
            "file:*:read,write",
            "http:*:request",
        ],
        max_iterations=max_iterations
    )

    console.print(Panel(f"[bold]Goal:[/bold] {goal}", title="Agent", border_style="blue"))

    # Run agent
    asyncio.run(_run_agent(config, verbose))


async def _run_agent(config: AgentConfig, verbose: bool):
    """Run the agent and display results."""
    runtime = AgentRuntime()
    await runtime.start()

    try:
        # Spawn agent
        agent = await runtime.spawn(config)
        console.print(f"[dim]Agent ID: {agent.id}[/dim]\n")

        # Track tool calls
        iteration = 0

        def on_event_sync(event):
            nonlocal iteration
            if event.type == "tool.executed":
                iteration += 1
                tool = event.data.get("tool", "unknown")
                status = event.data.get("status", "unknown")
                status_color = "green" if status == "success" else "red"
                console.print(f"  [{iteration}] [cyan]{tool}[/cyan] → [{status_color}]{status}[/status_color]")

        # Run agent
        console.print("[bold]Executing...[/bold]")

        result_agent = await runtime.run(agent.id)

        # Show result
        console.print()

        if result_agent.state == AgentState.COMPLETED:
            console.print(Panel(
                result_agent.result or "(no output)",
                title="[green]Result[/green]",
                border_style="green"
            ))
        elif result_agent.state == AgentState.FAILED:
            console.print(Panel(
                result_agent.last_error or "Unknown error",
                title="[red]Failed[/red]",
                border_style="red"
            ))
        else:
            console.print(f"[yellow]Agent ended in state: {result_agent.state}[/yellow]")

        # Stats
        console.print(f"\n[dim]Iterations: {result_agent.iterations} | Tool calls: {len(result_agent.tool_calls)}[/dim]")

        # Verbose: show tool calls
        if verbose and result_agent.tool_calls:
            console.print("\n[bold]Tool Call History:[/bold]")
            for i, call in enumerate(result_agent.tool_calls, 1):
                console.print(f"\n[cyan]#{i} {call['tool']}[/cyan]")
                console.print(f"  Input: {call['input']}")
                result = call['result']
                status = result.get('status', 'unknown')
                if status == 'success':
                    output = result.get('output', '')
                    if len(output) > 200:
                        output = output[:200] + "..."
                    console.print(f"  Output: {output}")
                else:
                    console.print(f"  Error: {result.get('error', 'unknown')}")

    finally:
        await runtime.stop()


@main.command()
def tools():
    """List available tools."""
    console.print(f"\n[bold green]Agent OS v{__version__}[/bold green]")
    console.print("[bold]Available Tools:[/bold]\n")

    from .tools import shell, file, http

    all_tools = shell.TOOLS + file.TOOLS + http.TOOLS

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Tool", style="cyan")
    table.add_column("Description")
    table.add_column("Required Capability", style="yellow")

    for schema, _ in all_tools:
        caps = ", ".join(schema.required_capabilities) if schema.required_capabilities else "none"
        table.add_row(schema.name, schema.description[:60] + "..." if len(schema.description) > 60 else schema.description, caps)

    console.print(table)


@main.command()
def info():
    """Show Agent OS system information."""
    console.print(f"\n[bold green]Agent OS v{__version__}[/bold green]\n")

    info_table = Table(show_header=False, box=None)
    info_table.add_column("Key", style="cyan")
    info_table.add_column("Value", style="white")

    info_table.add_row("Version", __version__)
    info_table.add_row("License", "Apache 2.0")
    info_table.add_row("Python", "3.11+")
    info_table.add_row("Status", "Phase 1 - Foundation")
    info_table.add_row("GitHub", "https://github.com/WOOSYSTEMS/agent-os")
    info_table.add_row("API Key", "✓ Set" if os.environ.get("ANTHROPIC_API_KEY") else "✗ Not set")

    console.print(info_table)

    # Show tools count
    console.print(f"\n[dim]Built-in tools: {len(BUILTIN_TOOLS)}[/dim]")


if __name__ == "__main__":
    main()
