"""
Agent OS Command Line Interface.

Usage:
    agent-os run              Start the Agent OS runtime
    agent-os spawn            Spawn a new agent
    agent-os list             List running agents
    agent-os status <id>      Get agent status
    agent-os terminate <id>   Terminate an agent
"""

import click
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from . import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="Agent OS")
def main():
    """Agent OS - An operating system for AI agents."""
    pass


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8888, help="Port to bind to")
@click.option("--debug", is_flag=True, help="Enable debug mode")
def run(host: str, port: int, debug: bool):
    """Start the Agent OS runtime."""
    console.print(f"[bold green]Agent OS v{__version__}[/bold green]")
    console.print(f"Starting runtime on {host}:{port}...")
    console.print("[yellow]Runtime not yet implemented - coming in Phase 1[/yellow]")

    # TODO: Start the actual runtime
    # from .runtime import start_runtime
    # start_runtime(host=host, port=port, debug=debug)


@main.command()
@click.option("--goal", "-g", required=True, help="Goal for the agent")
@click.option("--model", "-m", default="claude-3-5-sonnet-20241022", help="Model to use")
@click.option("--tools", "-t", multiple=True, help="Tools to enable")
def spawn(goal: str, model: str, tools: tuple):
    """Spawn a new agent with a goal."""
    console.print(f"[bold]Spawning agent...[/bold]")
    console.print(f"  Goal: {goal}")
    console.print(f"  Model: {model}")
    console.print(f"  Tools: {', '.join(tools) if tools else 'default'}")
    console.print("[yellow]Spawn not yet implemented - coming in Phase 1[/yellow]")


@main.command("list")
def list_agents():
    """List all running agents."""
    table = Table(title="Running Agents")
    table.add_column("ID", style="cyan")
    table.add_column("State", style="green")
    table.add_column("Goal", style="white")
    table.add_column("Model", style="magenta")
    table.add_column("Uptime", style="yellow")

    # TODO: Get actual agents from runtime
    # agents = runtime.list_agents()
    # for agent in agents:
    #     table.add_row(agent.id, agent.state, agent.goal, agent.model, agent.uptime)

    console.print(table)
    console.print("[yellow]No agents running (runtime not started)[/yellow]")


@main.command()
@click.argument("agent_id")
def status(agent_id: str):
    """Get detailed status of an agent."""
    console.print(f"[bold]Agent Status: {agent_id}[/bold]")
    console.print("[yellow]Status not yet implemented - coming in Phase 1[/yellow]")


@main.command()
@click.argument("agent_id")
@click.option("--force", "-f", is_flag=True, help="Force terminate")
def terminate(agent_id: str, force: bool):
    """Terminate an agent."""
    if force:
        console.print(f"[red]Force terminating agent {agent_id}...[/red]")
    else:
        console.print(f"[yellow]Gracefully terminating agent {agent_id}...[/yellow]")
    console.print("[yellow]Terminate not yet implemented - coming in Phase 1[/yellow]")


@main.command()
def info():
    """Show Agent OS system information."""
    console.print(f"[bold green]Agent OS v{__version__}[/bold green]")
    console.print()

    info_table = Table(show_header=False, box=None)
    info_table.add_column("Key", style="cyan")
    info_table.add_column("Value", style="white")

    info_table.add_row("Version", __version__)
    info_table.add_row("License", "Apache 2.0")
    info_table.add_row("Python", "3.11+")
    info_table.add_row("Status", "Phase 1 - Foundation")
    info_table.add_row("Docs", "https://github.com/YOUR_USERNAME/agent-os")

    console.print(info_table)


if __name__ == "__main__":
    main()
