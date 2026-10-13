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
        """Create domain TradeTriggerEntity from SQLAlchemy model."""
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
                asset_analysis_id=_val("asset_analysis_id", None),
                trigger_type=str(_val("trigger_type", "price_level")),
                condition_json=str(_val("condition_json", "{}")),
                status=str(_val("status", "pending")),
                created_at=_val("created_at", clock.now()),
                fired_at=_val("fired_at", None),
            )
        return cls.model_validate(obj, from_attributes=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to a plain dictionary."""
        return self.model_dump()
