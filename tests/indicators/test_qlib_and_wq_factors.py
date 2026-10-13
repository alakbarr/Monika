"""
Tests for vectorized Qlib158 factors and safe WorldQuant 101 factor primitives.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from monika.domain.indicators.alpha_zoo.qlib158 import _calc_resi_rsqr
from monika.domain.indicators.alpha_zoo.factors.worldquant_101.wq_alpha_002 import compute as compute_alpha_002


def test_qlib158_resi_rsqr_perfect_linear():
    """Verify vectorized _calc_resi_rsqr calculates exact slope/residual/r2 on linear trend."""
    window = 10
    n = 30
    # Perfect linear trend: close = 3 * t + 10
    t = np.arange(n, dtype=np.float64)
    close = 3.0 * t + 10.0
    df = pd.DataFrame({"close": close})

    resi, rsqr = _calc_resi_rsqr(df, window)

    assert len(resi) == n
    assert len(rsqr) == n
    # First window - 1 elements must be NaN
    assert resi.iloc[: window - 1].isna().all()
    assert rsqr.iloc[: window - 1].isna().all()

    # For perfect linear trend, residual should be ~0.0 and R^2 should be ~1.0
    valid_resi = resi.iloc[window - 1 :]
    valid_rsqr = rsqr.iloc[window - 1 :]

    np.testing.assert_allclose(valid_resi.values, 0.0, atol=1e-8)
    np.testing.assert_allclose(valid_rsqr.values, 1.0, atol=1e-8)


def test_qlib158_resi_rsqr_with_nan_and_short_series():
    """Verify _calc_resi_rsqr handles series shorter than window and NaN entries."""
    window = 5
    # Short series
    short_df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
    resi_short, rsqr_short = _calc_resi_rsqr(short_df, window)
    assert resi_short.isna().all()
    assert rsqr_short.isna().all()

    # Series with embedded NaN
    close = np.array([10.0, 11.0, np.nan, 13.0, 14.0, 15.0, 16.0], dtype=np.float64)
    df_nan = pd.DataFrame({"close": close})
    resi, rsqr = _calc_resi_rsqr(df_nan, window)

    # Windows spanning index 2 (the NaN) must evaluate to NaN
    # Window 0..4 (ends at idx 4) spans idx 2 -> NaN
    assert np.isnan(resi.iloc[4])
    assert np.isnan(rsqr.iloc[4])
    # Window 2..6 (ends at idx 6) spans idx 2 -> NaN
    assert np.isnan(resi.iloc[6])
    assert np.isnan(rsqr.iloc[6])


def test_wq_alpha_002_safeguard_zero_volume_and_open():
    """Verify wq_alpha_002 executes cleanly when volume or open contains zeros."""
    dates = pd.date_range("2026-01-01", periods=20, freq="1D")
    tickers = ["EURUSD", "GBPUSD"]

    # Wide DataFrames
    close = pd.DataFrame(np.random.uniform(1.0, 1.2, size=(20, 2)), index=dates, columns=tickers)
    open_ = pd.DataFrame(np.random.uniform(1.0, 1.2, size=(20, 2)), index=dates, columns=tickers)
    # Zero volume in several rows
    volume = pd.DataFrame(np.zeros((20, 2)), index=dates, columns=tickers)

    panel = {
        "close": close,
        "open": open_,
        "volume": volume,
    }

    result = compute_alpha_002(panel)
    assert isinstance(result, pd.DataFrame)
    assert result.shape == (20, 2)
    # Should not produce runtime warnings or infs
    assert not np.isinf(result.to_numpy()).any()
