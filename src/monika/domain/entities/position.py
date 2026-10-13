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
    partially_filled: bool = False
    opened_at: datetime = Field(default_factory=clock.now)
    closed_at: Optional[datetime] = None
    status: str = "open"  # open, closed
    pnl: Optional[float] = None
    is_paper: bool = False
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
        return cls.model_validate(obj, from_attributes=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a plain dictionary."""
        return self.model_dump()
