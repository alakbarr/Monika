import pytest
from datetime import datetime, timezone, timedelta
from database.models import PriceOHLCV, TechnicalIndicator, TimesFMForecast
from analysis.calculators.daily_range_calculator import compute_daily_range_context
from analysis.calculators.intraday_level_optimizer import compute_optimal_levels
from indicators.timesfm_engine import TimesFMEngine
import utils.clock as clock


@pytest.mark.asyncio
async def test_daily_range_with_timesfm_forecast(db_session):
    now = clock.now()
    # Populate D1 bars
    for i in range(10):
        t = now - timedelta(days=(10 - i))
        bar = PriceOHLCV(
            symbol="EURUSD",
            timeframe="D1",
            timestamp=t,
            open=1.1000,
            high=1.1080,
            low=1.0980,
            close=1.1050,
            volume=1000.0,
        )
        db_session.add(bar)

    # Add TimesFM forecast with wide expected range
    tfm_fc = {
        "symbol": "EURUSD",
        "timeframe": "H1",
        "generated_at": now,
        "horizon_steps": 24,
        "quantiles": {
            "q10": [1.0950] * 24,
            "q50": [1.1050] * 24,
            "q90": [1.1150] * 24,
        },
        "expected_range": 0.0200,  # 200 pips
        "quantile_skew": 0.15,
        "volatility_expansion_ratio": 1.45,
        "reachability_envelope": [],
    }
    engine = TimesFMEngine()
    await engine.save_forecast(db_session, tfm_fc)
    await db_session.commit()

    ctx = await compute_daily_range_context(db_session, "EURUSD", settings={"trading": {"risk": {}}})
    assert "error" not in ctx
    assert ctx["timesfm_range"] == 0.0200
    assert ctx["timesfm_vol_ratio"] == 1.45
    assert ctx["effective_range"] > ctx["adr"]  # Blended effective range scaled upward


@pytest.mark.asyncio
async def test_intraday_level_optimizer_with_timesfm_reachability(db_session):
    now = clock.now()
    # Add minimal D1 data for ADR
    for i in range(6):
        t = now - timedelta(days=(6 - i))
        bar = PriceOHLCV(
            symbol="XAUUSD",
            timeframe="D1",
            timestamp=t,
            open=2600.0,
            high=2630.0,
            low=2590.0,
            close=2620.0,
            volume=500.0,
        )
        db_session.add(bar)

    # Add TimesFM forecast where Q90 is capped at 2640.0
    tfm_fc = {
        "symbol": "XAUUSD",
        "timeframe": "H1",
        "generated_at": now,
        "horizon_steps": 24,
        "quantiles": {
            "q10": [2590.0] * 24,
            "q50": [2615.0] * 24,
            "q90": [2640.0] * 24,
        },
        "expected_range": 50.0,
        "quantile_skew": 0.05,
        "volatility_expansion_ratio": 1.1,
        "reachability_envelope": [],
    }
    engine = TimesFMEngine()
    await engine.save_forecast(db_session, tfm_fc)

    from database.models import OrderBlock
    # In-reach order block (2635.0 <= Q90 of 2640.0)
    ob1 = OrderBlock(
        symbol="XAUUSD", timeframe="H4", direction="bullish",
        price_low=2632.0, price_high=2635.0, formed_at=now,
    )
    # Overextended order block (2655.0 > Q90 of 2640.0)
    ob2 = OrderBlock(
        symbol="XAUUSD", timeframe="H4", direction="bullish",
        price_low=2650.0, price_high=2655.0, formed_at=now,
    )
    db_session.add(ob1)
    db_session.add(ob2)
    await db_session.commit()

    res = await compute_optimal_levels(db_session, "XAUUSD", "buy", entry_price=2610.0, settings={"trading": {"risk": {}}})
    assert "error" not in res
    assert len(res["top_tp_candidates"]) > 0
    # Highest scoring candidate should be the in-reach level (<= Q90)
    best_candidate = res["top_tp_candidates"][0]
    assert best_candidate["price"] <= 2640.0
