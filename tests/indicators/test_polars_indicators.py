# ==============================================================================
# File: tests/indicators/test_polars_indicators.py
# ==============================================================================

from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl
import pytest

from monika.domain.indicators.classic import (
    compute_adx,
    compute_atr,
    compute_bollinger_bands,
    compute_macd,
    compute_moving_averages,
    compute_rsi,
    compute_stochastic,
    compute_yang_zhang_volatility,
)
from monika.domain.indicators.polars_indicators import (
    compute_adx_polars,
    compute_atr_polars,
    compute_bollinger_bands_polars,
    compute_ema_polars,
    compute_macd_polars,
    compute_rsi_polars,
    compute_sma_polars,
    compute_stochastic_polars,
    compute_yang_zhang_polars,
)
from monika.domain.market.candle_ring_buffer import CandleRingBuffer, RingBufferHub
from monika.domain.market.market_data_bus import MarketDataBus


@pytest.fixture
def sample_ohlcv_arrays():
    np.random.seed(42)
    n = 100
    base = 100.0
    returns = np.random.normal(0, 0.01, size=n)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + np.abs(np.random.normal(0, 0.005, size=n)))
    low = close * (1 - np.abs(np.random.normal(0, 0.005, size=n)))
    open_ = (high + low) / 2.0
    volume = np.random.uniform(100, 1000, size=n)
    return open_, high, low, close, volume


def test_candle_ring_buffer_to_polars(sample_ohlcv_arrays):
    open_, high, low, close, volume = sample_ohlcv_arrays
    buf = CandleRingBuffer(capacity=200)

    for i in range(len(close)):
        ts = 1700000000.0 + i * 60.0
        buf.append_or_update(ts, open_[i], high[i], low[i], close[i], volume[i])

    assert len(buf) == 100
    df_pl = buf.to_polars()
    assert isinstance(df_pl, pl.DataFrame)
    assert len(df_pl) == 100
    assert set(df_pl.columns) == {"timestamp", "open", "high", "low", "close", "volume"}
    assert df_pl["close"][-1] == pytest.approx(close[-1])

    # Check latest timestamp property
    assert buf.latest_timestamp is not None
    assert buf.latest_timestamp == int(1700000000.0 + 99 * 60.0)

    # Hub integration
    hub = RingBufferHub()
    hub.get_buffer("EURUSD", "M1").append_or_update(1700000000.0, 1.1, 1.2, 1.0, 1.15, 50.0)
    hub_pl = hub.get_latest_polars("EURUSD", "M1", count=10)
    assert hub_pl is not None
    assert len(hub_pl) == 1
    assert hub.get_latest_timestamp("EURUSD", "M1") == 1700000000


def test_market_data_bus_polars():
    bus = MarketDataBus()
    now_ts = 1700000000.0
    records = [{"timestamp": now_ts, "open": 1.25, "high": 1.26, "low": 1.24, "close": 1.255, "volume": 200.0}]
    bus.seed_from_records("GBPUSD", "H1", records)

    df_pl = bus.get_candles_polars("GBPUSD", "H1", count=10)
    assert df_pl is not None
    assert len(df_pl) == 1
    assert df_pl["close"][0] == pytest.approx(1.255)
    assert bus.get_latest_timestamp("GBPUSD", "H1") == int(now_ts)


def test_polars_indicators_primitives(sample_ohlcv_arrays):
    open_, high, low, close, volume = sample_ohlcv_arrays
    df_pl = pl.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )

    # SMA & EMA
    sma = compute_sma_polars(df_pl["close"], period=20)
    assert len(sma) == 100
    assert np.isnan(sma[0])
    assert not np.isnan(sma[19])

    ema = compute_ema_polars(df_pl["close"], period=20)
    assert len(ema) == 100
    assert not np.isnan(ema[19])

    # RSI
    rsi = compute_rsi_polars(df_pl["close"], period=14)
    assert len(rsi) == 100
    valid_rsi = rsi.to_numpy()
    valid_rsi = valid_rsi[~np.isnan(valid_rsi)]
    assert np.all(valid_rsi >= 0.0) and np.all(valid_rsi <= 100.0)

    # Stochastic
    stoch_df = compute_stochastic_polars(df_pl, k_period=14, d_period=3)
    assert len(stoch_df) == 100
    assert "stoch_k" in stoch_df.columns
    assert "stoch_d" in stoch_df.columns

    # ATR
    atr = compute_atr_polars(df_pl, period=14)
    assert len(atr) == 100
    valid_atr = atr.to_numpy()
    valid_atr = valid_atr[~np.isnan(valid_atr)]
    assert np.all(valid_atr >= 0.0)

    # Bollinger Bands
    bb_df = compute_bollinger_bands_polars(df_pl["close"], period=20, num_std=2.0)
    assert len(bb_df) == 100
    valid_mask = ~np.isnan(bb_df["upper"].to_numpy())
    assert np.all(bb_df["upper"].to_numpy()[valid_mask] >= bb_df["lower"].to_numpy()[valid_mask])

    # MACD
    macd_df = compute_macd_polars(df_pl["close"], fast=12, slow=26, signal=9)
    assert len(macd_df) == 100
    assert "macd" in macd_df.columns
    assert "macd_signal" in macd_df.columns
    assert "macd_diff" in macd_df.columns

    # Yang-Zhang
    yz = compute_yang_zhang_polars(df_pl, window=20)
    assert len(yz) == 100
    valid_yz = yz.to_numpy()
    valid_yz = valid_yz[~np.isnan(valid_yz)]
    assert np.all(valid_yz >= 0.0)

    # ADX
    adx_df = compute_adx_polars(df_pl, period=14)
    assert len(adx_df) == 100
    valid_adx = adx_df["adx"].to_numpy()
    valid_adx = valid_adx[~np.isnan(valid_adx)]
    assert np.all(valid_adx >= 0.0) and np.all(valid_adx <= 100.0)


def test_classic_indicators_backward_compatibility(sample_ohlcv_arrays):
    open_, high, low, close, volume = sample_ohlcv_arrays
    dates = pd.date_range("2024-01-01", periods=100, freq="1h")
    df = pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=dates,
    )

    # MA
    mas = compute_moving_averages(df["close"], sma_periods=(20,), ema_periods=(21,))
    assert "SMA_20" in mas
    assert "EMA_21" in mas
    assert isinstance(mas["SMA_20"], pd.Series)
    assert len(mas["SMA_20"]) == 100

    # RSI
    rsi_s = compute_rsi(df["close"], period=14)
    assert isinstance(rsi_s, pd.Series)
    assert len(rsi_s) == 100

    # Stochastic
    k_s, d_s = compute_stochastic(df["high"], df["low"], df["close"])
    assert isinstance(k_s, pd.Series)
    assert isinstance(d_s, pd.Series)
    assert len(k_s) == 100

    # MACD
    m, s, h = compute_macd(df["close"])
    assert isinstance(m, pd.Series)
    assert isinstance(s, pd.Series)
    assert isinstance(h, pd.Series)

    # Bollinger Bands
    u, m, l, p, w = compute_bollinger_bands(df["close"], period=20, std_dev=2.0)
    assert isinstance(u, pd.Series)
    assert isinstance(p, pd.Series)

    # ATR
    atr_s = compute_atr(df["high"], df["low"], df["close"], period=14)
    assert isinstance(atr_s, pd.Series)
    assert len(atr_s) == 100

    # ADX
    adx_s, pdi_s, ndi_s = compute_adx(df["high"], df["low"], df["close"], period=14)
    assert isinstance(adx_s, pd.Series)
    assert isinstance(pdi_s, pd.Series)
    assert isinstance(ndi_s, pd.Series)
    assert len(adx_s) == 100

    # Yang-Zhang
    yz_s = compute_yang_zhang_volatility(df, window=20)
    assert isinstance(yz_s, pd.Series)
    assert len(yz_s) == 100
