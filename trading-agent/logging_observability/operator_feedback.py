"""
Operator Feedback Capture (Phase 7.5).
Allows human operators and reviewers to rate, categorize, and annotate trade rationales,
storing feedback events linked directly into the cycle event log for model evaluation and fine-tuning.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from logging_observability.trading_cycle_event_log import (
    get_cycle_event_log,
    CycleEventType,
)

logger = logging.getLogger("TradingAgent.OperatorFeedback")


@dataclass
class AnalysisFeedback:
    feedback_id: str
    cycle_id: str
    rating: int  # 1 (poor) to 5 (excellent)
    category: str  # e.g. "hallucination", "accurate_thesis", "poor_timing", "invalid_sl", "good_setup"
    note: str
    created_at: str
    operator_id: str = "operator"
    symbol: Optional[str] = None
    target_event_seq: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OperatorFeedbackManager:
    """Manages operator feedback capture and persistence."""

    def __init__(self):
        self._feedback_store: List[AnalysisFeedback] = []

    def submit_feedback(
        self,
        cycle_id: str,
        rating: int,
        category: str,
        note: str,
        operator_id: str = "operator",
        symbol: Optional[str] = None,
        target_event_seq: Optional[int] = None,
    ) -> AnalysisFeedback:
        """Record human operator feedback and append it into the cycle event stream."""
        if not (1 <= rating <= 5):
            raise ValueError(f"Rating must be between 1 and 5, got {rating}")

        feedback = AnalysisFeedback(
            feedback_id=f"fb_{uuid.uuid4().hex[:12]}",
            cycle_id=cycle_id,
            rating=rating,
            category=category,
            note=note,
            created_at=datetime.now(timezone.utc).isoformat(),
            operator_id=operator_id,
            symbol=symbol,
            target_event_seq=target_event_seq,
        )
        self._feedback_store.append(feedback)

        # Append to TradingCycleEventLog with lineage link to target event
        event_log = get_cycle_event_log()
        source_seqs = [target_event_seq] if target_event_seq else []
        event_log.record_event(
            cycle_id=cycle_id,
            event_type=CycleEventType.OPERATOR_FEEDBACK,
            payload=feedback.to_dict(),
            source_event_seqs=source_seqs,
        )
        logger.info(
            f"[OperatorFeedback] Recorded feedback {feedback.feedback_id} "
            f"for cycle {cycle_id}: rating={rating}, category={category}"
        )
        return feedback

    def get_feedback_for_cycle(self, cycle_id: str) -> List[AnalysisFeedback]:
        """Return all feedback records for a given cycle."""
        return [fb for fb in self._feedback_store if fb.cycle_id == cycle_id]


# Singleton instance
_default_feedback_mgr: Optional[OperatorFeedbackManager] = None


def get_operator_feedback_manager() -> OperatorFeedbackManager:
    """Singleton getter for OperatorFeedbackManager."""
    global _default_feedback_mgr
    if _default_feedback_mgr is None:
        _default_feedback_mgr = OperatorFeedbackManager()
    return _default_feedback_mgr
