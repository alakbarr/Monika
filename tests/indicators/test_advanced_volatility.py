"""
Unit tests for indicators/technical.py (Yang-Zhang volatility, AC1 autocorrelation, is_final bar handling).
"""
import numpy as np
import pandas as pd
import pytest
from indicators.technical import (
    compute_yang_zhang_volatility,
    compute_lag1_autocorrelation,
    TechnicalIndicatorCalculator,
)


def _make_dummy_ohlcv(n: int = 50) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="1h")
    close = 100.0 + np.cumsum(np.random.normal(0, 1, n))
    high = close + np.random.uniform(0.5, 2.0, n)
    low = close - np.random.uniform(0.5, 2.0, n)
    open_p = close + np.random.uniform(-0.5, 0.5, n)
    volume = np.random.uniform(100, 1000, n)

    df = pd.DataFrame(
        {"open": open_p, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )
    return df


def test_yang_zhang_volatility():
    df = _make_dummy_ohlcv(60)
    yz = compute_yang_zhang_volatility(df, window=20)

    assert len(yz) == len(df)
    # First 20 values should have nan/zero, then positive volatility
    valid_vals = yz.dropna()
    assert (valid_vals >= 0.0).all()
    assert valid_vals.iloc[-1] > 0.0


def test_lag1_autocorrelation():
    # Momentum series: positive autocorrelation
    dates = pd.date_range("2025-01-01", periods=50, freq="1h")
    trend = pd.Series(np.linspace(100, 200, 50), index=dates)
    ac1 = compute_lag1_autocorrelation(trend, window=20)

    # Should compute without error and produce float
    assert len(ac1) == 50
    assert not ac1.dropna().empty


def test_is_final_bar_protection():
    df = _make_dummy_ohlcv(30)
    calc = TechnicalIndicatorCalculator(session=None, settings={})

    # With is_final=True, computes all rows
    res_final = calc._compute_all(df, is_final=True)
    assert len(res_final) == len(df)

    # With is_final=False, drops forming bar
    res_provisional = calc._compute_all(df, is_final=False)
    assert len(res_provisional) == len(df) - 1
    assert df.index[-1] not in res_provisional
