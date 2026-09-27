# ==============================================================================
# File: cli/subcommands/runcard.py
# ==============================================================================

"""
Cryptographic Run Card Subcommand.
Generates and verifies tamper-evident execution run cards.
"""

import argparse
import json
from pathlib import Path
from cli.subcommands.base import Subcommand
from cli.theme import get_console, stamp_info, stamp_ok, stamp_err, stamp_warn


class RunCardSubcommand(Subcommand):
    name = "runcard"
    description = "Generate and verify cryptographic execution run cards."

    def register_subparser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        parser = subparsers.add_parser("runcard", help="Cryptographic Run Card management.")
        sub = parser.add_subparsers(dest="runcard_action")

        gen_p = sub.add_parser("generate", help="Generate signed cryptographic run card.")
        gen_p.add_argument("--output", default="run_card.json", help="Destination path for run_card.json.")

        ver_p = sub.add_parser("verify", help="Verify integrity and signature of a run card.")
        ver_p.add_argument("--input", default="run_card.json", help="Path to run_card.json.")

        return parser

    async def execute(self, args: argparse.Namespace) -> int:
        action = getattr(args, "runcard_action", "generate")
        console = get_console()

        from logging_observability.run_card import RunCardGenerator
        from config.settings import load_settings

        if action == "generate":
            out_path = getattr(args, "output", "run_card.json")
            console.print(f"{stamp_info('RUNCARD')} Generating signed execution run card...")
            try:
                cfg = load_settings()
            except Exception:
                cfg = {}

            card = RunCardGenerator.generate(settings=cfg, output_path=out_path)
            console.print(f"{stamp_ok('SUCCESS')} Run card created at `{out_path}`.")
            console.print(f"  • Run ID: [bold cyan]{card['run_id']}[/bold cyan]")
            console.print(f"  • Git Commit: {card['git_info']['commit_hash'][:8]}")
            console.print(f"  • Signature: [green]{card['signature'][:16]}...[/green]")
            return 0

        elif action == "verify":
            in_path = getattr(args, "input", "run_card.json")
            if not Path(in_path).exists():
                console.print(f"{stamp_err('ERROR')} File not found: `{in_path}`.")
                return 1

            console.print(f"{stamp_info('RUNCARD')} Verifying `{in_path}`...")
            card = RunCardGenerator.load(in_path)
            ok, reason = RunCardGenerator.verify(card)
            if ok:
                console.print(f"{stamp_ok('VERIFIED')} {reason}")
                console.print(f"  • Run ID: {card.get('run_id')}")
                console.print(f"  • Timestamp: {card.get('timestamp')}")
                console.print(f"  • Mode: {card.get('config_fingerprint', {}).get('trading_mode')}")
                return 0
            else:
                console.print(f"{stamp_err('FAILED')} {reason}")
                return 1

        else:
            console.print(f"{stamp_warn('UNKNOWN')} Unknown runcard action: '{action}'. Use generate or verify.")
            return 1
