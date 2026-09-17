"""
Unit tests for indicators/microstructure.py (VPIN, Kyle's Lambda, Amihud, asset routing).
"""
import numpy as np
import pandas as pd
import pytest
from indicators.microstructure import (
    compute_vpin,
    compute_amihud_illiquidity,
    compute_kyle_lambda,
    get_microstructure_metrics,
)


def test_compute_vpin():
    # Synthetic trades DataFrame
    np.random.seed(42)
    n = 100
    prices = 100.0 + np.cumsum(np.random.normal(0, 0.5, n))
    volumes = np.random.uniform(1, 10, n)
    trades_df = pd.DataFrame({"price": prices, "volume": volumes})

    vpin = compute_vpin(trades_df, bucket_volume=10.0, n_buckets=10)
    assert 0.0 <= vpin <= 1.0


def test_compute_amihud_illiquidity():
    dates = pd.date_range("2025-01-01", periods=30, freq="1h")
    rets = pd.Series(np.random.normal(0, 0.01, 30), index=dates)
    vol = pd.Series(np.random.uniform(1000, 5000, 30), index=dates)

    amihud = compute_amihud_illiquidity(rets, vol, window=10)
    assert len(amihud) == 30
    assert (amihud >= 0.0).all()


def test_compute_kyle_lambda():
    dates = pd.date_range("2025-01-01", periods=30, freq="1h")
    p_chg = pd.Series(np.random.normal(0, 1.0, 30), index=dates)
    signed_vol = pd.Series(np.random.normal(0, 50.0, 30), index=dates)

    kyle = compute_kyle_lambda(p_chg, signed_vol, window=10)
    assert len(kyle) == 30
    assert not kyle.dropna().empty


def test_get_microstructure_metrics_asset_routing():
    dates = pd.date_range("2025-01-01", periods=25, freq="1h")
    ohlcv = pd.DataFrame({
        "open": np.linspace(100, 105, 25),
        "high": np.linspace(101, 106, 25),
        "low": np.linspace(99, 104, 25),
        "close": np.linspace(100.5, 105.5, 25),
        "volume": np.random.uniform(100, 500, 25),
    }, index=dates)

    trades = pd.DataFrame({
        "price": np.linspace(2600, 2610, 30),
        "volume": np.random.uniform(1, 5, 30),
    })

    # BTCUSD -> VPIN
    btc_metrics = get_microstructure_metrics("BTCUSD", trades_df=trades, ohlcv_df=ohlcv)
    assert "vpin" in btc_metrics
    assert "kyle_lambda" not in btc_metrics

    # EURUSD -> Kyle Lambda
    fx_metrics = get_microstructure_metrics("EURUSD", trades_df=trades, ohlcv_df=ohlcv)
    assert "kyle_lambda" in fx_metrics
    assert "vpin" not in fx_metrics

    # XTIUSD -> Amihud
    oil_metrics = get_microstructure_metrics("XTIUSD", trades_df=trades, ohlcv_df=ohlcv)
    assert "amihud_illiquidity" in oil_metrics
    assert "kyle_lambda" not in oil_metrics
