# ==============================================================================
# File: domain/entities/snapshots.py
# ==============================================================================

"""
Domain Value Objects & Snapshots for Risk and Portfolio Evaluation.

Pure domain data structures used by RiskGate, position sizers, and
portfolio monitors without coupling to live broker sockets or SQLAlchemy models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

import monika.core.primitives.clock as clock


class AccountSnapshot(BaseModel):
    """Snapshot of account capital, balance, and risk metrics."""

    model_config = ConfigDict(from_attributes=True)

    equity: float
    balance: float
    margin_free: float = 0.0
    leverage: float = 100.0
    currency: str = "USD"
    timestamp: datetime = Field(default_factory=clock.now)

    @property
    def floating_pnl(self) -> float:
        """Unrealized floating profit or loss."""
        return self.equity - self.balance

    @property
    def drawdown_pct(self) -> float:
        """Current equity drawdown percentage relative to balance."""
        if self.balance <= 0.0:
            return 0.0
        if self.equity >= self.balance:
            return 0.0
        return ((self.balance - self.equity) / self.balance) * 100.0


class ActivePositionSnapshot(BaseModel):
    """Standardized snapshot of an active open position."""

    model_config = ConfigDict(from_attributes=True)

    ticket: Optional[int] = None
    id: Optional[Union[int, str]] = None
    symbol: str
    direction: str  # BUY, SELL
    volume: float  # lots
    entry_price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    current_price: Optional[float] = None
    pnl: float = 0.0
    is_paper: bool = False

    @property
    def lots(self) -> float:
        """Alias for volume in lots."""
        return self.volume


class CalendarRiskEvent(BaseModel):
    """High or medium impact macroeconomic event record."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    title: str
    currency: str
    impact: str  # high, medium, low
    event_time: datetime
    forecast: Optional[str] = None
    previous: Optional[str] = None


class CalendarRiskEvents(BaseModel):
    """Collection of upcoming or active calendar risk events."""

    model_config = ConfigDict(from_attributes=True)

    events: List[CalendarRiskEvent] = Field(default_factory=list)
    window_minutes: int = 15

    def is_in_blackout_window(self, symbol: str, current_time: Optional[datetime] = None) -> bool:
        """
        Check if current_time falls within window_minutes of any high-impact event
        affecting base or quote currency of symbol.
        """
        from monika.domain.market.currency_utils import get_symbol_currencies

        now = current_time or clock.now()
        base_curr, quote_curr = get_symbol_currencies(symbol)
        currencies = {base_curr.upper(), quote_curr.upper()} if base_curr and quote_curr else set()

        for evt in self.events:
            if evt.currency.upper() in currencies and evt.impact.lower() in ("high", "critical"):
                diff_seconds = abs((evt.event_time - now).total_seconds())
                if diff_seconds <= (self.window_minutes * 60):
                    return True
        return False


class SymbolExposure(BaseModel):
    """Aggregate exposure metrics across open positions for a symbol."""

    model_config = ConfigDict(from_attributes=True)

    symbol: str
    position_count: int = 0
    net_lots: float = 0.0
    gross_lots: float = 0.0
    total_unrealized_pnl: float = 0.0
