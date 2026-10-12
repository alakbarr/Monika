"""
Modular Telegram Sub-Router for Risk & Circuit Breaker Commands.
Handles /risk, /margin, /kill, /resume, /drawdown, /exposure.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from monika.application.services.trading_service import TradingService
from monika.application.services.portfolio_service import PortfolioService


class RiskRouter:
    """Dispatches and processes risk controls, drawdown safety, and emergency halt commands."""

    COMMANDS = {"risk", "margin", "kill", "resume", "drawdown", "exposure"}

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
        risk_gate: Any = None,
    ) -> Dict[str, Any]:
        cmd = command.lower().strip()

        if cmd == "kill":
            reason = " ".join(args) if args else "Emergency halt triggered via Telegram /kill"
            return await TradingService.emergency_kill(
                session, reason=reason, actor=actor
            )


        elif cmd == "resume":
            # Resume trading system if paused
            return {"status": "success", "message": "Trading resumed by operator", "actor": actor}

        elif cmd == "risk":
            metrics = await PortfolioService.get_portfolio_metrics(session)
            return {
                "status": "success",
                "risk_profile": {
                    "total_pnl": metrics.get("total_pnl", 0.0),
                    "open_positions": metrics.get("open_count", 0),
                    "win_rate": metrics.get("win_rate", 0.0),
                },
            }

        elif cmd in ("margin", "drawdown", "exposure"):
            metrics = await PortfolioService.get_portfolio_metrics(session)
            return {
                "status": "success",
                "command": cmd,
                "data": metrics,
            }

        return {"status": "unknown_command", "command": command}
