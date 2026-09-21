"""
Unit tests for Monotonic TradingCycleEventLog (Phase 7.1), Provenance Lineage (Phase 7.2),
and Operator Feedback Capture (Phase 7.5).
"""

import tempfile
from pathlib import Path
import pytest
from logging_observability.trading_cycle_event_log import (
    TradingCycleEventLog,
    CycleEventType,
)
from logging_observability.operator_feedback import OperatorFeedbackManager


def test_monotonic_cycle_event_log_and_lineage():
    with tempfile.TemporaryDirectory() as tmp_dir:
        log = TradingCycleEventLog(storage_dir=Path(tmp_dir))
        cid = "cycle_2026_09_22_001"

        # 1. Cycle Start (seq 1)
        ev1 = log.record_event(cid, CycleEventType.CYCLE_START, {"status": "started"})
        assert ev1.seq == 1

        # 2. Fundamental Stage signal (seq 2, parent: 1)
        ev2 = log.record_event(
            cid,
            CycleEventType.STAGE_FUNDAMENTAL,
            {"macro_bias": "hawkish_usd"},
            source_event_seqs=[ev1.seq],
        )
        assert ev2.seq == 2

        # 3. Per Asset analysis (seq 3, parent: 2)
        ev3 = log.record_event(
            cid,
            CycleEventType.STAGE_PER_ASSET,
            {"symbol": "EURUSD", "signal": "bearish_ob"},
            source_event_seqs=[ev2.seq],
        )
        assert ev3.seq == 3

        # 4. Debate conclusion (seq 4, parent: 3)
        ev4 = log.record_event(
            cid,
            CycleEventType.STAGE_DEBATE,
            {"winner": "bear", "confidence": 0.85},
            source_event_seqs=[ev3.seq],
        )
        assert ev4.seq == 4

        # 5. Order Dispatch (seq 5, parent: 4)
        ev5 = log.record_event(
            cid,
            CycleEventType.ORDER_DISPATCH,
            {"symbol": "EURUSD", "action": "sell", "lot": 0.1},
            source_event_seqs=[ev4.seq],
        )
        assert ev5.seq == 5

        # Verify contiguous sequence
        events = log.get_events_for_cycle(cid)
        assert len(events) == 5
        assert [e.seq for e in events] == [1, 2, 3, 4, 5]

        # Verify Provenance Lineage: Tracing Order Dispatch (seq 5) back to origin
        lineage = log.trace_decision_lineage(cid, target_seq=5)
        lineage_seqs = [e.seq for e in lineage]
        assert lineage_seqs == [1, 2, 3, 4, 5]

        # Reconstruct cycle summary
        recon = log.reconstruct_cycle(cid)
        assert recon["total_events"] == 5


def test_operator_feedback_capture():
    mgr = OperatorFeedbackManager()
    fb = mgr.submit_feedback(
        cycle_id="cycle_100",
        rating=5,
        category="accurate_thesis",
        note="Model correctly anticipated Asian high sweep and did not chase chop.",
        operator_id="admin_01",
        symbol="XAUUSD",
        target_event_seq=3,
    )

    assert fb.rating == 5
    assert fb.category == "accurate_thesis"
    assert fb.operator_id == "admin_01"

    feedback_list = mgr.get_feedback_for_cycle("cycle_100")
    assert len(feedback_list) == 1
    assert feedback_list[0].feedback_id == fb.feedback_id

    # Invalid rating bounds
    with pytest.raises(ValueError):
        mgr.submit_feedback(cycle_id="cycle_100", rating=6, category="bad", note="out of bounds")
