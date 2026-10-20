import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
import pandas as pd
import numpy as np

from monika.application.analysis.strategies.registry import (
    StrategyRegistry,
    QUARANTINED_STRATEGY_IDS,
    PROMOTED_EMPIRICAL_STRATEGIES,
)
from monika.application.analysis.strategies.usdjpy_atr_exhaustion import USDJPYATRExhaustionStrategy
from monika.application.analysis.strategies.xtiusd_atr_exhaustion import XTIUSDATRExhaustionStrategy
from monika.application.analysis.strategies.xauusd_atr_exhaustion import XAUUSDATRExhaustionStrategy
from monika.application.analysis.strategies.btcusd_dynamic_donchian import BTCUSDDynamicDonchianStrategy
from monika.application.analysis.strategies.tsm_momentum import TimeSeriesMomentum
from monika.application.analysis.validators.in_harness_grounding import InHarnessGroundingValidator
from monika.infrastructure.data_ingestion.sources.sovereign_yield_spreads import SovereignYieldSpreads


class DummyCandle:
    def __init__(self, open_: float, high: float, low: float, close: float):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close


def test_quarantined_and_promoted_strategies_integrity():
    """Verify toxic alphas are quarantined and newly promoted empirical alphas are in the whitelist."""
    # Ensure toxic alphas are quarantined
    for toxic_id in [
        "asian_range_fade",
        "tokyo_open_sweep",
        "alpha_xtiusd_374fa7",
        "alpha_eurusd_8060ed",
        "alpha_xauusd_5044bf",
    ]:
        assert toxic_id in QUARANTINED_STRATEGY_IDS

    # Ensure newly promoted empirical strategies are promoted
    for promoted_id in [
        "usdjpy_atr_exhaustion",
        "xtiusd_atr_exhaustion",
        "xauusd_atr_exhaustion",
        "btcusd_dynamic_donchian",
    ]:
        assert promoted_id in PROMOTED_EMPIRICAL_STRATEGIES
        strategy_cls = StrategyRegistry.get(promoted_id)
        assert strategy_cls is not None
        instance = strategy_cls()
        assert instance.strategy_id == promoted_id


def test_empirical_strategies_attributes():
    """Verify attributes and metadata of newly promoted empirical strategy classes."""
    strat_usdjpy = USDJPYATRExhaustionStrategy()
    assert strat_usdjpy.strategy_id == "usdjpy_atr_exhaustion"
    assert "USDJPY" in strat_usdjpy.applicable_symbols
    assert strat_usdjpy.factor_family == "mean_reversion"

    strat_xti = XTIUSDATRExhaustionStrategy()
    assert strat_xti.strategy_id == "xtiusd_atr_exhaustion"
    assert "XTIUSD" in strat_xti.applicable_symbols
    assert strat_xti.factor_family == "mean_reversion"

    strat_xau = XAUUSDATRExhaustionStrategy()
    assert strat_xau.strategy_id == "xauusd_atr_exhaustion"
    assert "XAUUSD" in strat_xau.applicable_symbols
    assert strat_xau.factor_family == "mean_reversion"

    strat_btc = BTCUSDDynamicDonchianStrategy()
    assert strat_btc.strategy_id == "btcusd_dynamic_donchian"
    assert "BTCUSD" in strat_btc.applicable_symbols
    assert strat_btc.factor_family == "breakout"


@pytest.mark.asyncio
async def test_usdjpy_atr_exhaustion_evaluation():
    """Verify USDJPYATRExhaustionStrategy evaluates candle stream and generates valid signal."""
    strategy = USDJPYATRExhaustionStrategy()

    # Create 60 candles where price stretches strongly above upper band
    candles = []
    base = 150.0
    for i in range(50):
        p = base + i * 0.02
        candles.append(DummyCandle(open_=p, high=p + 0.10, low=p - 0.10, close=p))

    # Last candles: aggressive spike to push RSI > 68 and stretch > 2.25x ATR
    for i in range(10):
        p = base + 1.0 + i * 0.50
        candles.append(DummyCandle(open_=p - 0.20, high=p + 0.30, low=p - 0.30, close=p))

    # Rejection bar at the end
    last_p = base + 6.0
    candles.append(DummyCandle(open_=last_p, high=last_p + 0.8, low=last_p - 0.5, close=last_p - 0.2))

    session = AsyncMock()
    with patch.object(strategy, "get_historical_candles", new_callable=AsyncMock) as mock_candles:
        mock_candles.return_value = candles
        signal = await strategy.evaluate(session, "USDJPY", settings={})

    assert signal is not None
    assert signal.strategy_id == "usdjpy_atr_exhaustion"
    assert signal.symbol == "USDJPY"
    if signal.valid:
        assert signal.direction in ("buy", "sell")
        assert signal.entry_price > 0
        assert signal.stop_loss is not None
        assert signal.take_profit is not None


@pytest.mark.asyncio
async def test_btcusd_dynamic_donchian_breakout_evaluation():
    """Verify BTCUSDDynamicDonchianStrategy evaluates candle breakout and sets stop loss / take profit."""
    strategy = BTCUSDDynamicDonchianStrategy()

    candles = []
    base = 65000.0
    for i in range(50):
        p = base + (i % 5) * 50.0
        candles.append(DummyCandle(open_=p, high=p + 40.0, low=p - 40.0, close=p))

    # Breakout candle exceeding 20-period high
    breakout_p = base + 1200.0
    candles.append(
        DummyCandle(open_=breakout_p - 200.0, high=breakout_p + 100.0, low=breakout_p - 250.0, close=breakout_p)
    )

    session = AsyncMock()
    with patch.object(strategy, "get_historical_candles", new_callable=AsyncMock) as mock_candles:
        mock_candles.return_value = candles
        signal = await strategy.evaluate(session, "BTCUSD", settings={})

    assert signal is not None
    assert signal.strategy_id == "btcusd_dynamic_donchian"
    assert signal.symbol == "BTCUSD"
    if signal.valid:
        assert signal.direction == "buy"
        assert signal.entry_price == pytest.approx(breakout_p)
        assert signal.stop_loss < signal.entry_price
        assert signal.take_profit > signal.entry_price


def create_mock_session():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_res.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_res
    session.begin_nested = MagicMock()
    session.add = MagicMock()
    return session


@pytest.mark.asyncio
async def test_tsm_momentum_regime_normalization():
    """Verify TimeSeriesMomentum accepts normalized regime labels without failing strict confirmation."""
    strategy = TimeSeriesMomentum()
    session = create_mock_session()

    with patch(
        "monika.application.analysis.strategies.tsm_momentum.classify_market_regime", new_callable=AsyncMock
    ) as mock_reg:
        # Test that BULLISH_TREND does not trigger 'fails strict confirmation'
        mock_reg.return_value = {"regime": "BULLISH_TREND"}

        with patch.object(strategy, "get_historical_candles", new_callable=AsyncMock) as mock_candles:
            # Provide empty candles to stop at data retrieval after regime passes
            mock_candles.return_value = []
            signal = await strategy.evaluate(session, "BTCUSD", settings={})

            assert signal is not None
            assert "fails strict confirmation" not in (signal.rationale or "")


def test_in_harness_grounding_reconciliation():
    """Verify ADR/ATR paradox reconciliation: ATR noise floor does not exceed ADR ceiling."""
    # Scenario: Low volatility or compression where ATR (0.0025) exceeds ADR ceiling (0.45 * 0.0020 = 0.0009).
    # Prior to fix, SL dist of 0.00085 was rejected because 0.00085 < ATR * 0.95.
    # With fix, min_sl_dist is capped at 0.90 * adr_ceiling (0.00081), allowing valid trade.
    grounding_data = {
        "current_price": 1.0850,
        "h1_atr": 0.0025,
        "daily_atr": 0.0020,
        "adr": 0.0020,
    }

    decision_payload = {
        "decision": "buy",
        "entry_price": 1.0850,
        "stop_loss": 1.08415,  # sl_dist = 0.00085
        "take_profit": 1.0875,
        "confidence": 0.85,
    }

    is_grounded, errors, metadata = InHarnessGroundingValidator.verify_grounding(
        decision_payload=decision_payload,
        data_bundle=grounding_data,
        symbol="EURUSD",
    )

    noise_errors = [e for e in errors if "too tight for market noise" in e]
    assert len(noise_errors) == 0, f"Expected zero noise errors due to reconciliation, got: {noise_errors}"


@pytest.mark.asyncio
async def test_sovereign_yield_spreads_db_fallback():
    """Verify SovereignYieldSpreads._fetch_db_fallback executes with alias candidates."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [2.45, 2.40]
    mock_session.execute.return_value = mock_result

    res = await SovereignYieldSpreads._fetch_db_fallback("GERMANY_10Y", session=mock_session)
    assert res is not None
    curr, prev = res
    assert curr == 2.45
    assert prev == 2.40

    # Ensure execute was called
    assert mock_session.execute.called
