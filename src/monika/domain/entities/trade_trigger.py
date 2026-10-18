# ==============================================================================
# File: domain/entities/trade_trigger.py
# ==============================================================================

"""
Trade Trigger Domain Entity.

Pure domain representation of conditional trade triggers and rules,
decoupled from database persistence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

import monika.core.primitives.clock as clock


class TradeTriggerEntity(BaseModel):
    """Pure domain entity representing a conditional trade trigger."""

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    id: Optional[int] = None
    asset_analysis_id: Optional[int] = None
    trigger_type: str  # price_level, indicator, time, news
    condition_json: str
    status: str = "pending"  # pending, fired, cancelled
    created_at: datetime = Field(default_factory=clock.now)
    fired_at: Optional[datetime] = None

    @classmethod
    def from_orm(cls, obj: Any) -> TradeTriggerEntity:
        """Create domain TradeTriggerEntity from ORM model or compatible object."""
        if isinstance(obj, cls):
            return obj
        return cls.model_validate(obj, from_attributes=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a plain dictionary."""
        return self.model_dump()
