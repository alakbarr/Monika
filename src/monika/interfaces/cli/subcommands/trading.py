# ==============================================================================
# File: cli/subcommands/trading.py
# ==============================================================================

"""
Trading Operations Subcommands (positions, unsuspend).
"""

import argparse

from monika.interfaces.cli.subcommands.base import Subcommand


class TradingSubcommand(Subcommand):
    name = "trading"
    description = "Trading operations and position inspection."

    def register_subparser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        parser = subparsers.add_parser("trading", help="Trading operations and positions.")
        sub = parser.add_subparsers(dest="trading_action")

        pos_p = sub.add_parser("positions", help="List active open positions.")
        pos_p.add_argument("--paper", action="store_true", help="List paper positions only.")

        unsusp_p = sub.add_parser("unsuspend", help="Unsuspend symbol or all symbols.")
        unsusp_p.add_argument("symbol", nargs="?", default=None, help="Specific symbol.")
        unsusp_p.add_argument("--all", action="store_true", help="Unsuspend all symbols.")

        return parser

    async def execute(self, args: argparse.Namespace) -> int:
        raw_action = getattr(args, "trading_action", None)
        action = raw_action if raw_action and raw_action != "trading" else "positions"
        from monika.interfaces.cli.commands.daemon_ctrl import _cmd_positions, _cmd_unsuspend

        if action == "positions":
            await _cmd_positions(args)
        elif action == "unsuspend":
            await _cmd_unsuspend(args)
        return 0
