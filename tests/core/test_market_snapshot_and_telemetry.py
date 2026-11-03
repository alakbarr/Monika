# ==============================================================================
# File: tests/core/test_market_snapshot_and_telemetry.py
# Description: Tests for MarketSnapshotService, VerifiedMarketSnapshot & BatchedTelemetrySink.
# ==============================================================================

import asyncio
from datetime import datetime, timezone
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.validators.market_snapshot import VerifiedMarketSnapshot
from monika.application.services.market_snapshot_service import (
    AssetMarketSnapshot,
    MarketSnapshotService,
)
from monika.core.telemetry.batched_sink import (
    BatchedTelemetrySink,
    disable_batched_telemetry,
    enable_batched_telemetry,
)


@pytest.fixture(autouse=True)
def cleanup_services():
    MarketSnapshotService.reset()
    yield
    MarketSnapshotService.reset()


def test_market_snapshot_service_crud():
    service = MarketSnapshotService.get_instance()
    now = datetime.now(timezone.utc)

    snap = service.set_snapshot(
        symbol="EURUSD",
        timeframe="H1",
        timestamp=now,
        open_=1.0850,
        high=1.0890,
        low=1.0840,
        close=1.0880,
        volume=12500.0,
        indicators={"rsi_14": 55.4, "atr_14": 0.0035},
    )

    assert snap.symbol == "EURUSD"
    assert snap.timeframe == "H1"
    assert snap.is_fresh(max_age_seconds=10.0) is True

    # Retrieve
    retrieved = service.get_snapshot("EURUSD", "H1", max_age_seconds=10.0)
    assert retrieved is not None
    assert retrieved.close == 1.0880
    assert retrieved.indicators["rsi_14"] == 55.4

    # Miss on unknown timeframe
    assert service.get_snapshot("EURUSD", "M15") is None

    # Clear
    assert service.clear() == 1
    assert service.get_snapshot("EURUSD", "H1") is None


@pytest.mark.asyncio
async def test_verified_market_snapshot_memory_hit():
    service = MarketSnapshotService.get_instance()
    now = datetime.now(timezone.utc)

    service.set_snapshot(
        symbol="XAUUSD",
        timeframe="H1",
        timestamp=now,
        open_=2650.0,
        high=2665.0,
        low=2645.0,
        close=2660.0,
        volume=8400.0,
        indicators={"rsi_14": 62.1},
    )

    vms = VerifiedMarketSnapshot()

    class DummySession(AsyncSession):
        def __init__(self):
            pass

        async def execute(self, *args, **kwargs):
            raise AssertionError("Database query was executed despite memory snapshot hit!")

    session_inst = DummySession()
    res = await vms.compute("XAUUSD", session_inst, as_of=None, timeframe="H1")
    assert res["symbol"] == "XAUUSD"
    assert res["latest_close"] == 2660.0
    assert res["latest_high"] == 2665.0
    assert res["rsi_14"] == 62.1
    assert res["_ground_truth"] is True


@pytest.mark.asyncio
async def test_batched_telemetry_sink_dual_lane():
    sink = BatchedTelemetrySink(flush_interval_seconds=60.0, max_batch_size=10, max_queue_size=50)

    # 1. Routine event -> queued without direct flush
    await sink.persist_activity("scraping", "Scraped Bloomberg news item", actor="news_scraper")
    assert sink._queue.qsize() == 1

    await sink.persist_activity("system", "Healthcheck heartbeat OK", actor="daemon")
    assert sink._queue.qsize() == 2

    # Verify queue items
    assert not sink._queue.empty()


@pytest.mark.asyncio
async def test_enable_disable_batched_telemetry():
    sink = enable_batched_telemetry(flush_interval_seconds=0.1)
    assert sink is not None
    assert sink._running is True

    await disable_batched_telemetry()
    assert sink._running is False
