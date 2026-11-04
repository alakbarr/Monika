# ==============================================================================
# File: tests/core/test_polars_bridge.py
# Description: Unit and Property-Based Tests for PolarsBridge & Arrow Interop
# ==============================================================================

from datetime import datetime, timezone
import numpy as np
import pandas as pd
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from monika.core.dataframe.polars_bridge import (
    CANONICAL_OHLCV_SCHEMA,
    PolarsBridge,
    is_polars,
    to_pandas,
    to_polars,
)
from monika.domain.market.candle_ring_buffer import CANDLE_DTYPE


def test_is_polars():
    df_pl = pl.DataFrame({"a": [1, 2, 3]})
    s_pl = pl.Series("b", [4, 5, 6])
    lf_pl = df_pl.lazy()
    df_pd = pd.DataFrame({"a": [1, 2, 3]})

    assert is_polars(df_pl) is True
    assert is_polars(s_pl) is True
    assert is_polars(lf_pl) is True
    assert is_polars(df_pd) is False
    assert is_polars([1, 2, 3]) is False


def test_to_polars_from_pandas_datetime_index():
    ts = pd.date_range("2026-01-01", periods=5, freq="1h", tz="UTC")
    df_pd = pd.DataFrame(
        {
            "open": [1.1, 1.2, 1.3, 1.4, 1.5],
            "high": [1.2, 1.3, 1.4, 1.5, 1.6],
            "low": [1.0, 1.1, 1.2, 1.3, 1.4],
            "close": [1.15, 1.25, 1.35, 1.45, 1.55],
            "volume": [100.0, 200.0, 300.0, 400.0, 500.0],
        },
        index=ts,
    )
    df_pd.index.name = "timestamp"

    pl_df = to_polars(df_pd)
    assert isinstance(pl_df, pl.DataFrame)
    assert len(pl_df) == 5
    assert "timestamp" in pl_df.columns
    assert pl_df["timestamp"].dtype == pl.Datetime("us", "UTC")
    assert pl_df["close"].to_list() == [1.15, 1.25, 1.35, 1.45, 1.55]


def test_to_polars_from_structured_numpy():
    arr = np.zeros(3, dtype=CANDLE_DTYPE)
    arr["timestamp"] = [1704067200, 1704070800, 1704074400]  # epoch seconds
    arr["open"] = [10.0, 20.0, 30.0]
    arr["high"] = [11.0, 21.0, 31.0]
    arr["low"] = [9.0, 19.0, 29.0]
    arr["close"] = [10.5, 20.5, 30.5]
    arr["volume"] = [1000.0, 2000.0, 3000.0]

    pl_df = to_polars(arr)
    assert isinstance(pl_df, pl.DataFrame)
    assert len(pl_df) == 3
    assert pl_df["timestamp"].dtype == pl.Datetime("us", "UTC")
    assert pl_df["open"].to_list() == [10.0, 20.0, 30.0]
    assert pl_df["volume"].to_list() == [1000.0, 2000.0, 3000.0]


def test_to_polars_empty():
    empty_pd = pd.DataFrame()
    pl_df = to_polars(empty_pd)
    assert isinstance(pl_df, pl.DataFrame)
    assert len(pl_df) == 0
    assert set(pl_df.columns) == set(CANONICAL_OHLCV_SCHEMA.keys())


def test_to_pandas_roundtrip():
    ts = pd.date_range("2026-01-01", periods=10, freq="15min", tz="UTC")
    df_pd = pd.DataFrame(
        {
            "open": np.linspace(100, 110, 10),
            "high": np.linspace(101, 111, 10),
            "low": np.linspace(99, 109, 10),
            "close": np.linspace(100.5, 110.5, 10),
            "volume": np.linspace(500, 1500, 10),
        },
        index=ts,
    )
    df_pd.index.name = "timestamp"

    # Convert to Polars and back
    pl_df = to_polars(df_pd)
    restored_pd = to_pandas(pl_df, set_datetime_index=True)

    assert isinstance(restored_pd, pd.DataFrame)
    assert len(restored_pd) == 10
    assert isinstance(restored_pd.index, pd.DatetimeIndex)
    np.testing.assert_allclose(restored_pd["close"].values, df_pd["close"].values)
    np.testing.assert_allclose(restored_pd["volume"].values, df_pd["volume"].values)


@settings(max_examples=25, deadline=None)
@given(
    prices=st.lists(
        st.floats(min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False),
        min_size=5,
        max_size=50,
    )
)
def test_hypothesis_roundtrip_numerical_identity(prices):
    n = len(prices)
    ts = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    df_pd = pd.DataFrame(
        {
            "open": prices,
            "high": [p * 1.01 for p in prices],
            "low": [p * 0.99 for p in prices],
            "close": prices,
            "volume": [100.0] * n,
        },
        index=ts,
    )
    df_pd.index.name = "timestamp"

    pl_df = to_polars(df_pd)
    recovered = to_pandas(pl_df)

    assert len(recovered) == n
    np.testing.assert_allclose(recovered["close"].values, df_pd["close"].values, rtol=1e-6)
    np.testing.assert_allclose(recovered["open"].values, df_pd["open"].values, rtol=1e-6)
