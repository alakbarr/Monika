# ==============================================================================
# File: logging_observability/dashboard/routes/common.py
# Description: Shared State, Models, and Dependencies for Dashboard Routes
# ==============================================================================

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import WebSocket
from collections import deque
from pydantic import BaseModel, Field

logger = logging.getLogger("TradingAgent.DashboardAPI.Routes")

_start_time = time.time()
_dependencies: Dict[str, Any] = {}
_active_websockets: set[WebSocket] = set()

# WebSocket Monotonic Sequence Watermark & Replay Buffer (Phase 7.3)
_stream_seq: int = 0
_live_event_buffer: deque = deque(maxlen=500)


def get_current_stream_seq() -> int:
    """Return latest monotonic WebSocket event sequence number."""
    return _stream_seq


def get_buffered_events_since(since_seq: int) -> List[dict]:
    """Retrieve buffered events strictly newer than since_seq for reconnect replay."""
    return [ev for ev in list(_live_event_buffer) if ev.get("seq", 0) > since_seq]


def record_stream_event(message: dict) -> dict:
    """Stamp message with monotonic seq and as_of_seq and append to ring buffer."""
    global _stream_seq
    _stream_seq += 1
    message["seq"] = _stream_seq
    message["as_of_seq"] = _stream_seq
    _live_event_buffer.append(dict(message))
    return message


def set_dashboard_dependencies(**kwargs) -> None:
    """Register runtime agent dependencies for interactive dashboard endpoints."""
    _dependencies.update(kwargs)


def get_dashboard_dependency(name: str) -> Optional[Any]:
    """Retrieve runtime agent dependency by name."""
    return _dependencies.get(name)


def _safe_json(raw: Optional[str]) -> Any:
    """Parse JSON text safely (return raw text on parse error, None on None)."""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return raw


async def broadcast_live_event(event_type: str, payload: dict) -> None:
    """Broadcast an event to all connected dashboard live-feed WebSockets with monotonic sequence."""
    if not _active_websockets:
        # Still record into buffer even without active subscribers for future reconnects
        msg = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        record_stream_event(msg)
        return

    message = {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    record_stream_event(message)

    dead = []
    for ws in list(_active_websockets):
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _active_websockets.discard(ws)


class TriggerCycleRequest(BaseModel):
    forced: bool = Field(default=True, description="Force execution even if scheduled time hasn't arrived")
    reason: str = Field(default="Manual trigger from Dashboard", description="Reason for triggering cycle")
    symbol: Optional[str] = Field(default=None, description="Optional target symbol for ad-hoc analysis")
    context: Optional[str] = Field(default=None, description="Ad-hoc context or specific hypothesis to analyze")


class OverrideRiskRequest(BaseModel):
    risk_percent_per_trade: Optional[float] = Field(default=None, ge=0.1, le=5.0, description="Risk percent per trade (e.g. 0.1 - 5.0)")
    max_daily_drawdown_percent: Optional[float] = Field(default=None, ge=0.5, le=20.0, description="Max daily drawdown limit in % (e.g. 0.5 - 20.0)")
    max_weekly_drawdown_percent: Optional[float] = Field(default=None, description="Max weekly drawdown limit in %")
    max_concurrent_positions: Optional[int] = Field(default=None, description="Max open concurrent positions")
    max_lot_per_symbol: Optional[float] = Field(default=None, description="Max lot size per symbol")
    custom_overrides: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary additional risk parameters")
    max_risk_amount_usd: Optional[float] = Field(None, ge=10.0, le=50000.0)
    auto_execute: Optional[bool] = None
    system_paused: Optional[bool] = None
    reason: Optional[str] = Field(None, description="Audit reason for risk override")


class ClosePositionRequest(BaseModel):
    ticket: Optional[int] = Field(default=None, description="MT5 deal/order ticket number")
    position_id: Optional[int] = Field(default=None, description="Database Position record ID")
    paper_trade_id: Optional[int] = Field(default=None, description="PaperTradeRecord ID")
    symbol: Optional[str] = Field(default=None, description="Currency symbol")
    reason: str = Field(default="Manual close from Dashboard", description="Closure reason")


class SteerRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Steering instruction or tactical directive for analysis cycle")
    mode: Optional[str] = Field(default="steer", description="Delivery mode ('steer' or 'follow_up')")
    symbols: Optional[List[str]] = Field(default=None, description="Optional target symbols affected")


TriggerCycleRequest.model_rebuild()
OverrideRiskRequest.model_rebuild()
ClosePositionRequest.model_rebuild()
SteerRequest.model_rebuild()


def _get_settings_path() -> str:
    """Resolve absolute path to settings.yaml."""
    candidates = [
        os.getenv("SETTINGS_PATH"),
        "config/settings.yaml",
        "trading-agent/config/settings.yaml",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "config", "settings.yaml"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return os.path.abspath("config/settings.yaml")
