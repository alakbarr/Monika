"""
Unit tests for new empirical strategies:
- LondonTrendBreakoutStrategy (GBPUSD, AUDUSD)
- LondonGoldBreakoutStrategy (XAUUSD)
- CrudeLondonBreakoutStrategy (XTIUSD, XBRUSD)
- BTCUSMomentumStrategy (BTCUSD)
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, patch

from monika.application.analysis.strategies.base_strategy import CandleDict, EdgeSignal
from monika.application.analysis.strategies.registry import StrategyRegistry
from monika.application.analysis.strategies.london_trend_breakout import LondonTrendBreakoutStrategy
from monika.application.analysis.strategies.london_gold_breakout import LondonGoldBreakoutStrategy
from monika.application.analysis.strategies.crude_london_breakout import CrudeLondonBreakoutStrategy
from monika.application.analysis.strategies.btc_us_momentum import BTCUSMomentumStrategy
from tests.conftest import create_mock_async_session


def _make_candles(n: int = 30, base_price: float = 1.3000, trend: float = 0.0001) -> list[CandleDict]:
    candles = []
    p = base_price
    for i in range(n):
        o = p
        h = p + 0.0010
        l = p - 0.0010
        c = p + trend
        candles.append(
            CandleDict(
                open=o,
                high=h,
                low=l,
                close=c,
                volume=100.0,
                timestamp=datetime(2026, 10, 20, i % 24, 0, tzinfo=timezone.utc),
            )
        )
        p = c
    return candles


def test_new_strategies_registered():
    """Verify that all 4 new empirical strategies are registered in StrategyRegistry."""
    registered = StrategyRegistry.list_strategies()
    assert "london_trend_breakout" in registered
    assert "london_gold_breakout" in registered
    assert "crude_london_breakout" in registered
    assert "btc_us_momentum" in registered


@pytest.mark.asyncio
async def test_london_trend_breakout_evaluation():
    strat = LondonTrendBreakoutStrategy()
    session = create_mock_async_session()

    # Rejection: wrong symbol
    sig = await strat.evaluate(session, "USDJPY")
    assert not sig.valid
    assert "not applicable" in sig.rationale.lower()

    # Rejection: outside London open window (e.g. 10:00 UTC)
    t_10 = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
    sig_10 = await strat.evaluate(session, "GBPUSD", as_of=t_10)
    assert not sig_10.valid
    assert "outside" in sig_10.rationale.lower()

    # Valid evaluation at 07:00 UTC
    t_7 = datetime(2026, 10, 21, 7, 0, tzinfo=timezone.utc)
    candles = _make_candles(30, base_price=1.3000, trend=0.0002)
    # Set current bar to break above Asian range high
    candles[-1] = CandleDict(open=1.3050, high=1.3120, low=1.3040, close=1.3110, volume=500.0)

    with patch.object(strat, "get_historical_candles", AsyncMock(return_value=candles)):
        sig_buy = await strat.evaluate(session, "GBPUSD", as_of=t_7)
        assert isinstance(sig_buy, EdgeSignal)
        assert sig_buy.valid is True
        assert sig_buy.direction == "buy"
        assert sig_buy.entry_price == 1.3110
        assert sig_buy.stop_loss < sig_buy.entry_price
        assert sig_buy.take_profit > sig_buy.entry_price


@pytest.mark.asyncio
async def test_london_gold_breakout_evaluation():
    strat = LondonGoldBreakoutStrategy()
    session = create_mock_async_session()

    # Rejection: outside 08:00 UTC
    t_7 = datetime(2026, 10, 21, 7, 0, tzinfo=timezone.utc)
    sig_wrong_hr = await strat.evaluate(session, "XAUUSD", as_of=t_7)
    assert not sig_wrong_hr.valid

    # Valid evaluation at 08:00 UTC
    t_8 = datetime(2026, 10, 21, 8, 0, tzinfo=timezone.utc)
    candles = _make_candles(35, base_price=2650.0, trend=0.5)
    candles[-1] = CandleDict(open=2660.0, high=2675.0, low=2658.0, close=2672.0, volume=1000.0)

    with patch.object(strat, "get_historical_candles", AsyncMock(return_value=candles)):
        sig_gold = await strat.evaluate(session, "XAUUSD", as_of=t_8)
        assert isinstance(sig_gold, EdgeSignal)
        assert sig_gold.valid is True
        assert sig_gold.direction == "buy"
        assert sig_gold.entry_price == 2672.0
        assert sig_gold.stop_loss < sig_gold.entry_price
        assert sig_gold.take_profit > sig_gold.entry_price


@pytest.mark.asyncio
async def test_crude_london_breakout_evaluation():
    strat = CrudeLondonBreakoutStrategy()
    session = create_mock_async_session()

    # Rejection: wrong symbol
    sig = await strat.evaluate(session, "EURUSD")
    assert not sig.valid

    # Valid evaluation at 07:00 UTC
    t_7 = datetime(2026, 10, 21, 7, 0, tzinfo=timezone.utc)
    candles = _make_candles(30, base_price=75.0, trend=0.05)
    candles[-1] = CandleDict(open=76.8, high=78.5, low=76.7, close=78.2, volume=800.0)

    with patch.object(strat, "get_historical_candles", AsyncMock(return_value=candles)):
        sig_crude = await strat.evaluate(session, "XTIUSD", as_of=t_7)
        assert isinstance(sig_crude, EdgeSignal)
        assert sig_crude.valid is True
        assert sig_crude.direction == "buy"
        assert sig_crude.stop_loss < sig_crude.entry_price


@pytest.mark.asyncio
async def test_btc_us_momentum_evaluation():
    strat = BTCUSMomentumStrategy()
    session = create_mock_async_session()

    # Rejection: outside 13:00 UTC
    t_9 = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    sig_wrong_hr = await strat.evaluate(session, "BTCUSD", as_of=t_9)
    assert not sig_wrong_hr.valid

    # Valid evaluation at 13:00 UTC
    t_13 = datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc)
    candles = _make_candles(35, base_price=67000.0, trend=50.0)
    candles[-1] = CandleDict(open=68000.0, high=69500.0, low=67900.0, close=69200.0, volume=3000.0)

    with patch.object(strat, "get_historical_candles", AsyncMock(return_value=candles)):
        sig_btc = await strat.evaluate(session, "BTCUSD", as_of=t_13)
        assert isinstance(sig_btc, EdgeSignal)
        assert sig_btc.valid is True
        assert sig_btc.direction == "buy"
        assert sig_btc.stop_loss < sig_btc.entry_price
        assert sig_btc.take_profit > sig_btc.entry_price
