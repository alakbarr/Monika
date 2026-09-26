# ==============================================================================
# File: agent/state_rewind.py
# ==============================================================================

"""
Carrier-Aware State Rewind & Conversation Undo (/undo).
Institutional-grade engine turn protection architecture.

Enforces:
1. Concurrency verification against expected active message IDs.
2. Two-Plane Fortress: financial transactions in MT5/PostgreSQL are permanently retained.
3. Composite Carrier Splitting: preserves handoff compression summaries while rolling back user prompts.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from database.session_db_wal import SessionDbWal

logger = logging.getLogger("TradingAgent.Agent.StateRewind")

CARRIER_SIDE_EFFECT_PERSISTED = (
    "[CARRIER_SIDE_EFFECT_PERSISTED: Real broker transactions executed during this turn remain logged in MT5 and trade records]"
)

_SUMMARY_CARRIER_PATTERN = re.compile(
    r"(\[Summary of earlier conversation.*?\]:[\s\S]*?)(?:\n\n|\Z)",
    re.IGNORECASE,
)


class RewindTargetUnavailableError(ValueError):
    """Raised when the specified user turn is invalid or not in history."""
    pass


class ConcurrencyConflictError(RuntimeError):
    """Raised when the underlying session state changed while awaiting rewind."""
    pass


@dataclass
class RewindOutcome:
    active_prefix: List[Dict[str, Any]]
    rewound_user_turn: Optional[Dict[str, Any]]
    undone_count: int
    carrier_side_effect_persisted: bool
    status_message: str


class StateRewindManager:
    """Manages transactional turn rollback with concurrency fences and financial protection."""

    def __init__(self, db: SessionDbWal):
        self.db = db

    def rewind_session(
        self,
        session_id: str,
        user_ordinal: int = -1,
        expected_active_ids: Optional[List[int]] = None,
        warm_history: Optional[List[Dict[str, Any]]] = None,
    ) -> RewindOutcome:
        """
        Rewind conversation state to just before the target user turn with concurrency checks.
        """
        conn = self.db.get_connection()
        messages = self.db.get_messages(session_id)

        # 1. Concurrency Verification
        current_ids = [m.get("row_id") for m in messages if m.get("row_id") is not None]
        if expected_active_ids is not None:
            if current_ids != expected_active_ids:
                raise ConcurrencyConflictError(
                    f"Session history changed concurrently (expected {len(expected_active_ids)} ids, found {len(current_ids)})."
                )

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

        # 2. Check for financial side-effects
        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM tool_records
            WHERE session_id = ? AND turn_ordinal >= ? AND has_side_effects = 1;
        """, (session_id, target_turn_ordinal))
        row = cursor.fetchone()
        has_financial_side_effects = bool(row and row["count"] > 0)

        # 3. Composite Carrier Splitting: check if target message carries summary handoff
        content = target_message.get("content", "")
        summary_match = _SUMMARY_CARRIER_PATTERN.search(content)
        carrier_summary: Optional[str] = summary_match.group(1).strip() if summary_match else None

        active_prefix = messages[:msg_split_idx]
        undone_count = len(messages) - msg_split_idx

        with conn:
            if has_financial_side_effects:
                # Retain with persistent carrier marker
                conn.execute("""
                    UPDATE session_messages 
                    SET carrier_marker = ?
                    WHERE session_id = ? AND turn_ordinal >= ?;
                """, (CARRIER_SIDE_EFFECT_PERSISTED, session_id, target_turn_ordinal))
                logger.warning(
                    f"[StateRewind] Session '{session_id}' turn {target_turn_ordinal} rewound with persistent carrier."
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

                # If the target message had an embedded summary scaffold, re-insert it as a pure summary
                if carrier_summary:
                    conn.execute("""
                        INSERT INTO session_messages (session_id, role, content, turn_ordinal, created_at)
                        VALUES (?, 'system', ?, ?, CURRENT_TIMESTAMP);
                    """, (session_id, carrier_summary, target_turn_ordinal))
                    active_prefix.append({"role": "system", "content": carrier_summary})
                    logger.info(f"[StateRewind] Preserved composite compaction summary during rewind for {session_id}")

                status_msg = f"Turn #{target_turn_ordinal} ({undone_count} messages) successfully undone."

        return RewindOutcome(
            active_prefix=active_prefix,
            rewound_user_turn=target_message,
            undone_count=undone_count,
            carrier_side_effect_persisted=has_financial_side_effects,
            status_message=status_msg,
        )
