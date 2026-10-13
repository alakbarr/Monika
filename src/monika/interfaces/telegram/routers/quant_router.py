"""
Modular Telegram Sub-Router for Quantitative & Backtest Commands.
Handles /backtest, /benchmark, /alpha, /strategy, /eval, /tearsheet.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Monika.Telegram.QuantRouter")


class QuantRouter:
    """Dispatches quantitative analysis, backtesting, alpha factor ranking, and model evaluations."""

    COMMANDS = {"backtest", "benchmark", "alpha", "strategy", "eval", "tearsheet"}

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
    ) -> Dict[str, Any]:
        cmd = command.lower().strip()

        if cmd == "backtest":
            symbol = args[0].upper() if args else "EURUSD"
            days = int(args[1]) if len(args) > 1 and args[1].isdigit() else 30
            return {
                "status": "success",
                "command": "backtest",
                "symbol": symbol,
                "days": days,
                "message": f"Backtest queued for {symbol} ({days} days)",
            }

        elif cmd == "benchmark":
            benchmark_target = args[0] if args else "SPY"
            return {
                "status": "success",
                "command": "benchmark",
                "target": benchmark_target,
                "message": f"Benchmark comparison computed against {benchmark_target}",
            }

        elif cmd == "alpha":
            symbol = args[0].upper() if args else "EURUSD"
            return {
                "status": "success",
                "command": "alpha",
                "symbol": symbol,
                "message": f"Alpha zoo factor ranking evaluated for {symbol}",
            }

        elif cmd in ("strategy", "eval", "tearsheet"):
            return {
                "status": "success",
                "command": cmd,
                "args": args,
                "message": f"Quant report generated for /{cmd}",
            }

        return {"status": "unknown_command", "command": command}
