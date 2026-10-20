"""Unit tests for GBPUSDTrendBreakoutStrategy."""

import pytest
from unittest.mock import AsyncMock, patch
from tests.conftest import create_mock_async_session
from monika.application.analysis.strategies.base_strategy import CandleDict, EdgeSignal
from monika.application.analysis.strategies.gbpusd_trend_breakout import GBPUSDTrendBreakoutStrategy


@pytest.mark.asyncio
async def test_gbpusd_trend_breakout_rejects_other_symbols():
    strat = GBPUSDTrendBreakoutStrategy()
    session = create_mock_async_session()
    sig = await strat.evaluate(session, "EURUSD", {})

    assert isinstance(sig, EdgeSignal)
    assert not sig.valid
    assert "not applicable" in sig.rationale.lower()


@pytest.mark.asyncio
async def test_gbpusd_trend_breakout_detects_bullish_breakout():
    strat = GBPUSDTrendBreakoutStrategy()
    session = create_mock_async_session()

    # Generate 150 candles with an upward trend and a final breakout bar
    candles = []
    base_price = 1.2500
    for i in range(140):
        # Stepping upward
        price = base_price + (i * 0.0005)
        candles.append(
            CandleDict(
                {
                    "open": price,
                    "high": price + 0.0010,
                    "low": price - 0.0005,
                    "close": price + 0.0005,
                }
            )
        )

    # Final bar creates a clear Donchian breakout above the last 12 bars and well above EMA-100
    last_p = base_price + (140 * 0.0005) + 0.0050
    candles.append(
        CandleDict(
            {
                "open": last_p - 0.0010,
                "high": last_p + 0.0020,
                "low": last_p - 0.0010,
                "close": last_p,
            }
        )
    )

    with patch.object(strat, "get_historical_candles", AsyncMock(return_value=candles)):
        sig = await strat.evaluate(session, "GBPUSD", {})

    assert isinstance(sig, EdgeSignal)
    assert sig.valid is True
    assert sig.direction == "buy"
    assert sig.entry_price == round(last_p, 5)
    assert sig.stop_loss < sig.entry_price
    assert sig.take_profit > sig.entry_price
    assert sig.confidence >= 0.65
    assert "Bullish Donchian Breakout" in sig.rationale


@pytest.mark.asyncio
async def test_gbpusd_trend_breakout_detects_bearish_breakdown():
    strat = GBPUSDTrendBreakoutStrategy()
    session = create_mock_async_session()

    # Generate 150 candles with a downward trend and a final breakdown bar
    candles = []
    base_price = 1.3500
    for i in range(140):
        price = base_price - (i * 0.0005)
        candles.append(
            CandleDict(
                {
                    "open": price,
                    "high": price + 0.0005,
                    "low": price - 0.0010,
                    "close": price - 0.0005,
                }
            )
        )

    # Final bar breaks down below the channel
    last_p = base_price - (140 * 0.0005) - 0.0050
    candles.append(
        CandleDict(
            {
                "open": last_p + 0.0010,
                "high": last_p + 0.0010,
                "low": last_p - 0.0020,
                "close": last_p,
            }
        )
    )

    with patch.object(strat, "get_historical_candles", AsyncMock(return_value=candles)):
        sig = await strat.evaluate(session, "GBPUSD", {})

    assert isinstance(sig, EdgeSignal)
    assert sig.valid is True
    assert sig.direction == "sell"
    assert sig.entry_price == round(last_p, 5)
    assert sig.stop_loss > sig.entry_price
    assert sig.take_profit < sig.entry_price
    assert sig.confidence >= 0.65
    assert "Bearish Donchian Breakdown" in sig.rationale
