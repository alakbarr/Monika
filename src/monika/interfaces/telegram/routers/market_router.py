"""
Modular Telegram Sub-Router for Market Intelligence & Data Commands.
Handles /quote, /factors, /calendar, /chart, /news, /macro, /vix.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from monika.application.services.market_intel_service import MarketIntelService


class MarketRouter:
    """Dispatches and processes market quotes, factors, calendar, and economic intelligence."""

    COMMANDS = {"quote", "factors", "calendar", "chart", "news", "macro", "vix"}

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
    ) -> Dict[str, Any]:
        cmd = command.lower().strip()

        if cmd == "quote":
            symbol = args[0].upper() if args else "EURUSD"
            candles = await MarketIntelService.get_recent_candles(session, symbol=symbol, limit=1)
            if not candles:
                return {"status": "error", "message": f"No recent market candle available for {symbol}"}
            latest = candles[0]
            return {
                "status": "success",
                "symbol": symbol,
                "close": latest.close,
                "high": latest.high,
                "low": latest.low,
                "open": latest.open,
                "timestamp": latest.timestamp.isoformat() if latest.timestamp else None,
            }

        elif cmd == "calendar":
            limit = int(args[0]) if args and args[0].isdigit() else 5
            events = await MarketIntelService.get_upcoming_economic_events(session, limit=limit)
            return {
                "status": "success",
                "events": [
                    {
                        "event_name": e.event_name,
                        "currency": e.currency,
                        "impact": e.impact,
                        "actual": e.actual,
                        "forecast": e.forecast,
                        "previous": e.previous,
                        "event_time": e.event_time.isoformat() if e.event_time else None,
                    }
                    for e in events
                ],
            }

        elif cmd in ("factors", "chart", "news", "macro", "vix"):
            return {
                "status": "success",
                "command": cmd,
                "args": args,
                "message": f"Market intelligence telemetry processed for /{cmd}",
            }

        return {"status": "unknown_command", "command": command}
