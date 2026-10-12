import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from indicators.smc_advanced import (
    detect_inducement,
    detect_breaker_blocks,
    detect_judas_swing,
    detect_equal_highs_lows,
    compute_ob_fvg_confluence,
    find_wick_to_wick_fvg,
)


def test_compute_ob_fvg_confluence():
    # Overlapping zones: OB [100, 110], FVG [105, 115] -> overlap [105, 110] = 5.0 -> 50%
    conf = compute_ob_fvg_confluence(110.0, 100.0, 115.0, 105.0)
    assert conf["confluent"] is True
    assert conf["overlap_pct"] == 50.0

    # Non-overlapping zones
    non_conf = compute_ob_fvg_confluence(110.0, 100.0, 130.0, 120.0)
    assert non_conf["confluent"] is False
    assert non_conf["overlap_pct"] == 0.0


def test_detect_equal_highs_lows():
    dates = pd.date_range("2026-01-01", periods=20, freq="1h")
    data = []
    for i, d in enumerate(dates):
        # Create equal highs around 2000.00 at index 5 and index 12
        high = 2000.00 if i in (5, 12) else 1990.0 + (i % 5)
        low = 1980.0
        data.append({"timestamp": d, "open": 1985.0, "high": high, "low": low, "close": 1988.0, "volume": 100})
    df = pd.DataFrame(data)

    pools = detect_equal_highs_lows(df, tolerance_pips=5.0, min_touches=2)
    eqh_pools = [p for p in pools if p.pool_type == "EQH"]
    assert len(eqh_pools) >= 1
    assert eqh_pools[0].touch_count >= 2
    assert abs(eqh_pools[0].price_level - 2000.0) < 0.1


def test_detect_inducement():
    dates = pd.date_range("2026-01-01", periods=10, freq="1h")
    df = pd.DataFrame([{
        "timestamp": d, "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 50
    } for i, d in enumerate(dates)])

    swings = [
        {"type": "high", "price": 105.0, "timestamp": dates[3].isoformat()},
        {"type": "low", "price": 101.0, "timestamp": dates[5].isoformat()},
        {"type": "high", "price": 110.0, "timestamp": dates[8].isoformat()},
    ]

    res = detect_inducement(df, swings, trend="bullish")
    assert res.idm_detected is True
    assert res.idm_price == 101.0


def test_detect_judas_swing():
    # London Open Judas Swing test: 08:00 UTC spikes above Asian High and gets rejected
    dates = pd.date_range("2026-01-01 06:00:00", periods=20, freq="15min", tz="UTC")
    data = []
    asian_high = 2050.0
    asian_low = 2040.0
    for d in dates:
        if d.hour == 8 and d.minute == 0:
            # Trap bar: Spikes to 2055 (above Asian High 2050), closes back inside at 2048
            data.append({"timestamp": d, "open": 2049.0, "high": 2055.0, "low": 2047.0, "close": 2048.0, "volume": 300})
        else:
            data.append({"timestamp": d, "open": 2045.0, "high": 2048.0, "low": 2042.0, "close": 2046.0, "volume": 100})
    df = pd.DataFrame(data)

    res = detect_judas_swing(df, asian_high=asian_high, asian_low=asian_low)
    assert res.judas_detected is True
    assert res.trap_direction == "BEARISH_TRAP"
    assert res.expansion_extreme == 2055.0
