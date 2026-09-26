# ==============================================================================
# File: cli/subcommands/daemon.py
# ==============================================================================

"""
Daemon & Lifecycle Subcommands (run, stop, pause, resume, kill, status).
"""

import argparse
import asyncio
import os
import sys
from typing import Any

from cli.subcommands.base import Subcommand
from cli.theme import get_console, stamp_err, stamp_info, stamp_ok, stamp_warn


class DaemonSubcommand(Subcommand):
    name = "daemon"
    description = "Manage Monika Trading Agent daemon process lifecycle."

    def register_subparser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        parser = subparsers.add_parser("daemon", help="Manage daemon process.")
        sub = parser.add_subparsers(dest="daemon_action")
        
        # Subactions
        sub.add_parser("status", help="Show system status and daemon state.")
        sub.add_parser("pause", help="Pause trading proposals.")
        sub.add_parser("resume", help="Resume trading proposals.")
        
        kill_p = sub.add_parser("kill", help="Trigger emergency kill switch.")
        kill_p.add_argument("-y", "--yes", action="store_true", help="Bypass confirmation prompt.")
        
        stop_p = sub.add_parser("stop", help="Stop running Monika daemon.")
        stop_p.add_argument("-f", "--force", action="store_true", help="Force kill daemon.")

        return parser

    async def execute(self, args: argparse.Namespace) -> int:
        action = getattr(args, "daemon_action", None) or getattr(args, "command", "status")
        from cli.main import (
            _cmd_status,
            _cmd_pause,
            _cmd_resume,
            _cmd_kill,
            _cmd_stop,
        )

        if action == "status":
            await _cmd_status(args)
        elif action == "pause":
            await _cmd_pause(args)
        elif action == "resume":
            await _cmd_resume(args)
        elif action == "kill":
            await _cmd_kill(args)
        elif action == "stop":
            await _cmd_stop(args)
        else:
            get_console().print(f"{stamp_err('ERROR')} Unknown daemon action: {action}")
            return 1
        return 0
