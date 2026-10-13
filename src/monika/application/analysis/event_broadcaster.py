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
Supports dynamic subscriber registration for clean-architecture decoupling.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

logger = logging.getLogger("Monika.Application.Analysis.EventBroadcaster")

_event_listeners: List[Callable[[str, Dict[str, Any]], Any]] = []


def register_event_listener(listener: Callable[[str, Dict[str, Any]], Any]) -> None:
    """Register an observer callback (e.g. WebSocket broadcaster) for live pipeline events."""
    if listener not in _event_listeners:
        _event_listeners.append(listener)


def unregister_event_listener(listener: Callable[[str, Dict[str, Any]], Any]) -> None:
    """Unregister an observer callback."""
    if listener in _event_listeners:
        _event_listeners.remove(listener)


async def _safe_await(awaitable_obj: Any) -> None:
    try:
        await awaitable_obj
    except Exception as err:
        logger.debug(f"[EventBroadcaster] Async listener error: {err}")


def _dispatch_to_listener(
    listener: Callable[[str, Dict[str, Any]], Any], event_type: str, payload: Dict[str, Any]
) -> None:
    try:
        res = listener(event_type, payload)
        if inspect.isawaitable(res):
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(_safe_await(res))
            except RuntimeError:
                pass
    except Exception as exc:
        logger.debug(f"[EventBroadcaster] Listener dispatch error: {exc}")


def emit_analysis_event(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Broadcast an analysis pipeline event asynchronously to active listeners.
    Safe to invoke from sync or async contexts. Does not raise exceptions.
    """
    try:
        enriched_payload = dict(payload)
        if "timestamp" not in enriched_payload:
            enriched_payload["timestamp"] = datetime.now(timezone.utc).isoformat()

        if _event_listeners:
            for listener in list(_event_listeners):
                _dispatch_to_listener(listener, event_type, enriched_payload)
            return

        # Fallback to direct dashboard broadcast if listeners not registered yet
        try:
            from monika.interfaces.dashboard.routes.common import broadcast_live_event

            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(broadcast_live_event(event_type, enriched_payload))
            except RuntimeError:
                pass
        except ImportError, Exception:
            pass

    except Exception as exc:
        logger.debug(f"[EventBroadcaster] Failed emitting {event_type}: {exc}")


async def emit_analysis_event_async(event_type: str, payload: Dict[str, Any]) -> None:
    """Coroutine version for explicit awaiting inside async nodes."""
    try:
        enriched_payload = dict(payload)
        if "timestamp" not in enriched_payload:
            enriched_payload["timestamp"] = datetime.now(timezone.utc).isoformat()

        if _event_listeners:
            for listener in list(_event_listeners):
                try:
                    res = listener(event_type, enriched_payload)
                    if inspect.isawaitable(res):
                        await res
                except Exception as exc:
                    logger.debug(f"[EventBroadcaster Async] Listener error: {exc}")
            return

        # Fallback
        try:
            from monika.interfaces.dashboard.routes.common import broadcast_live_event

            await broadcast_live_event(event_type, enriched_payload)
        except ImportError, Exception:
            pass
    except Exception as exc:
        logger.debug(f"[EventBroadcaster Async] Failed emitting {event_type}: {exc}")
