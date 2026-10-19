# ==============================================================================
# File: application/agent/chat/pending_actions.py
# ==============================================================================

"""
PendingAction data structure for human-in-the-loop action proposals.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional


class PendingAction:
    """Menyimpan usulan aksi yang menunggu konfirmasi user."""

    def __init__(self, action_id: str, action_type: str, params: dict, description: str, is_persisted: bool = False):
        self.action_id = action_id
        self.action_type = action_type  # "place_order" | "close_position" | "pause" | "resume"
        self.params = params
        self.description = description
        self.is_persisted = is_persisted
        self.created_at = datetime.now(timezone.utc)
        self.expires_at = self.created_at + timedelta(seconds=90)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def to_dict(self) -> dict:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "params": self.params,
            "description": self.description,
            "is_persisted": self.is_persisted,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PendingAction":
        obj = cls(
            action_id=d["action_id"],
            action_type=d["action_type"],
            params=d.get("params", {}),
            description=d.get("description", ""),
            is_persisted=d.get("is_persisted", False),
        )
        if "created_at" in d and d["created_at"]:
            try:
                obj.created_at = datetime.fromisoformat(d["created_at"])
            except Exception:
                pass
        if "expires_at" in d and d["expires_at"]:
            try:
                obj.expires_at = datetime.fromisoformat(d["expires_at"])
            except Exception:
                pass
        return obj
