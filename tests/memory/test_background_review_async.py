"""
Unit tests for async background review and ReadBeforeWriteGuard.
"""

import asyncio
import pytest
from pathlib import Path
from analysis.memory.background_review import BackgroundReviewEngine
from analysis.memory.skill_crystallizer import ReadBeforeWriteGuard


@pytest.mark.asyncio
async def test_background_review_filters_transient_errors():
    engine = BackgroundReviewEngine()
    engine.start()

    try:
        # Schedule transient error trade outcome
        transient_outcome = {
            "ticket": 1001,
            "symbol": "XAUUSD",
            "profit_loss": -50.0,
            "close_reason": "broker_connection_lost",
        }

        enqueued = await engine.schedule_review(transient_outcome)
        assert enqueued is True

        # Wait for processing
        await asyncio.sleep(0.1)

        # Must be discarded, not processed
        assert engine.discarded_count == 1
        assert engine.processed_count == 0
    finally:
        await engine.stop()


@pytest.mark.asyncio
async def test_background_review_processes_valid_trade():
    class DummyReflector:
        def __init__(self):
            self.called = False
        async def reflect_on_trade(self, outcome):
            self.called = True
            return {"status": "ok"}

    reflector = DummyReflector()
    engine = BackgroundReviewEngine(reflector=reflector)
    engine.start()

    try:
        valid_outcome = {
            "ticket": 1002,
            "symbol": "EURUSD",
            "profit_loss": 120.0,
            "close_reason": "take_profit_hit",
        }

        enqueued = await engine.schedule_review(valid_outcome)
        assert enqueued is True

        await asyncio.sleep(0.1)
        assert engine.processed_count == 1
        assert reflector.called is True
    finally:
        await engine.stop()


def test_read_before_write_guard(tmp_path: Path):
    guard = ReadBeforeWriteGuard()
    skill_file = tmp_path / "skill_test.md"

    # Non-existent file can be written without prior inspection
    assert guard.can_write(skill_file) is True

    # Now create file on disk
    skill_file.write_text("# Old Content\n", encoding="utf-8")

    # Guard should now block if not inspected
    guard_fresh = ReadBeforeWriteGuard()
    assert guard_fresh.can_write(skill_file) is False

    # Read/inspect -> now can write
    content = guard_fresh.inspect_and_read(skill_file)
    assert content == "# Old Content\n"
    assert guard_fresh.can_write(skill_file) is True
