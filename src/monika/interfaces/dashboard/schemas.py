# ==============================================================================
# File: interfaces/dashboard/schemas.py
# Description: Canonical Pydantic Response and Request Models for Dashboard API
# ==============================================================================

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """Base schema with permissive attributes and camel/snake flexibility."""
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class PingResponse(BaseSchema):
    status: str = Field(default="pong")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ActionStatusResponse(BaseSchema):
    status: str = Field(..., description="Action outcome: ok, success, error, or killed")
    message: str = Field(default="", description="Descriptive outcome message")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Optional extra execution details")


class AuthRoleResponse(BaseSchema):
    role: str = Field(default="viewer", description="Active RBAC role")
    authenticated: bool = Field(default=False)
    is_localhost: bool = Field(default=True)
    username: Optional[str] = Field(default=None)


class HealthDiagnostics(BaseSchema):
    python_version: str = ""
    disk_usage_gb: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    active_threads: int = 0
    active_tasks: int = 0


class HealthStatusResponse(BaseSchema):
    status: str = Field(default="ok")
    uptime_seconds: float = Field(default=0.0)
    db_connected: bool = Field(default=True)
    mt5_connected: bool = Field(default=True)
    heartbeat_age_seconds: Optional[float] = None
    last_scraper_run: Optional[str] = None
    last_analysis_cycle: Optional[str] = None
    gemini_api_available: bool = Field(default=True)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    diagnostics: Optional[HealthDiagnostics] = None


class OverviewResponse(BaseSchema):
    agent_status: str = Field(default="active")
    open_positions_count: int = Field(default=0)
    daily_pnl: float = Field(default=0.0)
    daily_pnl_pct: Optional[float] = None
    current_drawdown: float = Field(default=0.0)
    drawdown_pct: Optional[float] = None
    trading_paused: bool = Field(default=False)
    pause_reason: Optional[str] = None
    vix: Optional[float] = None
    vix_date: Optional[str] = None
    last_analysis_at: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_live: Optional[bool] = False
    is_paper: Optional[bool] = True


class PositionItem(BaseSchema):
    id: int
    mt5_ticket: Optional[int] = None
    symbol: str
    direction: str
    volume: float
    entry_price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    status: str = "open"
    pnl: Optional[float] = None
    current_price: Optional[float] = None
    floating_pnl: Optional[float] = None
    is_paper: Optional[bool] = True


class OrderLogItem(BaseSchema):
    id: int
    ticket: Optional[int] = None
    symbol: str
    order_type: str = "buy"
    volume: float = 0.01
    price: float = 0.0
    sl: Optional[float] = None
    tp: Optional[float] = None
    status: str = "filled"
    created_at: Optional[str] = None


class RiskScorecardResponse(BaseSchema):
    symbol: str = "EURUSD"
    composite_score: float = 0.0
    risk_level: str = "normal"
    metrics: Dict[str, Any] = Field(default_factory=dict)


class ConfigSettingsResponse(BaseSchema):
    settings: Dict[str, Any] = Field(default_factory=dict)
    active_profile: Optional[str] = None
    updated_at: Optional[str] = None


class ConfigUpdateResponse(BaseSchema):
    status: str = "ok"
    message: str = "Configuration updated successfully"
    updated_keys: List[str] = Field(default_factory=list)


class WsTicketResponse(BaseSchema):
    status: str = "ok"
    ticket: str
    expires_in_seconds: int = 60
    role: str = "viewer"


class CalendarEventItem(BaseSchema):
    id: int
    title: str
    country: str
    impact: str = "HIGH"
    scheduled_at: str
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None


class ClassifiedNewsItem(BaseSchema):
    id: int
    title: str
    source: Optional[str] = None
    impact: str = "HIGH"
    sentiment: Optional[str] = None
    published_at: str
    summary: Optional[str] = None


class COTReportItem(BaseSchema):
    market_code: str
    market_name: Optional[str] = None
    commercial_net: float = 0.0
    non_commercial_net: float = 0.0
    report_date: str


class DebateOutcomeItem(BaseSchema):
    id: int
    cycle_id: str
    symbol: str
    verdict: str
    confidence: float = 0.0
    created_at: str


class MT5SignalItem(BaseSchema):
    id: Optional[int] = None
    symbol: str
    timeframe: str = "H1"
    indicator: str
    signal: str
    timestamp: str


class TradeTriggerItem(BaseSchema):
    id: int
    symbol: str
    trigger_type: str
    status: str
    reason: str
    created_at: str


class TokenSummaryResponse(BaseSchema):
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    period_hours: int = 24
