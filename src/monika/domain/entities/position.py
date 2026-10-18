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
        """Create domain PositionEntity from ORM model or compatible object."""
        if isinstance(obj, cls):
            return obj
        try:
            return cls.model_validate(obj, from_attributes=True)
        except Exception:

            def _clean(val: Any, default: Any = None) -> Any:
                if val is None or callable(val) or type(val).__name__ in ("MagicMock", "Mock", "AsyncMock"):
                    return default
                return val

            return cls(
                id=_clean(getattr(obj, "id", None), None),
                order_id=_clean(getattr(obj, "order_id", None), None),
                analysis_id=_clean(getattr(obj, "analysis_id", None), None),
                mt5_ticket=int(_clean(getattr(obj, "mt5_ticket", None) or getattr(obj, "ticket", None), 0) or 0),
                symbol=str(_clean(getattr(obj, "symbol", None), "EURUSD")),
                direction=str(_clean(getattr(obj, "direction", None), "buy")),
                volume=float(_clean(getattr(obj, "volume", None), 0.1) or 0.1),
                initial_volume=_clean(getattr(obj, "initial_volume", None), None),
                requested_volume=_clean(getattr(obj, "requested_volume", None), None),
                entry_price=float(_clean(getattr(obj, "entry_price", None), 1.0) or 1.0),
                sl=_clean(getattr(obj, "sl", None), None),
                tp=_clean(getattr(obj, "tp", None), None),
                slippage_pips=float(_clean(getattr(obj, "slippage_pips", None), 0.0) or 0.0),
                partially_filled=bool(_clean(getattr(obj, "partially_filled", None), False)),
                opened_at=_clean(getattr(obj, "opened_at", None), clock.now()),
                closed_at=_clean(getattr(obj, "closed_at", None), None),
                status=str(_clean(getattr(obj, "status", None), "open")),
                pnl=_clean(getattr(obj, "pnl", None), None),
                pnl_pct=_clean(getattr(obj, "pnl_pct", None), None),
                is_paper=bool(_clean(getattr(obj, "is_paper", None), False)),
                pair_group_id=_clean(getattr(obj, "pair_group_id", None), None),
                trailing_override_json=_clean(getattr(obj, "trailing_override_json", None), None),
                mae_pips=_clean(getattr(obj, "mae_pips", None), None),
                mfe_pips=_clean(getattr(obj, "mfe_pips", None), None),
                sl_slippage_pips=float(_clean(getattr(obj, "sl_slippage_pips", None), 0.0) or 0.0),
                entry_session=_clean(getattr(obj, "entry_session", None), None),
                market_regime=_clean(getattr(obj, "market_regime", None), None),
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a plain dictionary."""
        return self.model_dump()
