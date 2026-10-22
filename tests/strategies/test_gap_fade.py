import pytest
from unittest.mock import AsyncMock
from tests.conftest import create_mock_async_session
from monika.application.analysis.strategies.gap_fade import DailyReopenGapFade
from monika.application.analysis.strategies.base_strategy import CandleDict


def _make_candles(n: int = 20, base: float = 1.0000, tr: float = 0.0020) -> list[CandleDict]:
    half = tr / 2.0
    return [
        CandleDict(
            {
                "timestamp": f"2026-01-01T{i:02d}:00:00Z",
                "open": base,
                "high": base + half,
                "low": base - half,
                "close": base,
                "volume": 100.0,
            }
        )
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_gap_fade_unsupported_symbol():
    settings = {"trading": {"edge_strategy": {"gap_fade": {"enabled": True}}}}
    strategy = DailyReopenGapFade(settings)
    session = create_mock_async_session()

    sig = await strategy.evaluate(session, "UNSUPPORTED_SYM", settings)
    assert not sig.valid
    assert "not in applicable_symbols" in sig.rationale


@pytest.mark.asyncio
async def test_gap_fade_insufficient_history():
    settings = {"trading": {"edge_strategy": {"gap_fade": {"enabled": True}}}}
    strategy = DailyReopenGapFade(settings)
    strategy.get_historical_candles = AsyncMock(return_value=_make_candles(n=10))

    session = create_mock_async_session()
    sig = await strategy.evaluate(session, "EURUSD", settings)
    assert not sig.valid
    assert "insufficient candle history" in sig.rationale


@pytest.mark.asyncio
async def test_gap_fade_no_gap_pattern():
    settings = {"trading": {"edge_strategy": {"gap_fade": {"enabled": True}}}}
    strategy = DailyReopenGapFade(settings)
    strategy.get_historical_candles = AsyncMock(return_value=_make_candles(n=20))

    session = create_mock_async_session()
    sig = await strategy.evaluate(session, "EURUSD", settings)
    assert not sig.valid
    assert "no gap fill rejection pattern" in sig.rationale


@pytest.mark.asyncio
async def test_gap_fade_valid_buy_signal():
    settings = {"trading": {"edge_strategy": {"gap_fade": {"enabled": True}}}}
    strategy = DailyReopenGapFade(settings)

    candles = _make_candles(n=20, base=1.0000, tr=0.0020)
    # Candle 19 (curr): gap down >= 0.35 * ATR (0.0007), bullish close > open
    candles[-1] = CandleDict(
        {
            "timestamp": "2026-01-01T20:00:00Z",
            "open": 0.9990,  # gap down 0.0010 from prev.close 1.0000
            "high": 0.9998,
            "low": 0.9988,
            "close": 0.9995,  # bullish close
            "volume": 150.0,
        }
    )
    strategy.get_historical_candles = AsyncMock(return_value=candles)

    session = create_mock_async_session()
    sig = await strategy.evaluate(session, "EURUSD", settings)

    assert sig.valid
    assert sig.direction == "buy"
    assert sig.confidence == 0.76
    assert sig.stop_loss < sig.entry_price < sig.take_profit
    assert "Gap down" in sig.rationale
    assert "bullish rejection close" in sig.rationale
    assert "gap_fade" in sig.tags


@pytest.mark.asyncio
async def test_gap_fade_valid_sell_signal():
    settings = {"trading": {"edge_strategy": {"gap_fade": {"enabled": True}}}}
    strategy = DailyReopenGapFade(settings)

    candles = _make_candles(n=20, base=1.0000, tr=0.0020)
    # Candle 19 (curr): gap up >= 0.35 * ATR (0.0007), bearish close < open
    candles[-1] = CandleDict(
        {
            "timestamp": "2026-01-01T20:00:00Z",
            "open": 1.0010,  # gap up 0.0010 from prev.close 1.0000
            "high": 1.0012,
            "low": 1.0002,
            "close": 1.0005,  # bearish close
            "volume": 150.0,
        }
    )
    strategy.get_historical_candles = AsyncMock(return_value=candles)

    session = create_mock_async_session()
    sig = await strategy.evaluate(session, "GBPUSD", settings)

    assert sig.valid
    assert sig.direction == "sell"
    assert sig.confidence == 0.76
    assert sig.take_profit < sig.entry_price < sig.stop_loss
    assert "Gap up" in sig.rationale
    assert "bearish rejection close" in sig.rationale
    assert "gap_fade" in sig.tags
