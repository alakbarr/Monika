"""The isolated backtest harness must emulate the database faithfully.

Before this fix the slice session answered queries with candle rows where the
database would return floats or tuples, and the simulation swallowed every
exception. Strategies that were broken in the harness therefore looked like
strategies without an edge, and could never be promoted.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from monika.application.analysis.strategies.base_strategy import CandleDict, EdgeSignal, EdgeStrategy
from monika.application.backtest.isolated_strategy_harness import (
    IsolatedStrategyBacktestHarness,
    ZeroLookaheadSliceSession,
    resample_candles,
)
from monika.infrastructure.database.models import OrderBlock, PriceOHLCV

SYMBOL = "EURUSD"
AS_OF = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _candles(count: int = 60) -> list[CandleDict]:
    start = AS_OF - timedelta(hours=count)
    return [
        CandleDict(
            {
                "timestamp": start + timedelta(hours=i),
                "time": start + timedelta(hours=i),
                "open": 1.1000 + i * 0.0001,
                "high": 1.1010 + i * 0.0001,
                "low": 1.0990 + i * 0.0001,
                "close": 1.1005 + i * 0.0001,
                "volume": 100.0 + i,
            }
        )
        for i in range(count)
    ]


def _session(candles=None) -> ZeroLookaheadSliceSession:
    candles = candles if candles is not None else _candles()
    cache = {
        (SYMBOL, "H1"): candles,
        (SYMBOL, "M15"): candles,
        (SYMBOL, "H4"): resample_candles(candles, 4),
        (SYMBOL, "D1"): resample_candles(candles, 24),
    }
    return ZeroLookaheadSliceSession(cache, as_of_time=AS_OF, symbol=SYMBOL)


@pytest.mark.asyncio
async def test_single_column_close_query_returns_floats():
    session = _session()
    stmt = (
        select(PriceOHLCV.close)
        .where(PriceOHLCV.symbol == SYMBOL, PriceOHLCV.timeframe == "D1")
        .order_by(PriceOHLCV.timestamp.desc())
        .limit(10)
    )
    rows = (await session.execute(stmt)).scalars().all()
    assert rows
    assert all(isinstance(value, float) for value in rows)


@pytest.mark.asyncio
async def test_two_column_query_returns_rows_with_attribute_and_unpack_access():
    session = _session()
    stmt = (
        select(PriceOHLCV.timestamp, PriceOHLCV.close)
        .where(PriceOHLCV.symbol == SYMBOL, PriceOHLCV.timeframe == "H1")
        .order_by(PriceOHLCV.timestamp.desc())
        .limit(10)
    )
    rows = (await session.execute(stmt)).all()
    assert rows
    for row in rows:
        # Database rows support attribute access ...
        assert isinstance(row.close, float)
        assert row.timestamp is not None
        # ... and tuple unpacking.
        timestamp, close = row
        assert timestamp == row.timestamp
        assert close == row.close


@pytest.mark.asyncio
async def test_queries_against_other_tables_return_no_rows():
    session = _session()
    stmt = select(OrderBlock).where(OrderBlock.symbol == SYMBOL)
    rows = (await session.execute(stmt)).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_strategy_settings_reach_the_strategy_configuration():
    settings = {
        "trading": {
            "edge_strategy": {
                "cfg_probe_strategy": {"enabled": True, "min_gap_pips": {"EURUSD": 5}},
            }
        }
    }

    class CfgProbeStrategy(EdgeStrategy):
        strategy_id = "cfg_probe_strategy"

        async def evaluate(self, session, symbol, settings, as_of=None):
            return EdgeSignal(
                self.strategy_id,
                symbol,
                None,
                False,
                0.0,
                rationale=f"cfg={self.cfg.get('min_gap_pips')}",
            )

    harness = IsolatedStrategyBacktestHarness(strategy_cls=CfgProbeStrategy, symbol=SYMBOL, settings=settings)
    instance = harness._get_strategy_instance()
    assert instance.cfg.get("min_gap_pips") == {"EURUSD": 5}


@pytest.mark.asyncio
async def test_evaluation_errors_are_reported_instead_of_swallowed():
    class BrokenStrategy(EdgeStrategy):
        strategy_id = "broken_probe_strategy"

        async def evaluate(self, session, symbol, settings, as_of=None):
            raise RuntimeError("probe failure")

    harness = IsolatedStrategyBacktestHarness(strategy_cls=BrokenStrategy, symbol=SYMBOL)
    metrics = await harness.run_simulation(session=_session(), lookback_candles=120)
    assert metrics.evaluation_errors > 0
    assert metrics.is_evaluable is False
    assert any("probe failure" in sample for sample in metrics.error_samples)


@pytest.mark.asyncio
async def test_strategy_without_errors_is_evaluable():
    class HealthyStrategy(EdgeStrategy):
        strategy_id = "healthy_probe_strategy"

        async def evaluate(self, session, symbol, settings, as_of=None):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="no setup")

    harness = IsolatedStrategyBacktestHarness(strategy_cls=HealthyStrategy, symbol=SYMBOL)
    metrics = await harness.run_simulation(session=_session(), lookback_candles=120)
    assert metrics.evaluation_errors == 0
    assert metrics.is_evaluable is True
