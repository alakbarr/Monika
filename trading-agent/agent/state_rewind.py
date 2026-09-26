# ==============================================================================
# File: agent/state_rewind.py
# ==============================================================================

"""
Carrier-Aware State Rewind & Conversation Undo (/undo).
Institutional-grade engine turn protection architecture.

Enables rolling back conversation turns (/undo) while respecting the
Two-Plane Fortress financial invariant: conversations can be rolled back,
but physical financial side-effects (MT5 orders placed or deals closed)
must never be ghost-deleted from audit history.
Instead, they are marked as CARRIER_SIDE_EFFECT_PERSISTED.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from database.session_db_wal import SessionDbWal

logger = logging.getLogger("TradingAgent.Agent.StateRewind")

CARRIER_SIDE_EFFECT_PERSISTED = "[CARRIER_SIDE_EFFECT_PERSISTED: Real broker transactions executed during this turn remain logged in MT5 and trade records]"


class RewindTargetUnavailableError(ValueError):
    """Raised when the specified user turn is invalid or not in history."""
    pass


@dataclass
class RewindOutcome:
    active_prefix: List[Dict[str, Any]]
    rewound_user_turn: Optional[Dict[str, Any]]
    undone_count: int
    carrier_side_effect_persisted: bool
    status_message: str


class StateRewindManager:
    """Manages transactional turn rollback with financial side-effect awareness."""

    def __init__(self, db: SessionDbWal):
        self.db = db

    def rewind_session(
        self,
        session_id: str,
        user_ordinal: int = -1,
        warm_history: Optional[List[Dict[str, Any]]] = None,
    ) -> RewindOutcome:
        """
        Rewind conversation state to just before the target user turn.
        
        Args:
            session_id: Identifier of the active session.
            user_ordinal: Index of user turn (0 = oldest, -1 = most recent user turn).
            warm_history: Optional in-memory transcript view.
        """
        conn = self.db.get_connection()
        messages = self.db.get_messages(session_id)

        user_turn_indices = [
            i for i, m in enumerate(messages) if m.get("role") == "user"
        ]

        if not user_turn_indices:
            raise RewindTargetUnavailableError("No user turns found in session history to rewind.")

        if user_ordinal < 0:
            target_idx = max(0, len(user_turn_indices) + user_ordinal)
        else:
            target_idx = min(user_ordinal, len(user_turn_indices) - 1)

        if target_idx >= len(user_turn_indices):
            raise RewindTargetUnavailableError("Target user turn is beyond the history boundary.")

        msg_split_idx = user_turn_indices[target_idx]
        target_message = messages[msg_split_idx]
        target_turn_ordinal = target_message.get("turn_ordinal", 0)

        # Check for financial side-effects in this turn or subsequent turns
        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM tool_records
            WHERE session_id = ? AND turn_ordinal >= ? AND has_side_effects = 1;
        """, (session_id, target_turn_ordinal))
        row = cursor.fetchone()
        has_financial_side_effects = bool(row and row["count"] > 0)

        # Compute active prefix
        active_prefix = messages[:msg_split_idx]
        undone_count = len(messages) - msg_split_idx

        with conn:
            if has_financial_side_effects:
                # Mark as carrier preserved instead of outright deletion
                conn.execute("""
                    UPDATE session_messages 
                    SET carrier_marker = ?
                    WHERE session_id = ? AND turn_ordinal >= ?;
                """, (CARRIER_SIDE_EFFECT_PERSISTED, session_id, target_turn_ordinal))
                logger.warning(
                    f"[StateRewind] Session '{session_id}' turn {target_turn_ordinal} rewound, "
                    f"but retained with {CARRIER_SIDE_EFFECT_PERSISTED} marker due to financial transactions."
                )
                status_msg = (
                    f"Turn #{target_turn_ordinal} successfully rewound. "
                    "Note: Financial transactions executed during this turn remain permanently recorded."
                )
            else:
                # Safe to prune conversation rows
                conn.execute("""
                    DELETE FROM session_messages
                    WHERE session_id = ? AND row_id >= ?;
                """, (session_id, target_message["row_id"]))
                status_msg = f"Turn #{target_turn_ordinal} ({undone_count} messages) successfully undone."

        return RewindOutcome(
            active_prefix=active_prefix,
            rewound_user_turn=target_message,
            undone_count=undone_count,
            carrier_side_effect_persisted=has_financial_side_effects,
            status_message=status_msg,
        )
