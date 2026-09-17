# ==============================================================================
# File: analysis/event_broadcaster.py
# Description: Live Pipeline Event Broadcaster for WebSocket & Observability (Q4)
# ==============================================================================

"""
Analysis pipeline event broadcaster for Monika AI Trading Agent.

Emits live step-level events at LangGraph node & stage boundaries:
- analysis_cycle_start: Emitted when an analysis cycle begins.
- analysis_step_start: Emitted when an individual stage/node starts execution.
- analysis_step_complete: Emitted upon node completion with timing and tokens.
- analysis_cycle_complete: Emitted upon cycle conclusion with decision and metrics.

Non-blocking, exception-safe, and gracefully operates offline or during backtesting.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.Analysis.EventBroadcaster")


def emit_analysis_event(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Broadcast an analysis pipeline event asynchronously to active WebSocket clients.
    Safe to invoke from sync or async contexts. Does not raise exceptions.
    """
    try:
        enriched_payload = dict(payload)
        if "timestamp" not in enriched_payload:
            enriched_payload["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Try to dispatch via broadcast_live_event in dashboard API
        try:
            from logging_observability.dashboard.api import broadcast_live_event

            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(broadcast_live_event(event_type, enriched_payload))
            except RuntimeError:
                # No running event loop in current thread
                pass
        except ImportError:
            pass

    except Exception as exc:
        logger.debug(f"[EventBroadcaster] Failed emitting {event_type}: {exc}")


async def emit_analysis_event_async(event_type: str, payload: Dict[str, Any]) -> None:
    """Coroutine version for explicit awaiting inside async nodes."""
    try:
        enriched_payload = dict(payload)
        if "timestamp" not in enriched_payload:
            enriched_payload["timestamp"] = datetime.now(timezone.utc).isoformat()

        from logging_observability.dashboard.api import broadcast_live_event

        await broadcast_live_event(event_type, enriched_payload)
    except Exception as exc:
        logger.debug(f"[EventBroadcaster Async] Failed emitting {event_type}: {exc}")
