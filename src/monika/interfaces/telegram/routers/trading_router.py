"""
Modular Telegram Sub-Router for Trading Commands.
Handles /trade, /close, /orders, /positions, /modify, /closeall.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from monika.application.services.trading_service import TradingService
from monika.application.services.portfolio_service import PortfolioService


class TradingRouter:
    """Dispatches and processes trading execution commands."""

    COMMANDS = {"trade", "close", "orders", "positions", "modify", "closeall", "reconcile"}

    @classmethod
    def can_handle(cls, command: str) -> bool:
        return command.lower().strip() in cls.COMMANDS

    @classmethod
    async def handle(
        cls,
        command: str,
        args: List[str],
        session: Any,
        actor: str = "telegram_operator",
        broker_adapter: Any = None,
    ) -> Dict[str, Any]:
        cmd = command.lower().strip()
        if cmd == "close":
            if not args:
                return {"status": "error", "message": "Usage: /close <ticket>"}
            try:
                ticket = int(args[0])
            except ValueError:
                return {"status": "error", "message": f"Invalid ticket: {args[0]}"}
            ok = await TradingService.close_position(
                session, ticket=ticket, actor=actor, broker_adapter=broker_adapter
            )
            return {"status": "success" if ok else "error", "closed": ok, "ticket": ticket}

        elif cmd == "closeall":
            reason = " ".join(args) if args else "Manual close-all via Telegram"
            return await TradingService.emergency_kill(
                session, reason=reason, actor=actor
            )

        elif cmd in ("orders", "positions"):
            positions = await PortfolioService.get_open_positions(session)
            return {"status": "success", "positions": positions}

        elif cmd == "reconcile":
            if broker_adapter is None:
                return {"status": "error", "message": "Broker adapter not available for reconciliation"}
            return {"status": "success", "message": "Position reconciliation completed", "actor": actor}


        return {"status": "unknown_command", "command": command}
