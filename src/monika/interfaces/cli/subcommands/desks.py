# ==============================================================================
# File: cli/subcommands/desks.py
# Monika Swarm Trading Desks CLI Subcommand
# ==============================================================================

"""
CLI Subcommand for inspecting and managing specialized multi-agent trading desk swarms.
"""

import argparse
from typing import Any

from rich.table import Table

from monika.application.graph.team_compiler import TeamCompiler
from monika.interfaces.cli.subcommands.base import Subcommand
from monika.interfaces.cli.theme import get_console


class DesksSubcommand(Subcommand):
    """Subcommand for inspecting declarative YAML trading desk swarms."""

    name: str = "desks"
    description: str = "Inspect and manage declarative institutional trading desk swarms."

    def register_subparser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        parser = subparsers.add_parser(self.name, help=self.description)
        desk_sub = parser.add_subparsers(dest="desk_action")

        # 'list' action
        desk_sub.add_parser("list", help="List all available specialized trading desk swarms.")

        # 'inspect' action
        inspect_p = desk_sub.add_parser("inspect", help="Inspect roles, prompts, and tools of a specific desk.")
        inspect_p.add_argument("desk_id", help="The desk ID to inspect (e.g. crypto_trading_desk).")

        return parser

    async def execute(self, args: argparse.Namespace) -> int:
        console = get_console()
        action = getattr(args, "desk_action", "list") or "list"

        if action == "list":
            table = Table(title="Institutional Specialized Swarm Trading Desks", show_header=True)
            table.add_column("Desk ID", style="cyan", no_wrap=True)
            table.add_column("Desk Name", style="bold")
            table.add_column("Target Universe", style="green")
            table.add_column("Consensus Protocol", style="yellow")
            table.add_column("Roles Count", justify="right")

            desks = TeamCompiler.list_available_desks()
            if not desks:
                console.print("[yellow]No desk swarm presets found in presets directory.[/yellow]")
                return 0

            for d_id in sorted(desks):
                cfg = TeamCompiler.load_desk_config(d_id)
                if cfg:
                    univ = ", ".join(cfg.target_universe) if cfg.target_universe else "ALL (Fallback)"
                    table.add_row(
                        cfg.desk_id,
                        cfg.desk_name,
                        univ,
                        cfg.consensus_protocol,
                        str(len(cfg.roles)),
                    )

            console.print(table)
            return 0

        elif action == "inspect":
            desk_id = getattr(args, "desk_id", "")
            cfg = TeamCompiler.load_desk_config(desk_id)
            if not cfg:
                console.print(f"[red]Desk preset '{desk_id}' not found.[/red]")
                return 1

            console.print(f"\n[bold cyan]=== {cfg.desk_name} ({cfg.desk_id}) ===[/bold cyan]")
            console.print(f"[dim]{cfg.description}[/dim]")
            console.print(f"[bold]Target Universe:[/bold] {', '.join(cfg.target_universe) or 'ALL'}")
            console.print(f"[bold]Consensus Protocol:[/bold] {cfg.consensus_protocol}")
            console.print(f"[bold]Min Conviction Threshold:[/bold] {cfg.min_confidence_threshold:.2f}\n")

            role_table = Table(title=f"Analyst Roles for {cfg.desk_name}", show_header=True)
            role_table.add_column("Role ID", style="cyan")
            role_table.add_column("Role Name", style="bold")
            role_table.add_column("Required Tools", style="magenta")

            for role in cfg.roles:
                role_table.add_row(
                    role.role_id,
                    role.name,
                    ", ".join(role.required_tools) if role.required_tools else "None",
                )
            console.print(role_table)
            return 0

        console.print(f"[red]Unknown desk action: {action}[/red]")
        return 1
