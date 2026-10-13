# ==============================================================================
# File: logging_observability/dashboard/routes/common.py
# Description: Shared State, Models, and Dependencies for Dashboard Routes
# ==============================================================================

import asyncio
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
_client_queues: Dict[WebSocket, asyncio.Queue] = {}

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


def _safe_json(raw: Optional[str], default: Any = None) -> Any:
    """Parse JSON text safely (return default/raw on parse error, default on None)."""
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default if default is not None else raw


async def broadcast_live_event(event_type: str, payload: dict) -> None:
    """Broadcast an event to all connected dashboard live-feed WebSockets non-blockingly via per-client queues."""
    message = {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    record_stream_event(message)

    if not _active_websockets and not _client_queues:
        return

    dead = []
    for ws, q in list(_client_queues.items()):
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning("[Dashboard WS] Client queue full, marking dead")
            dead.append(ws)
        except Exception:
            dead.append(ws)

    # Fallback for any raw websockets without queues
    for ws in list(_active_websockets):
        if ws not in _client_queues:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

    for ws in dead:
        _active_websockets.discard(ws)
        _client_queues.pop(ws, None)
        try:
            await ws.close()
        except Exception:
            pass


try:
    from monika.application.analysis.event_broadcaster import register_event_listener

    register_event_listener(broadcast_live_event)
except Exception:
    pass


class TriggerCycleRequest(BaseModel):
    forced: bool = Field(default=True, description="Force execution even if scheduled time hasn't arrived")
    reason: str = Field(default="Manual trigger from Dashboard", description="Reason for triggering cycle")
    symbol: Optional[str] = Field(default=None, description="Optional target symbol for ad-hoc analysis")
    context: Optional[str] = Field(default=None, description="Ad-hoc context or specific hypothesis to analyze")


class OverrideRiskRequest(BaseModel):
    risk_percent_per_trade: Optional[float] = Field(
        default=None, ge=0.1, le=5.0, description="Risk percent per trade (e.g. 0.1 - 5.0)"
    )
    max_daily_drawdown_percent: Optional[float] = Field(
        default=None, ge=0.5, le=20.0, description="Max daily drawdown limit in % (e.g. 0.5 - 20.0)"
    )
    max_weekly_drawdown_percent: Optional[float] = Field(default=None, description="Max weekly drawdown limit in %")
    max_concurrent_positions: Optional[int] = Field(default=None, description="Max open concurrent positions")
    max_lot_per_symbol: Optional[float] = Field(default=None, description="Max lot size per symbol")
    custom_overrides: Optional[Dict[str, Any]] = Field(default=None, description="Arbitrary additional risk parameters")
    max_risk_amount_usd: Optional[float] = Field(None, ge=10.0, le=50000.0)
    auto_execute: Optional[bool] = None
    system_paused: Optional[bool] = None
    duration_seconds: Optional[int] = Field(default=None, description="TTL duration in seconds before override reverts")
    expires_at: Optional[str] = Field(default=None, description="ISO timestamp when override expires")
    reason: Optional[str] = Field(None, description="Audit reason for risk override")


class ClosePositionRequest(BaseModel):
    ticket: Optional[int] = Field(default=None, description="MT5 deal/order ticket number")
    position_id: Optional[int] = Field(default=None, description="Database Position record ID")
    paper_trade_id: Optional[int] = Field(default=None, description="PaperTradeRecord ID")
    symbol: Optional[str] = Field(default=None, description="Currency symbol")
    volume: Optional[float] = Field(default=None, gt=0.0, description="Partial volume/lots to close")
    percentage: Optional[float] = Field(
        default=None, ge=1.0, le=100.0, description="Percentage of position to close (1-100)"
    )
    reason: str = Field(default="Manual close from Dashboard", description="Closure reason")


class SteerRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Steering instruction or tactical directive for analysis cycle")
    mode: Optional[str] = Field(default="steer", description="Delivery mode ('steer' or 'follow_up')")
    symbols: Optional[List[str]] = Field(default=None, description="Optional target symbols affected")


class ModifyPositionRequest(BaseModel):
    sl: Optional[float] = Field(default=None, description="New stop loss price")
    tp: Optional[float] = Field(default=None, description="New take profit price")
    comment: Optional[str] = Field(default="Mod:dashboard", description="Audit note or comment")


class TrailingOverrideRequest(BaseModel):
    atr_multiplier: Optional[float] = Field(default=None, gt=0.0, description="Trailing stop ATR multiplier (e.g. 1.5)")
    trail_atr_multiple: Optional[float] = Field(default=None, gt=0.0, description="Alias for atr_multiplier")
    breakeven_atr_multiple: Optional[float] = Field(default=None, gt=0.0, description="ATR multiple to trigger BE")
    trailing_pips: Optional[float] = Field(default=None, gt=0.0, description="Fixed trailing distance in pips")
    breakeven_pips: Optional[float] = Field(default=None, gt=0.0, description="Fixed profit in pips to trigger BE")
    enabled: bool = Field(default=True, description="Enable or disable trailing stop")
    reset_to_default: bool = Field(default=False, description="Reset trailing stop to system defaults")


class BulkBreakevenRequest(BaseModel):
    only_profit: bool = Field(default=True, description="Only move positions currently in profit to breakeven")
    symbol: Optional[str] = Field(default=None, description="Optional symbol filter, e.g. EURUSD")


class BatchCloseRequest(BaseModel):
    filter_type: str = Field(default="all", description="'all', 'profit_only', or 'loss_only'")
    symbol: Optional[str] = Field(default=None, description="Optional symbol filter")
    tickets: List[int] = Field(default_factory=list, description="Specific MT5 position tickets to close")
    reason: str = Field(default="Batch close from Dashboard")


class ManualOrderPreviewRequest(BaseModel):
    symbol: str = Field(..., min_length=1, description="Trading instrument symbol")
    direction: str = Field(default="buy", description="'buy' or 'sell'")
    entry_price: Optional[float] = Field(default=None, description="Entry price (or current market price)")
    price: Optional[float] = Field(default=None, description="Alias for entry_price")
    sl: Optional[float] = Field(default=None, description="Stop loss price")
    tp: Optional[float] = Field(default=None, description="Take profit price")
    risk_percent: Optional[float] = Field(default=None, ge=0.1, le=5.0, description="Risk percentage override")
    fixed_lots: Optional[float] = Field(default=None, gt=0.0, description="Fixed lots override")
    volume: Optional[float] = Field(default=None, gt=0.0, description="Alias for fixed_lots")


class ManualOrderSubmitRequest(BaseModel):
    symbol: str = Field(..., min_length=1)
    direction: str = Field(default="buy", description="'buy' or 'sell'")
    order_type: str = Field(
        default="buy", description="'buy', 'sell', 'buy_limit', 'sell_limit', 'buy_stop', 'sell_stop'"
    )
    lots: Optional[float] = Field(default=None, gt=0.0, description="Order volume in lots")
    volume: Optional[float] = Field(default=None, gt=0.0, description="Order volume alias")
    price: Optional[float] = Field(default=None, description="Order execution/limit/stop price")
    sl: Optional[float] = Field(default=None, description="Stop loss price")
    tp: Optional[float] = Field(default=None, description="Take profit price")
    comment: str = Field(default="Manual:Dashboard", description="Order comment")
    is_paper: Optional[bool] = Field(default=None, description="Explicit paper trading toggle")


class DeprecateSkillRequest(BaseModel):
    reason: Optional[str] = Field(default="Operator manual deprecation", description="Reason for deprecating skill")


class CrystallizeSkillRequest(BaseModel):
    symbol: Optional[str] = Field(default=None, description="Optional symbol filter, e.g. EURUSD")


TriggerCycleRequest.model_rebuild()
OverrideRiskRequest.model_rebuild()
ClosePositionRequest.model_rebuild()
SteerRequest.model_rebuild()
ModifyPositionRequest.model_rebuild()
TrailingOverrideRequest.model_rebuild()
BulkBreakevenRequest.model_rebuild()
BatchCloseRequest.model_rebuild()
ManualOrderPreviewRequest.model_rebuild()
ManualOrderSubmitRequest.model_rebuild()
DeprecateSkillRequest.model_rebuild()
CrystallizeSkillRequest.model_rebuild()


def _get_settings_path() -> str:
    """Resolve absolute path to settings.yaml with active profile support."""
    # Check for active profile marker first
    if os.path.exists("profiles/active_profile"):
        try:
            with open("profiles/active_profile", "r", encoding="utf-8") as pf:
                p_name = pf.read().strip()
                if p_name and p_name != "default":
                    cand_cfg = f"profiles/{p_name}/settings.yaml"
                    if os.path.exists(cand_cfg):
                        return os.path.abspath(cand_cfg)
        except Exception:
            pass

    candidates = [
        os.getenv("SETTINGS_PATH"),
        "config/settings.yaml",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "config",
            "settings.yaml",
        ),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return os.path.abspath("config/settings.yaml")
