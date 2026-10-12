# ==============================================================================
# File: tests/indicators/test_micro_alpha_zoo.py
# Monika Micro-Alpha Factor Zoo Test Suite
# ==============================================================================

import numpy as np
import pandas as pd
import pytest

from indicators.micro_alpha_zoo import MicroAlphaZoo


@pytest.fixture
def sample_ohlcv():
    np.random.seed(42)
    n = 50
    close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.random.uniform(0.1, 1.0, n)
    low = close - np.random.uniform(0.1, 1.0, n)
    open_ = low + np.random.uniform(0.0, 1.0, n) * (high - low)
    volume = np.random.uniform(1000.0, 5000.0, n)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def test_registry_has_20_factors():
    factors = MicroAlphaZoo.list_factors()
    assert len(factors) == 20
    names = [f.name for f in factors]
    assert "alpha_001" in names
    assert "alpha_002" in names
    assert "alpha_028" in names
    assert "alpha_amihud_illiquidity" in names
    assert "alpha_decay_trend_strength" in names


def test_individual_factor_computations(sample_ohlcv):
    a1 = MicroAlphaZoo.compute_factor("alpha_001", sample_ohlcv)
    assert len(a1) == len(sample_ohlcv)
    assert np.isnan(a1.iloc[0])  # Warmup should be NaN

    a28 = MicroAlphaZoo.compute_factor("alpha_028", sample_ohlcv)
    assert len(a28) == len(sample_ohlcv)

    eff = MicroAlphaZoo.compute_factor("alpha_range_efficiency", sample_ohlcv)
    # Range efficiency is in [0, 1]
    valid_eff = eff.dropna()
    assert (valid_eff >= 0.0).all() and (valid_eff <= 1.0001).all()

    decay = MicroAlphaZoo.compute_factor("alpha_decay_trend_strength", sample_ohlcv)
    assert len(decay) == len(sample_ohlcv)
    assert np.isnan(decay.iloc[0])


def test_compute_all_factors(sample_ohlcv):
    all_df = MicroAlphaZoo.compute_all_factors(sample_ohlcv)
    assert isinstance(all_df, pd.DataFrame)
    assert len(all_df) == len(sample_ohlcv)
    assert all_df.shape[1] >= 20
