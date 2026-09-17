import pytest
from datetime import datetime, timezone
from risk.risk_gate import RiskGate
from risk.position_sizing import SizingResult
from indicators.timesfm_engine import TimesFMEngine
import utils.clock as clock


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
        "quantiles": {"q10": [2600.0] * 24, "q30": [2620.0] * 24, "q50": [2630.0] * 24, "q70": [2640.0] * 24, "q90": [2650.0] * 24},
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
