# ==============================================================================
# File: tests/application/test_matrix_alignment_polars.py
# Description: Tests for Polars-Accelerated Multi-Asset Matrix Alignment
# ==============================================================================

import numpy as np
import pandas as pd
import pytest

from monika.application.backtest.matrix_alignment import (
    AlignedMarketMatrix,
    MatrixAlignmentEngine,
)


def test_matrix_alignment_multi_instrument():
    dates1 = pd.date_range("2026-01-01 00:00", periods=50, freq="1h", tz="UTC")
    dates2 = pd.date_range("2026-01-01 02:00", periods=50, freq="1h", tz="UTC")

    df1 = pd.DataFrame(
        {
            "open": np.linspace(100, 150, 50),
            "high": np.linspace(101, 151, 50),
            "low": np.linspace(99, 149, 50),
            "close": np.linspace(100.5, 150.5, 50),
            "volume": np.linspace(10, 50, 50),
        },
        index=dates1,
    )
    df1.index.name = "timestamp"

    df2 = pd.DataFrame(
        {
            "open": np.linspace(2000, 2500, 50),
            "high": np.linspace(2010, 2510, 50),
            "low": np.linspace(1990, 2490, 50),
            "close": np.linspace(2005, 2505, 50),
            "volume": np.linspace(500, 1000, 50),
        },
        index=dates2,
    )
    df2.index.name = "timestamp"

    matrix = MatrixAlignmentEngine.align_dataframes({"EURUSD": df1, "BTCUSD": df2})

    assert isinstance(matrix, AlignedMarketMatrix)
    assert matrix.instruments == ("BTCUSD", "EURUSD")
    assert matrix.close.shape[1] == 2
    # 50 hours starting at 00:00 and 50 hours starting at 02:00 -> total 52 hours
    assert matrix.shape[0] == 52

    # Volume for untraded bars must be 0.0, price must be NaN
    # BTC starts at 02:00, so first 2 bars for BTC (col 0) must be NaN price and 0.0 volume
    assert np.isnan(matrix.open[0, 0])
    assert np.isnan(matrix.close[0, 0])
    assert matrix.volume[0, 0] == 0.0

    # EUR starts at 00:00, so first bar for EUR (col 1) must be valid
    assert matrix.close[0, 1] == 100.5
    assert matrix.volume[0, 1] == 10.0


def test_matrix_alignment_empty_or_invalid():
    with pytest.raises(ValueError, match="df_dict cannot be empty"):
        MatrixAlignmentEngine.align_dataframes({})

    with pytest.raises(ValueError, match="No valid timestamps found"):
        MatrixAlignmentEngine.align_dataframes({"EURUSD": pd.DataFrame()})


def test_matrix_alignment_get_bar_dict():
    dates = pd.date_range("2026-01-01", periods=10, freq="1h", tz="UTC")
    df = pd.DataFrame(
        {
            "open": [10.0] * 10,
            "high": [12.0] * 10,
            "low": [8.0] * 10,
            "close": [11.0] * 10,
            "volume": [100.0] * 10,
        },
        index=dates,
    )
    df.index.name = "timestamp"

    matrix = MatrixAlignmentEngine.align_dataframes({"XAUUSD": df})
    bar = matrix.get_bar_dict(0, "XAUUSD")

    assert bar is not None
    assert bar["open"] == 10.0
    assert bar["close"] == 11.0
    assert bar["volume"] == 100.0
    assert matrix.get_bar_dict(0, "UNKNOWN") is None
