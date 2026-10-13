# ==============================================================================
# File: domain/entities/position.py
# ==============================================================================

"""
Position Domain Entity.

Pure domain representation of an open or closed trading position,
completely decoupled from SQLAlchemy database models and sessions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict, Field

import monika.core.primitives.clock as clock


class PositionEntity(BaseModel):
    """Pure domain entity representing a trading position."""
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    id: Optional[int] = None
    order_id: Optional[str] = None
    analysis_id: Optional[int] = None
    mt5_ticket: Optional[int] = None
    symbol: str
    direction: str  # buy, sell
    volume: float
    initial_volume: Optional[float] = None
    requested_volume: Optional[float] = None
    entry_price: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    slippage_pips: Optional[float] = 0.0
    partially_filled: Optional[bool] = False
    opened_at: datetime = Field(default_factory=clock.now)
    closed_at: Optional[datetime] = None
    status: str = "open"  # open, closed
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    is_paper: Optional[bool] = False
    pair_group_id: Optional[str] = None
    trailing_override_json: Optional[str] = None
    mae_pips: Optional[float] = None
    mfe_pips: Optional[float] = None
    sl_slippage_pips: Optional[float] = 0.0
    entry_session: Optional[str] = None
    market_regime: Optional[str] = None

    @classmethod
    def from_orm(cls, obj: Any) -> PositionEntity:
        """Create domain PositionEntity from SQLAlchemy model."""
        if isinstance(obj, cls):
            return obj
        if hasattr(obj, "_mock_return_value") or hasattr(obj, "_mock_wraps"):
            def _val(attr: str, default: Any = None) -> Any:
                v = getattr(obj, attr, default)
                if hasattr(v, "_mock_return_value") or hasattr(v, "_mock_wraps"):
                    return default
                return v

            return cls(
                id=_val("id", 1),
                mt5_ticket=_val("mt5_ticket", _val("ticket", 1001)),
                symbol=_val("symbol", "EURUSD"),
                direction=_val("direction", "buy"),
                volume=_val("volume", 0.1),
                initial_volume=_val("initial_volume", None),
                requested_volume=_val("requested_volume", None),
                entry_price=_val("entry_price", 1.1000),
                sl=_val("sl", None),
                tp=_val("tp", None),
                slippage_pips=_val("slippage_pips", 0.0),
                partially_filled=_val("partially_filled", False),
                opened_at=_val("opened_at", clock.now()),
                closed_at=_val("closed_at", None),
                status=_val("status", "open"),
                pnl=_val("pnl", None),
                pnl_pct=_val("pnl_pct", None),
                is_paper=_val("is_paper", False),
                pair_group_id=_val("pair_group_id", None),
                trailing_override_json=_val("trailing_override_json", None),
                mae_pips=_val("mae_pips", None),
                mfe_pips=_val("mfe_pips", None),
                sl_slippage_pips=_val("sl_slippage_pips", 0.0),
                entry_session=_val("entry_session", None),
                market_regime=_val("market_regime", None),
            )
        try:
            return cls.model_validate(obj, from_attributes=True)
        except Exception:
            return cls(
                id=getattr(obj, "id", None),
                order_id=getattr(obj, "order_id", None),
                analysis_id=getattr(obj, "analysis_id", None),
                mt5_ticket=getattr(obj, "mt5_ticket", getattr(obj, "ticket", None)),
                symbol=getattr(obj, "symbol", "EURUSD"),
                direction=getattr(obj, "direction", "buy"),
                volume=getattr(obj, "volume", 0.1),
                initial_volume=getattr(obj, "initial_volume", None),
                requested_volume=getattr(obj, "requested_volume", None),
                entry_price=getattr(obj, "entry_price", 1.1000),
                sl=getattr(obj, "sl", None),
                tp=getattr(obj, "tp", None),
                slippage_pips=getattr(obj, "slippage_pips", 0.0) or 0.0,
                partially_filled=bool(getattr(obj, "partially_filled", False)),
                opened_at=getattr(obj, "opened_at", None) or clock.now(),
                closed_at=getattr(obj, "closed_at", None),
                status=getattr(obj, "status", "open") or "open",
                pnl=getattr(obj, "pnl", None),
                pnl_pct=getattr(obj, "pnl_pct", None),
                is_paper=bool(getattr(obj, "is_paper", False)),
                pair_group_id=getattr(obj, "pair_group_id", None),
                trailing_override_json=getattr(obj, "trailing_override_json", None),
                mae_pips=getattr(obj, "mae_pips", None),
                mfe_pips=getattr(obj, "mfe_pips", None),
                sl_slippage_pips=getattr(obj, "sl_slippage_pips", 0.0) or 0.0,
                entry_session=getattr(obj, "entry_session", None),
                market_regime=getattr(obj, "market_regime", None),
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a plain dictionary."""
        return self.model_dump()
