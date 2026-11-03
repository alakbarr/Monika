# ==============================================================================
# File: tests/core/test_rust_kernels_parity.py
# Description: Parity and invariant verification for Rust C-ABI kernels and NumPy fallbacks.
# ==============================================================================

import numpy as np
import pandas as pd
import pytest

from monika.application.backtest.monte_carlo_engine import MonteCarloStressTester
from monika.core.native.rust_bridge import (
    decay_linear_f64,
    is_rust_accelerator_available,
    monte_carlo_simulate_f64,
    rolling_corr_f64,
    ts_rank_f64,
)
from monika.domain.indicators.factor_primitives import decay_linear, ts_corr, ts_rank


def test_rust_accelerator_available():
    """Verify that monika_core_rs compiled DLL/so is loadable."""
    assert is_rust_accelerator_available() is True


def test_ts_rank_parity():
    np.random.seed(42)
    # 100 observations, window 10
    raw = np.random.randn(100)
    # Insert NaN at position 25 to test strict NaN propagation
    raw[25] = np.nan

    s = pd.Series(raw)
    rust_out = ts_rank_f64(raw, 10)
    assert rust_out is not None

    py_out = ts_rank(s, 10).to_numpy()

    # Verify warmup NaN
    assert np.isnan(rust_out[:9]).all()
    assert np.isnan(py_out[:9]).all()

    # Compare finite values
    valid_mask = ~np.isnan(rust_out) & ~np.isnan(py_out)
    assert np.sum(valid_mask) > 50
    np.testing.assert_allclose(rust_out[valid_mask], py_out[valid_mask], rtol=1e-12, atol=1e-12)

    # Verify strict NaN propagation at window containing position 25
    for t in range(25, 35):
        assert np.isnan(rust_out[t])
        assert np.isnan(py_out[t])


def test_decay_linear_parity():
    np.random.seed(123)
    raw = np.random.uniform(10.0, 50.0, size=80)
    raw[40] = np.nan

    s = pd.Series(raw)
    rust_out = decay_linear_f64(raw, 5)
    assert rust_out is not None

    py_out = decay_linear(s, 5).to_numpy()

    # Verify warmup NaN
    assert np.isnan(rust_out[:4]).all()
    assert np.isnan(py_out[:4]).all()

    # Compare finite values
    valid_mask = ~np.isnan(rust_out) & ~np.isnan(py_out)
    assert np.sum(valid_mask) > 50
    np.testing.assert_allclose(rust_out[valid_mask], py_out[valid_mask], rtol=1e-12, atol=1e-12)

    # Verify strict NaN propagation
    for t in range(40, 45):
        assert np.isnan(rust_out[t])
        assert np.isnan(py_out[t])


def test_rolling_corr_parity():
    np.random.seed(456)
    x = np.random.randn(90)
    y = x * 0.7 + np.random.randn(90) * 0.3
    x[30] = np.nan

    s_x = pd.Series(x)
    s_y = pd.Series(y)

    rust_out = rolling_corr_f64(x, y, 10)
    assert rust_out is not None

    py_out = ts_corr(s_x, s_y, 10).to_numpy()

    # Verify warmup NaN
    assert np.isnan(rust_out[:9]).all()
    assert np.isnan(py_out[:9]).all()

    # Compare finite values
    valid_mask = ~np.isnan(rust_out) & ~np.isnan(py_out)
    assert np.sum(valid_mask) > 50
    np.testing.assert_allclose(rust_out[valid_mask], py_out[valid_mask], rtol=1e-7, atol=1e-7)

    # Test constant series in window returns NaN without error
    const_x = np.ones(20)
    const_y = np.arange(20, dtype=float)
    rust_const = rolling_corr_f64(const_x, const_y, 5)
    assert rust_const is not None
    assert np.isnan(rust_const).all()


def test_monte_carlo_simulate_determinism():
    returns = np.array([0.01, -0.005, 0.02, -0.01, 0.015, -0.02, 0.008, 0.03, -0.012, 0.005])
    res1 = monte_carlo_simulate_f64(
        returns,
        num_simulations=500,
        initial_equity=10000.0,
        ruin_drawdown_pct=0.30,
        mode_code=0,
        block_size=3,
        seed=42,
    )
    res2 = monte_carlo_simulate_f64(
        returns,
        num_simulations=500,
        initial_equity=10000.0,
        ruin_drawdown_pct=0.30,
        mode_code=0,
        block_size=3,
        seed=42,
    )
    assert res1 is not None and res2 is not None
    max_dds1, final_eqs1, ruin1 = res1
    max_dds2, final_eqs2, ruin2 = res2

    np.testing.assert_array_equal(max_dds1, max_dds2)
    np.testing.assert_array_equal(final_eqs1, final_eqs2)
    assert ruin1 == ruin2


def test_monte_carlo_stress_tester_integration():
    tester = MonteCarloStressTester(seed=42)
    trade_returns = [0.02, -0.01, 0.015, -0.005, 0.03, -0.02, 0.01, -0.008, 0.025, -0.015]
    result = tester.simulate_trade_sequence(
        trade_returns,
        num_simulations=1000,
        initial_equity=10000.0,
        ruin_drawdown_pct=0.40,
        mode="bootstrap",
    )
    assert result["is_valid"] is True
    assert result["num_simulations"] == 1000
    assert result["var_95_drawdown_pct"] >= 0.0
    assert result["max_simulated_dd_pct"] >= result["var_95_drawdown_pct"]
    assert "median_p50" in result["final_equity_distribution"]
