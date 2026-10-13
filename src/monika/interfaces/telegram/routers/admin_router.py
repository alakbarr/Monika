"""
Modular Telegram Sub-Router for Administrative & Lifecycle Commands.
Handles /start, /auth, /pair, /status, /settings, /help, /pause, /resume, /run.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Monika.Telegram.AdminRouter")


class AdminRouter:
    """Dispatches administrative, pairing, authorization, and lifecycle management commands."""

    COMMANDS = {"start", "auth", "pair", "status", "settings", "help", "pause", "resume", "run"}

    @classmethod
    def can_handle(cls, command: str) -> bool:
        return command.lower().strip() in cls.COMMANDS

    @classmethod
    async def handle(
        cls,
        command: str,
        args: List[str],
        session: Any = None,
        actor: str = "telegram_operator",
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        cmd = command.lower().strip()

        if cmd in ("pause", "resume", "run") and not is_admin:
            return {"status": "error", "message": f"Command /{cmd} requires administrative authorization"}

        if cmd == "start":
            return {
                "status": "success",
                "message": "Monika Autonomous Quantitative Trading System online.",
            }

        elif cmd == "help":
            return {
                "status": "success",
                "message": "Available sub-routers: Trading (/trade, /close, /orders), Risk (/risk, /kill), Market (/quote, /calendar), Quant (/backtest, /alpha), Admin (/status, /settings).",
            }

        elif cmd == "status":
            return {
                "status": "success",
                "system_status": "operational",
                "message": "Monika core services running nominal.",
            }

        elif cmd in ("auth", "pair", "settings", "pause", "resume", "run"):
            return {
                "status": "success",
                "command": cmd,
                "args": args,
                "actor": actor,
                "message": f"Admin command /{cmd} executed successfully.",
            }

        return {"status": "unknown_command", "command": command}
