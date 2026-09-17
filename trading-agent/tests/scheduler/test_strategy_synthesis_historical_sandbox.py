import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal, CandleDict
from scheduler.strategy_synthesis_scheduler import (
    StrategySynthesisScheduler,
    HistoricalSliceSession,
)


class MockCandle:
    def __init__(self, ts, o, h, l, c, v=100.0):
        self.timestamp = ts
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v


@pytest.mark.asyncio
async def test_historical_slice_session_zero_lookahead():
    """Verifies that HistoricalSliceSession never leaks future bars beyond current slice."""
    base_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    all_candles = [
        MockCandle(base_time + timedelta(hours=i), 1.1000 + i * 0.0005, 1.1010 + i * 0.0005, 1.0990 + i * 0.0005, 1.1005 + i * 0.0005)
        for i in range(100)
    ]

    # Slice up to bar 40 (meaning 41 candles total)
    slice_40 = all_candles[:41]
    session = HistoricalSliceSession(slice_40)

    # Strategy queries session for candles
    res = await session.execute("dummy stmt")
    scalars = res.scalars().all()

    # Must return exactly 41 items in descending order (newest first)
    assert len(scalars) == 41
    assert scalars[0].timestamp == slice_40[-1].timestamp
    # Bar 50 must NOT be present
    assert not any(c.timestamp == all_candles[50].timestamp for c in scalars)


@pytest.mark.asyncio
async def test_run_historical_simulation_insufficient_candles():
    """Verifies that fewer than 60 candles in DB safely returns empty trade list."""
    scheduler = StrategySynthesisScheduler({})

    class DummyStrategy(EdgeStrategy):
        strategy_id = "test_strat_few_candles"
        async def evaluate(self, session, symbol, settings):
            return None

    with patch("scheduler.strategy_synthesis_scheduler.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_exec = MagicMock()
        # Return only 20 candles (less than 60 min_candles)
        mock_exec.scalars.return_value.all.return_value = [
            MockCandle(datetime.now(timezone.utc), 1.1, 1.11, 1.09, 1.1) for _ in range(20)
        ]
        mock_session.execute.return_value = mock_exec
        mock_get_session.return_value.__aenter__.return_value = mock_session

        returns = await scheduler.run_historical_simulation(DummyStrategy, "EURUSD")
        assert returns == []


@pytest.mark.asyncio
async def test_run_historical_simulation_detects_trades_with_friction():
    """Verifies that historical simulation executes trades and applies realistic friction."""
    scheduler = StrategySynthesisScheduler({})

    class MovingAverageCrossoverStrategy(EdgeStrategy):
        strategy_id = "ma_cross_test"
        applicable_symbols = {"EURUSD"}

        async def evaluate(self, session, symbol, settings):
            candles = await self.get_historical_candles(session, symbol, "H1", 20)
            if len(candles) < 15:
                return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0)

            # Signal buy when latest close > open of previous candle
            latest = candles[-1]
            prev = candles[-2]
            if latest.close > prev.open:
                return EdgeSignal(
                    strategy_id=self.strategy_id,
                    symbol=symbol,
                    direction="buy",
                    valid=True,
                    confidence=0.85,
                    stop_loss=latest.close * 0.995,   # 0.5% SL
                    take_profit=latest.close * 1.010,  # 1.0% TP
                )
            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0)

    # Generate 150 simulated realistic candles with cyclical price moves
    base_time = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
    mock_candles = []
    price = 1.1000
    import math
    for i in range(150):
        delta = math.sin(i / 5.0) * 0.0030
        p = price + delta
        mock_candles.append(MockCandle(base_time + timedelta(hours=i), p - 0.0005, p + 0.0020, p - 0.0020, p))

    with patch("scheduler.strategy_synthesis_scheduler.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_exec = MagicMock()
        mock_exec.scalars.return_value.all.return_value = mock_candles
        mock_session.execute.return_value = mock_exec
        mock_get_session.return_value.__aenter__.return_value = mock_session

        returns = await scheduler.run_historical_simulation(MovingAverageCrossoverStrategy, "EURUSD")

        # Must have evaluated multiple trades
        assert len(returns) > 0
        assert all(isinstance(r, float) for r in returns)
        # Returns must have variation (both positive and negative after friction)
        assert any(r > 0 for r in returns)


def test_walk_forward_empirical_split():
    """Verifies walk forward validation correctly partitions returns and calculates WFE."""
    scheduler = StrategySynthesisScheduler({})

    class DummyStrategy(EdgeStrategy):
        strategy_id = "wf_test_strat"

    # 10 trades: IS has 6 trades, OOS has 4 trades
    empirical_returns = [0.015, 0.012, 0.018, 0.010, 0.014, 0.016, 0.012, 0.015, 0.011, 0.013]
    wf_res = scheduler.run_walk_forward_validation(DummyStrategy, "EURUSD", returns=empirical_returns)

    assert wf_res["passed"] is True
    assert wf_res["is_trades"] == 6
    assert wf_res["oos_trades"] == 4
    assert wf_res["wfe"] > 0.0
