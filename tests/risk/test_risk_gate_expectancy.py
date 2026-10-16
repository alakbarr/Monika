import pytest
from datetime import datetime, timezone
from monika.domain.risk.risk_gate import RiskGate
from monika.domain.risk.position_sizing import SizingResult
from monika.infrastructure.ml.timesfm_engine import TimesFMEngine
import monika.core.primitives.clock as clock


@pytest.mark.asyncio
async def test_risk_gate_timesfm_expectancy_rejection(db_session):
    now = clock.now()
    engine = TimesFMEngine()
    # Save forecast with Q90 at 2650.0
    tfm_fc = {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "generated_at": now,
        "horizon_steps": 24,
        "quantiles": {
            "q10": [2600.0] * 24,
            "q30": [2620.0] * 24,
            "q50": [2630.0] * 24,
            "q70": [2640.0] * 24,
            "q90": [2650.0] * 24,
        },
        "expected_range": 50.0,
        "quantile_skew": 0.0,
        "volatility_expansion_ratio": 1.0,
        "reachability_envelope": [],
    }
    await engine.save_forecast(db_session, tfm_fc)
    await db_session.commit()

    gate = RiskGate(settings={"timesfm": {"enabled": True, "expectancy_gate": {"enabled": True}}})

    # Case 1: Overextended TP (2720.0 >> Q90 2650.0) -> Rejected
    unrealistic_sizing = SizingResult(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2630.0,
        stop_loss=2615.0,
        take_profit=2720.0,  # Unreachable in 24h
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=15.0,
        sl_distance_pips=150.0,
        pip_value_per_lot=1.0,
        raw_lots=0.66,
        recommended_lots=0.66,
        rr_ratio=6.0,
        is_valid=True,
    )

    ok, reason = await gate._check_timesfm_expectancy(db_session, "XAUUSD", "buy", unrealistic_sizing)
    assert ok is False
    assert "exceeds TimesFM Q90 ceiling" in reason

    # Case 2: Realistic TP (2645.0 <= Q90 2650.0) -> Approved
    realistic_sizing = SizingResult(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2630.0,
        stop_loss=2615.0,
        take_profit=2645.0,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=15.0,
        sl_distance_pips=150.0,
        pip_value_per_lot=1.0,
        raw_lots=0.66,
        recommended_lots=0.66,
        rr_ratio=1.0,
        is_valid=True,
    )
    ok_real, reason_real = await gate._check_timesfm_expectancy(db_session, "XAUUSD", "buy", realistic_sizing)
    assert ok_real is True
    assert "TimesFM expectancy passed" in reason_real


@pytest.mark.asyncio
async def test_risk_gate_timesfm_expectancy_rejection_forex_5_decimals(db_session):
    """Verify 5-decimal formatting in timesfm_expectancy rejection message for AUDUSD at 0.69116."""
    now = clock.now()
    engine = TimesFMEngine()

    tfm_fc = {
        "symbol": "AUDUSD",
        "timeframe": "H1",
        "generated_at": now,
        "horizon_steps": 24,
        "quantiles": {
            "q10": [0.68600] * 24,
            "q30": [0.68850] * 24,
            "q50": [0.69000] * 24,
            "q70": [0.69100] * 24,
            "q90": [0.69250] * 24,
        },
        "expected_range": 0.0065,
        "quantile_skew": 0.0,
        "volatility_expansion_ratio": 1.0,
        "reachability_envelope": [],
    }
    await engine.save_forecast(db_session, tfm_fc)
    await db_session.commit()

    gate = RiskGate(settings={"timesfm": {"enabled": True, "expectancy_gate": {"enabled": True}}})

    # Proposed TP 0.71000 exceeds Q90 0.69250
    sizing_tp_rejection = SizingResult(
        symbol="AUDUSD",
        direction="buy",
        entry_price=0.69116,
        stop_loss=0.68800,
        take_profit=0.71000,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.00316,
        sl_distance_pips=31.6,
        pip_value_per_lot=10.0,
        raw_lots=0.31,
        recommended_lots=0.31,
        rr_ratio=5.9,
        is_valid=True,
    )

    ok, reason = await gate._check_timesfm_expectancy(db_session, "AUDUSD", "buy", sizing_tp_rejection)
    assert ok is False
    assert "TimesFM Q90 ceiling (0.69250)" in reason
