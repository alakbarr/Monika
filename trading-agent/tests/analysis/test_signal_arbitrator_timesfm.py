import pytest
from datetime import datetime, timezone
from analysis.arbitration.signal_arbitrator import SignalArbitrator
from analysis.strategies.base_strategy import EdgeSignal
from indicators.timesfm_engine import TimesFMEngine
import utils.clock as clock


@pytest.mark.asyncio
async def test_signal_arbitrator_timesfm_statistical_suppression(db_session):
    now = clock.now()
    engine = TimesFMEngine()
    # Save bearish skew forecast
    tfm_fc = {
        "symbol": "EURUSD",
        "timeframe": "H1",
        "generated_at": now,
        "horizon_steps": 24,
        "quantiles": {"q10": [1.08] * 24, "q50": [1.09] * 24, "q90": [1.095] * 24},
        "expected_range": 0.015,
        "quantile_skew": -0.45,  # Strong bearish skew
        "volatility_expansion_ratio": 1.1,
        "reachability_envelope": [],
    }
    await engine.save_forecast(db_session, tfm_fc)
    await db_session.commit()

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    quant_sig = EdgeSignal(
        strategy_id="test_breakout",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=1.0920,
        stop_loss=1.0880,
        take_profit=1.1000,
    )
    # LLM is in wait stance
    llm_dec = {"decision": "wait", "confidence": 0.5}

    result = await arbitrator.arbitrate(
        db_session,
        symbol="EURUSD",
        quant_signal=quant_sig,
        llm_decision=llm_dec,
        vix_level=16.0,
    )

    assert result.decision == "avoid"
    assert result.selected_source == "statistical_suppression"
    assert "TimesFM statistical skew" in result.arbitration_reason


@pytest.mark.asyncio
async def test_signal_arbitrator_timesfm_conflict_resolution(db_session):
    now = clock.now()
    engine = TimesFMEngine()
    # Save bullish skew forecast
    tfm_fc = {
        "symbol": "GBPUSD",
        "timeframe": "H1",
        "generated_at": now,
        "horizon_steps": 24,
        "quantiles": {"q10": [1.25] * 24, "q50": [1.26] * 24, "q90": [1.28] * 24},
        "expected_range": 0.030,
        "quantile_skew": +0.40,  # Decisive bullish skew
        "volatility_expansion_ratio": 1.2,
        "reachability_envelope": [],
    }
    await engine.save_forecast(db_session, tfm_fc)
    await db_session.commit()

    arbitrator = SignalArbitrator(settings={"trading": {"signal_arbitration": {}}})
    quant_sig = EdgeSignal(
        strategy_id="test_trend",
        symbol="GBPUSD",
        direction="buy",
        valid=True,
        confidence=0.75,
        entry_price=1.2600,
        stop_loss=1.2550,
        take_profit=1.2750,
    )
    # LLM conflictingly says sell in mixed/ranging market
    llm_dec = {"decision": "sell", "confidence": 0.70, "entry_price": 1.2600, "stop_loss": 1.2650, "take_profit": 1.2500}

    result = await arbitrator.arbitrate(
        db_session,
        symbol="GBPUSD",
        quant_signal=quant_sig,
        llm_decision=llm_dec,
        vix_level=16.0,
        market_regime="ranging",
    )

    # TimesFM tie break favors the BUY side
    assert result.decision == "buy"
    assert "timesfm_tie_break" in result.selected_source
