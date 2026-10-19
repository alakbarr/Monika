import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, timezone

from monika.application.analysis.arbitration.signal_arbitrator import SignalArbitrator
from monika.application.analysis.strategies.base_strategy import EdgeSignal
from monika.domain.risk.evaluators.execution_checks import RiskExecutionChecksMixin, DEFAULT_SYMBOL_MAX_SPREAD_POINTS
from monika.application.analysis.tools.executor import FACTOR_POINT_MAP


def test_bonus_confluence_factors_registered_in_factor_point_map():
    """Verify bonus confluence factors are correctly in FACTOR_POINT_MAP with point 1."""
    assert FACTOR_POINT_MAP.get("quant_strategy_edge") == 1
    assert FACTOR_POINT_MAP.get("rr_ratio_bonus") == 1
    assert FACTOR_POINT_MAP.get("adr_target_bonus") == 1


@pytest.mark.asyncio
async def test_signal_arbitrator_suppresses_counter_trend_mean_reversion():
    """Verify that a synthesized alpha with mean_reversion tags is blocked during strong trend."""
    arbitrator = SignalArbitrator(
        settings={"trading": {"signal_arbitration": {"min_quant_confidence_for_trend_override": 0.70}}}
    )

    # Synthesized alpha that attempts to fade a strong trend
    mean_rev_signal = EdgeSignal(
        strategy_id="alpha_gbpusd_867953",
        symbol="GBPUSD",
        direction="sell",
        valid=True,
        confidence=0.85,
        entry_price=1.2850,
        stop_loss=1.2900,
        take_profit=1.2750,
        tags=["atr_exhaustion", "mean_reversion", "bearish_reversal"],
    )

    # Market is in a strong bullish trend, LLM is waiting
    session = AsyncMock()
    result = await arbitrator.arbitrate(
        session=session,
        symbol="GBPUSD",
        quant_signal=mean_rev_signal,
        llm_decision={"decision": "wait", "confidence": 0.5},
        regime_info={"regime": "trending_bullish"},
    )

    assert result.decision == "wait"
    assert result.selected_source == "regime_protection"
    assert "Counter-trend mean reversion is prohibited" in result.arbitration_reason


@pytest.mark.asyncio
async def test_signal_arbitrator_allows_genuine_trend_alpha_in_trend():
    """Verify that a genuine trend-following alpha is prioritized during trend."""
    arbitrator = SignalArbitrator(
        settings={"trading": {"signal_arbitration": {"min_quant_confidence_for_trend_override": 0.70}}}
    )

    trend_signal = EdgeSignal(
        strategy_id="alpha_xtiusd_374fa7",
        symbol="XTIUSD",
        direction="buy",
        valid=True,
        confidence=0.88,
        entry_price=94.20,
        stop_loss=92.70,
        take_profit=96.72,
        tags=["volume_expansion", "donchian_breakout", "bullish_momentum"],
    )

    session = AsyncMock()
    result = await arbitrator.arbitrate(
        session=session,
        symbol="XTIUSD",
        quant_signal=trend_signal,
        llm_decision={"decision": "wait", "confidence": 0.4},
        regime_info={"regime": "strong_trend"},
    )

    assert result.decision == "buy"
    assert result.selected_source == "quant"


@pytest.mark.asyncio
async def test_crypto_spread_resolution_in_risk_gate():
    """Verify that BTCUSD 1965 points spread is accepted under default points and relative spread."""
    checker = RiskExecutionChecksMixin()
    checker.settings = {"trading": {"risk": {}}}

    mock_mt5 = AsyncMock()
    mock_mt5.is_connected = AsyncMock(return_value=True)
    # BTCUSD spread: 1965 points ($19.65 at point 0.01), price $81,200 (spread pct = 0.024% <= 0.05%)
    mock_mt5.get_spread = AsyncMock(
        return_value={
            "spread_points": 1965,
            "spread_cost": 19.65,
            "bid": 81200.0,
            "ask": 81219.65,
        }
    )
    checker._mt5 = mock_mt5

    passed, reason = await checker._check_max_spread(session=None, symbol="BTCUSD")
    assert passed is True
    assert reason == "ok"


@pytest.mark.asyncio
async def test_crypto_spread_breach_in_risk_gate():
    """Verify that an exorbitant spread (e.g. 5000 points and 1% spread cost) is rejected."""
    checker = RiskExecutionChecksMixin()
    checker.settings = {"trading": {"risk": {}}}

    mock_mt5 = AsyncMock()
    mock_mt5.is_connected = AsyncMock(return_value=True)
    mock_mt5.get_spread = AsyncMock(
        return_value={
            "spread_points": 5000,
            "spread_cost": 500.0,
            "bid": 50000.0,
            "ask": 50500.0,
        }
    )
    checker._mt5 = mock_mt5

    passed, reason = await checker._check_max_spread(session=None, symbol="BTCUSD")
    assert passed is False
    assert "exceeds maximum allowed 3500.0 pts" in reason


@pytest.mark.asyncio
async def test_timesfm_mock_forecast_in_backtest_session():
    """Verify that ZeroLookaheadSliceSession returns MockTimesFMForecastRow without CandleDict parse errors."""
    from monika.application.backtest.isolated_strategy_harness import ZeroLookaheadSliceSession, CandleDict
    from monika.infrastructure.ml.timesfm_engine import TimesFMEngine

    candle = CandleDict(
        {"time": datetime.now(timezone.utc), "open": 1.12, "high": 1.13, "low": 1.11, "close": 1.125, "volume": 100}
    )
    session = ZeroLookaheadSliceSession(
        candle_cache={("EURUSD", "H1"): [candle]},
        as_of_time=datetime.now(timezone.utc),
        symbol="EURUSD",
    )

    engine = TimesFMEngine({})
    forecast = await engine.get_latest_forecast(session, "EURUSD", timeframe="H1")
    assert forecast is not None
    assert "quantiles" in forecast
    assert forecast["symbol"] == "EURUSD"
    assert "Q50" in forecast["quantiles"]


def test_donchian_breakout_applicable_symbols_restricted_to_crypto():
    """Verify that BTCDonchianBreakout and DonchianBreakoutStrategy are restricted to crypto only."""
    from monika.application.analysis.strategies.btc_donchian_breakout import (
        BTCDonchianBreakout,
        DonchianBreakoutStrategy,
    )

    assert BTCDonchianBreakout.applicable_symbols == {"BTCUSD", "ETHUSD", "SOLUSD"}
    assert DonchianBreakoutStrategy.applicable_symbols == {"BTCUSD", "ETHUSD", "SOLUSD"}
    assert "EURUSD" not in BTCDonchianBreakout.applicable_symbols


def test_smc_fvg_quarantined_from_core_bypass():
    """Verify that smc_fvg is not in CORE_STRATEGY_IDS and must undergo standard incubation."""
    from monika.application.analysis.strategies.decay_monitor import CORE_STRATEGY_IDS, get_strategy_decay_monitor

    assert "smc_fvg" not in CORE_STRATEGY_IDS
    monitor = get_strategy_decay_monitor()
    health = monitor.get_health("smc_fvg")
    assert health.is_incubation_passed is False
