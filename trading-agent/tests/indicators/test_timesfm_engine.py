import pytest
from datetime import datetime, timezone, timedelta
from database.models import PriceOHLCV, TechnicalIndicator, TimesFMForecast
from indicators.timesfm_engine import TimesFMEngine
import utils.clock as clock


@pytest.mark.asyncio
async def test_timesfm_engine_initialization():
    settings = {
        "timesfm": {
            "enabled": True,
            "device": "cpu",
            "horizon_hours": 24,
            "cache_ttl_hours": 8.0,
        }
    }
    engine = TimesFMEngine(settings)
    assert engine.enabled is True
    assert engine.horizon_hours == 24
    assert engine.cache_ttl_hours == 8.0


@pytest.mark.asyncio
async def test_timesfm_compute_and_save_forecast(db_session):
    now = clock.now()
    # Insert 40 sample bars of H1 data
    for i in range(40):
        t = now - timedelta(hours=(40 - i))
        price = 2000.0 + (i * 0.5)
        bar = PriceOHLCV(
            symbol="XAUUSD",
            timeframe="H1",
            timestamp=t,
            open=price - 1.0,
            high=price + 2.0,
            low=price - 2.0,
            close=price,
            volume=100.0,
        )
        db_session.add(bar)

    # Insert baseline ATR
    atr_ind = TechnicalIndicator(
        symbol="XAUUSD",
        indicator_name="ATR_14",
        timeframe="H1",
        timestamp=now,
        value_json='{"atr": 5.0}',
    )
    db_session.add(atr_ind)
    await db_session.commit()

    engine = TimesFMEngine({"timesfm": {"enabled": True}})
    forecast = await engine.compute_forecast(db_session, "XAUUSD", timeframe="H1", horizon_steps=24)

    assert forecast is not None
    assert forecast["symbol"] == "XAUUSD"
    assert forecast["horizon_steps"] == 24
    assert "quantiles" in forecast
    assert len(forecast["quantiles"]["q50"]) == 24
    assert forecast["expected_range"] > 0
    assert "quantile_skew" in forecast
    assert "volatility_expansion_ratio" in forecast
    assert len(forecast["reachability_envelope"]) == 24

    # Save to database
    saved = await engine.save_forecast(db_session, forecast)
    await db_session.commit()
    assert saved.id is not None

    # Retrieve from database
    retrieved = await engine.get_latest_forecast(db_session, "XAUUSD", timeframe="H1", max_age_hours=8.0)
    assert retrieved is not None
    assert retrieved["symbol"] == "XAUUSD"
    assert retrieved["expected_range"] == forecast["expected_range"]
    assert retrieved["quantile_skew"] == forecast["quantile_skew"]
