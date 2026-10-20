"""
Unit and integration tests for newly promoted empirical strategies.
Verifies registration, initialization, regime compatibility, and signal evaluation.
"""

from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock

from monika.application.analysis.strategies.base_strategy import CandleDict, EdgeSignal
from monika.application.analysis.strategies.registry import StrategyRegistry
from monika.application.analysis.strategies.asian_range_fade import AsianRangeFadeStrategy
from monika.application.analysis.strategies.smt_divergence import SMTDivergenceStrategy
from monika.application.analysis.strategies.tokyo_sweep import TokyoSweepStrategy
from monika.application.analysis.strategies.vwap_reversion import VWAPMeanReversionStrategy
from monika.application.analysis.strategies.bollinger_reversion import BollingerReversionStrategy


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


def test_promoted_strategies_registered():
    """Verify that all 5 promoted empirical strategies are registered in StrategyRegistry."""
    registered = StrategyRegistry.list_strategies()
    assert "asian_range_fade" in registered
    assert "smt_divergence" in registered
    assert "tokyo_open_sweep" in registered
    assert "vwap_mean_reversion" in registered
    assert "bollinger_reversion" in registered


def test_quarantined_strategies():
    """Verify that toxic strategies are quarantined and synthesized alphas are gated by incubation."""
    from monika.application.analysis.strategies.decay_monitor import get_strategy_decay_monitor

    q_ids = StrategyRegistry.QUARANTINED_STRATEGY_IDS
    assert "smc_fvg" in q_ids
    assert "btc_donchian_breakout" in q_ids
    assert "bollinger_reversion" in q_ids

    decay_mon = get_strategy_decay_monitor()
    assert not decay_mon.is_tradeable("bollinger_reversion")
    assert not decay_mon.get_health("alpha_eurusd_6d622a").is_incubation_passed
    assert not decay_mon.get_health("alpha_gbpusd_867953").is_incubation_passed

    # Verify curated applicable_symbols based on empirical backtest
    assert AsianRangeFadeStrategy.applicable_symbols == {"GBPUSD", "EURUSD"}
    assert TokyoSweepStrategy.applicable_symbols == {"USDJPY"}
    assert SMTDivergenceStrategy.applicable_symbols == {"EURUSD"}
    assert "USDJPY" not in VWAPMeanReversionStrategy.applicable_symbols


@pytest.mark.asyncio
async def test_asian_range_fade_evaluation():
    strat = AsianRangeFadeStrategy()
    session = AsyncMock()

    # Outside Asian session hours (e.g. 14:00 UTC) -> should return invalid signal
    as_of_ny = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)
    sig = await strat.evaluate(session, "GBPUSD", {}, as_of=as_of_ny)
    assert not sig.valid
    assert "Outside Asian session" in sig.rationale

    # Inside Asian session (e.g. 02:00 UTC) with candle data
    as_of_asian = datetime(2026, 10, 20, 2, 0, tzinfo=timezone.utc)
    candles = _make_candles(30, base_price=1.3000)
    # Simulate a rejection of the high: high exceeds prior, but closes bearish
    candles[-1] = CandleDict(open=1.3050, high=1.3060, low=1.3020, close=1.3030, volume=100.0, timestamp=as_of_asian)
    strat.get_historical_candles = AsyncMock(return_value=candles)

    sig_active = await strat.evaluate(session, "GBPUSD", {}, as_of=as_of_asian)
    assert isinstance(sig_active, EdgeSignal)
    if sig_active.valid:
        assert sig_active.direction in ("buy", "sell")
        assert sig_active.take_profit is not None
        assert sig_active.stop_loss is not None
        assert sig_active.confidence >= 0.70


@pytest.mark.asyncio
async def test_smt_divergence_evaluation():
    strat = SMTDivergenceStrategy()
    session = AsyncMock()
    now = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)

    candles = _make_candles(35, base_price=1.1000)
    strat.get_historical_candles = AsyncMock(return_value=candles)

    sig = await strat.evaluate(session, "EURUSD", {}, as_of=now)
    assert isinstance(sig, EdgeSignal)
    assert sig.strategy_id == "smt_divergence"


@pytest.mark.asyncio
async def test_tokyo_sweep_evaluation():
    strat = TokyoSweepStrategy()
    session = AsyncMock()

    # Outside Tokyo window (e.g. 15:00 UTC) -> invalid
    sig_out = await strat.evaluate(session, "EURUSD", {}, as_of=datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc))
    assert not sig_out.valid
    assert "Outside Tokyo open window" in sig_out.rationale

    # Inside Tokyo window (01:00 UTC)
    candles = _make_candles(25, base_price=1.1000)
    strat.get_historical_candles = AsyncMock(return_value=candles)
    sig_in = await strat.evaluate(session, "EURUSD", {}, as_of=datetime(2026, 10, 20, 1, 0, tzinfo=timezone.utc))
    assert isinstance(sig_in, EdgeSignal)
    assert sig_in.strategy_id == "tokyo_open_sweep"


@pytest.mark.asyncio
async def test_vwap_reversion_evaluation():
    strat = VWAPMeanReversionStrategy()
    session = AsyncMock()
    now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)

    candles = _make_candles(35, base_price=1.1000)
    strat.get_historical_candles = AsyncMock(return_value=candles)

    sig = await strat.evaluate(session, "EURUSD", {}, as_of=now)
    assert isinstance(sig, EdgeSignal)
    assert sig.strategy_id == "vwap_mean_reversion"


@pytest.mark.asyncio
async def test_bollinger_reversion_evaluation():
    strat = BollingerReversionStrategy()
    session = AsyncMock()
    now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)

    candles = _make_candles(35, base_price=150.00)
    strat.get_historical_candles = AsyncMock(return_value=candles)

    sig = await strat.evaluate(session, "USDJPY", {}, as_of=now)
    assert isinstance(sig, EdgeSignal)
    assert sig.strategy_id == "bollinger_reversion"
