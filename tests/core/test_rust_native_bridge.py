# ==============================================================================
# File: tests/core/test_rust_native_bridge.py
# Description: Unit and 100% numerical parity tests for monika_core_rs native accelerator.
# ==============================================================================

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest

import monika.core.native.rust_bridge as rb
from monika.application.backtest.monte_carlo_engine import MonteCarloStressTester
from monika.application.backtest.statistical_tests import probability_of_backtest_overfitting
from monika.core.native.rust_bridge import (
    atr_f64,
    bollinger_bands_f64,
    cscv_pbo_from_chunks_f64,
    donchian_f64,
    ema_f64,
    eval_equity_paths_f64,
    find_fvg_f64,
    find_swing_pivots_f64,
    find_swings_f64,
    is_rust_accelerator_available,
    kyle_lambda_ols_f64,
    rsi_f64,
    sma_f64,
    supertrend_f64,
    tick_rule_cvd_f64,
    vpin_fractional_f64,
)
from monika.domain.indicators.chart_patterns import find_swing_pivots
from monika.domain.indicators.microstructure import compute_kyle_lambda, compute_vpin
from monika.domain.indicators.order_flow import OrderFlowEngine
from monika.domain.indicators.structure import find_fvg, find_swings
from monika.domain.indicators.technical import (
    compute_atr,
    compute_bollinger_bands,
    compute_donchian_channels,
    compute_moving_averages,
    compute_rsi,
    compute_supertrend,
)


@pytest.fixture(autouse=True)
def reset_rust_bridge_state():
    """Ensure rust_bridge initialization cache is fresh between tests."""
    orig_init = rb._LIB_INITIALIZED
    orig_inst = rb._LIB_INSTANCE
    yield
    rb._LIB_INITIALIZED = orig_init
    rb._LIB_INSTANCE = orig_inst


class TestRustNativeBridgeAvailability:
    def test_accelerator_available_by_default(self):
        """Verify compiled shared library loads and reports True by default."""
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        assert is_rust_accelerator_available() is True

    def test_accelerator_disable_environment_variable(self, monkeypatch):
        """Verify MONIKA_DISABLE_RUST_ACCEL=1 disables native loader and forces fallback."""
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        assert is_rust_accelerator_available() is False

        # Direct kernel wrapper calls must return None when disabled
        assert vpin_fractional_f64(np.array([1.0, 2.0]), np.array([10.0, 20.0]), 5.0, 10) is None
        assert kyle_lambda_ols_f64(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0, 3.0]), 3) is None
        assert tick_rule_cvd_f64(np.array([1.0, 2.0]), np.array([10.0, 20.0])) is None
        assert find_swings_f64(np.ones(10), np.ones(10), 2) is None
        assert find_swing_pivots_f64(np.ones(10), np.ones(10), 2) is None
        assert sma_f64(np.ones(10), 3) is None
        assert ema_f64(np.ones(10), 3) is None
        assert rsi_f64(np.ones(10), 3) is None
        assert atr_f64(np.ones(10), np.ones(10), np.ones(10), 3) is None
        assert bollinger_bands_f64(np.ones(10), 3) is None
        assert find_fvg_f64(np.ones(10), np.ones(10), np.ones(10)) is None
        assert donchian_f64(np.ones(10), np.ones(10), 3) is None
        assert supertrend_f64(np.ones(10), np.ones(10), np.ones(10), 3, 3.0) is None


class TestRustNumericalParity:
    def test_vpin_fractional_parity(self, monkeypatch):
        """Verify exact VPIN parity between Rust kernel and Python fallback loop."""
        rng = np.random.default_rng(42)
        n = 500
        prices = 100.0 + np.cumsum(rng.normal(0, 0.2, size=n))
        volumes = rng.uniform(1.0, 10.0, size=n)
        df = pd.DataFrame({"price": prices, "volume": volumes})
        bucket_vol = float(np.sum(volumes) / 20.0)

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        vpin_rust = compute_vpin(df, bucket_volume=bucket_vol, n_buckets=20)

        # 2. Python fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        vpin_fallback = compute_vpin(df, bucket_volume=bucket_vol, n_buckets=20)

        assert math.isclose(vpin_rust, vpin_fallback, rel_tol=1e-12)
        assert 0.0 <= vpin_rust <= 1.0

    def test_kyle_lambda_parity(self, monkeypatch):
        """Verify exact Kyle Lambda OLS parity between Rust and Vectorized NumPy fallback."""
        rng = np.random.default_rng(101)
        n = 300
        p_chg = pd.Series(rng.normal(0, 0.01, size=n))
        s_vol = pd.Series(rng.normal(0, 50.0, size=n))

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        kyle_rust = compute_kyle_lambda(p_chg, s_vol, window=15)

        # 2. NumPy fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        kyle_fallback = compute_kyle_lambda(p_chg, s_vol, window=15)

        np.testing.assert_allclose(kyle_rust.to_numpy(), kyle_fallback.to_numpy(), rtol=1e-12, atol=1e-12)

    @pytest.mark.asyncio
    async def test_order_flow_cvd_parity(self, monkeypatch):
        """Verify OrderFlowEngine CVD calculation parity between Rust and fallback."""
        rng = np.random.default_rng(202)
        n = 200
        closes = 2000.0 + np.cumsum(rng.choice([-0.5, 0.0, 0.5], size=n))
        volumes = rng.uniform(1.0, 5.0, size=n)
        df = pd.DataFrame({"close": closes, "volume": volumes})

        engine = OrderFlowEngine()

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        snap_rust = await engine._compute_tick_rule_cvd_snapshot(df=df, symbol="BTCUSD")

        # 2. NumPy fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        snap_fallback = await engine._compute_tick_rule_cvd_snapshot(df=df, symbol="BTCUSD")

        assert math.isclose(snap_rust.cvd_session_delta, snap_fallback.cvd_session_delta, rel_tol=1e-12)
        assert snap_rust.cvd_divergence == snap_fallback.cvd_divergence
        assert snap_rust.order_book_imbalance == snap_fallback.order_book_imbalance

    def test_find_swings_parity(self, monkeypatch):
        """Verify find_swings DataFrame parity between Rust and Python fallback."""
        rng = np.random.default_rng(303)
        n = 150
        base = 1.1000 + np.cumsum(rng.normal(0, 0.001, size=n))
        df = pd.DataFrame(
            {
                "high": base + rng.uniform(0.0005, 0.002, size=n),
                "low": base - rng.uniform(0.0005, 0.002, size=n),
                "close": base,
            },
            index=pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC"),
        )

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        sh_rust, sl_rust = find_swings(df, swing_window=4)

        # 2. Python fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        sh_fallback, sl_fallback = find_swings(df, swing_window=4)

        pd.testing.assert_frame_equal(sh_rust, sh_fallback)
        pd.testing.assert_frame_equal(sl_rust, sl_fallback)

    def test_find_swing_pivots_parity(self, monkeypatch):
        """Verify find_swing_pivots list parity between Rust and Python fallback."""
        rng = np.random.default_rng(404)
        n = 120
        highs = 100.0 + np.cumsum(rng.normal(0, 0.5, size=n)) + rng.uniform(0.1, 0.5, size=n)
        lows = highs - rng.uniform(0.5, 1.5, size=n)

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        pivots_rust = find_swing_pivots(highs, lows, order=3)

        # 2. Python fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        pivots_fallback = find_swing_pivots(highs, lows, order=3)

        assert pivots_rust == pivots_fallback

    def test_monte_carlo_stress_tester_parity(self, monkeypatch):
        """Verify Monte Carlo simulation metrics parity between Rust path evaluation and NumPy fallback."""
        rng = np.random.default_rng(505)
        returns = rng.normal(0.002, 0.02, size=80).tolist()

        for test_mode in ("permutation", "bootstrap", "block_bootstrap"):
            # 1. Rust mode
            monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
            rb._LIB_INITIALIZED = False
            rb._LIB_INSTANCE = None
            mc_rust = MonteCarloStressTester(seed=42).simulate_trade_sequence(
                returns,
                num_simulations=500,
                initial_equity=10000.0,
                ruin_drawdown_pct=0.30,
                mode=test_mode,
            )

            # 2. NumPy fallback mode
            monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
            rb._LIB_INITIALIZED = False
            rb._LIB_INSTANCE = None
            mc_fallback = MonteCarloStressTester(seed=42).simulate_trade_sequence(
                returns,
                num_simulations=500,
                initial_equity=10000.0,
                ruin_drawdown_pct=0.30,
                mode=test_mode,
            )

            assert mc_rust["is_valid"] is True
            assert mc_rust["num_simulations"] == 500
            assert mc_rust["var_95_drawdown_pct"] == mc_fallback["var_95_drawdown_pct"]
            assert mc_rust["var_99_drawdown_pct"] == mc_fallback["var_99_drawdown_pct"]
            assert mc_rust["median_drawdown_pct"] == mc_fallback["median_drawdown_pct"]
            assert mc_rust["ruin_probability_pct"] == mc_fallback["ruin_probability_pct"]
            assert mc_rust["final_equity_distribution"] == mc_fallback["final_equity_distribution"]

    def test_probability_of_backtest_overfitting_parity(self, monkeypatch):
        """Verify CSCV PBO calculation parity between Rust and Python fallback."""
        rng = np.random.default_rng(606)
        matrix = rng.normal(0.001, 0.02, size=(240, 8))

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        pbo_rust = probability_of_backtest_overfitting(matrix, n_partitions=16, max_combinations=300)

        # 2. Python fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        pbo_fallback = probability_of_backtest_overfitting(matrix, n_partitions=16, max_combinations=300)

        assert pbo_rust["pbo"] == pbo_fallback["pbo"]
        assert pbo_rust["is_overfit"] == pbo_fallback["is_overfit"]
        assert pbo_rust["median_oos_rank"] == pbo_fallback["median_oos_rank"]
        assert pbo_rust["n_combinations"] == pbo_fallback["n_combinations"]

    def test_sma_and_ema_parity(self, monkeypatch):
        """Verify SMA and EMA exact parity between Rust accelerator and fallback."""
        rng = np.random.default_rng(707)
        close = pd.Series(100.0 + np.cumsum(rng.normal(0, 0.5, size=200)))

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        ma_rust = compute_moving_averages(close, sma_periods=(20, 50), ema_periods=(9, 21))

        # 2. Python fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        ma_fallback = compute_moving_averages(close, sma_periods=(20, 50), ema_periods=(9, 21))

        for k in ("SMA_20", "SMA_50", "EMA_9", "EMA_21"):
            np.testing.assert_allclose(ma_rust[k].dropna().values, ma_fallback[k].dropna().values, rtol=1e-10)

    def test_rsi_parity(self, monkeypatch):
        """Verify RSI exact parity between Rust accelerator and fallback."""
        rng = np.random.default_rng(808)
        close = pd.Series(50.0 + np.cumsum(rng.normal(0, 0.3, size=150)))

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        rsi_rust = compute_rsi(close, period=14)

        # 2. Python fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        rsi_fallback = compute_rsi(close, period=14)

        np.testing.assert_allclose(rsi_rust.dropna().values, rsi_fallback.dropna().values, rtol=1e-10)

    def test_atr_parity(self, monkeypatch):
        """Verify ATR exact parity between Rust accelerator and fallback."""
        rng = np.random.default_rng(909)
        close = pd.Series(100.0 + np.cumsum(rng.normal(0, 0.5, size=120)))
        high = close + rng.uniform(0.1, 1.0, size=120)
        low = close - rng.uniform(0.1, 1.0, size=120)

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        atr_rust = compute_atr(high, low, close, period=14)

        # 2. Python fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        atr_fallback = compute_atr(high, low, close, period=14)

        np.testing.assert_allclose(atr_rust.values[14:], atr_fallback.values[14:], rtol=1e-10)

    def test_bollinger_bands_parity(self, monkeypatch):
        """Verify Bollinger Bands exact parity between Rust accelerator and fallback."""
        rng = np.random.default_rng(1010)
        close = pd.Series(100.0 + np.cumsum(rng.normal(0, 0.5, size=150)))

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        bb_rust = compute_bollinger_bands(close, period=20, std_dev=2.0)

        # 2. Python fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        bb_fallback = compute_bollinger_bands(close, period=20, std_dev=2.0)

        for i in range(5):
            np.testing.assert_allclose(bb_rust[i].dropna().values, bb_fallback[i].dropna().values, rtol=1e-10)

    def test_find_fvg_parity(self, monkeypatch):
        """Verify FVG detection parity between Rust accelerator and fallback."""
        rng = np.random.default_rng(1111)
        close = pd.Series(
            100.0 + np.cumsum(rng.normal(0, 1.0, size=100)),
            index=pd.date_range("2025-01-01", periods=100, freq="1h"),
        )
        high = close + rng.uniform(0.2, 1.5, size=100)
        low = close - rng.uniform(0.2, 1.5, size=100)
        open_p = close - rng.normal(0, 0.5, size=100)
        df = pd.DataFrame({"open": open_p, "high": high, "low": low, "close": close}, index=close.index)

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        fvg_rust = find_fvg(df, symbol="EURUSD", timeframe="H1")

        # 2. Python fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        fvg_fallback = find_fvg(df, symbol="EURUSD", timeframe="H1")

        assert len(fvg_rust) == len(fvg_fallback)
        for r, f in zip(fvg_rust, fvg_fallback):
            assert r.formed_at == f.formed_at
            assert r.filled_at == f.filled_at
            assert r.direction == f.direction
            assert math.isclose(r.gap_high, f.gap_high, rel_tol=1e-9)
            assert math.isclose(r.gap_low, f.gap_low, rel_tol=1e-9)

    def test_donchian_channels_parity(self, monkeypatch):
        """Verify Donchian Channels parity between Rust kernel and pandas rolling fallback."""
        rng = np.random.default_rng(2222)
        close = pd.Series(
            100.0 + np.cumsum(rng.normal(0, 0.5, size=150)),
            index=pd.date_range("2025-01-01", periods=150, freq="1h"),
        )
        high = close + rng.uniform(0.1, 1.0, size=150)
        low = close - rng.uniform(0.1, 1.0, size=150)

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        u_rust, m_rust, l_rust = compute_donchian_channels(high, low, close, window=20)

        # 2. Fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        u_fb, m_fb, l_fb = compute_donchian_channels(high, low, close, window=20)

        np.testing.assert_allclose(u_rust.dropna().values, u_fb.dropna().values, rtol=1e-12)
        np.testing.assert_allclose(m_rust.dropna().values, m_fb.dropna().values, rtol=1e-12)
        np.testing.assert_allclose(l_rust.dropna().values, l_fb.dropna().values, rtol=1e-12)

    def test_supertrend_parity(self, monkeypatch):
        """Verify Supertrend and direction parity between Rust kernel and iterative fallback."""
        rng = np.random.default_rng(3333)
        close = pd.Series(
            100.0 + np.cumsum(rng.normal(0, 0.8, size=120)),
            index=pd.date_range("2025-01-01", periods=120, freq="1h"),
        )
        high = close + rng.uniform(0.2, 1.5, size=120)
        low = close - rng.uniform(0.2, 1.5, size=120)

        # 1. Rust mode
        monkeypatch.delenv("MONIKA_DISABLE_RUST_ACCEL", raising=False)
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        st_rust, dir_rust = compute_supertrend(high, low, close, period=10, multiplier=3.0)

        # 2. Fallback mode
        monkeypatch.setenv("MONIKA_DISABLE_RUST_ACCEL", "1")
        rb._LIB_INITIALIZED = False
        rb._LIB_INSTANCE = None
        st_fb, dir_fb = compute_supertrend(high, low, close, period=10, multiplier=3.0)

        np.testing.assert_allclose(st_rust.dropna().values, st_fb.dropna().values, rtol=1e-10)
        np.testing.assert_array_equal(dir_rust.values, dir_fb.values)


class TestRustEdgeCasesAndFailClosed:
    def test_empty_and_short_inputs(self):
        """Test that invalid inputs return None gracefully without segfaults or panics."""
        assert vpin_fractional_f64(np.array([]), np.array([]), 10.0, 10) is None
        assert vpin_fractional_f64(np.array([10.0]), np.array([5.0]), 10.0, 10) is None
        assert vpin_fractional_f64(np.array([10.0, 20.0]), np.array([5.0, 5.0]), -1.0, 10) is None

        assert kyle_lambda_ols_f64(np.array([1.0, 2.0]), np.array([1.0, 2.0]), 5) is None
        assert kyle_lambda_ols_f64(np.array([1.0, 2.0, 3.0]), np.array([1.0, 2.0]), 3) is None

        assert tick_rule_cvd_f64(np.array([]), np.array([])) is None
        assert find_swings_f64(np.array([1.0, 2.0]), np.array([1.0, 2.0]), 5) is None
        assert find_swing_pivots_f64(np.array([1.0, 2.0]), np.array([1.0, 2.0]), 5) is None

        assert eval_equity_paths_f64(np.empty((0, 0)), 10000.0, 0.5) is None
        assert cscv_pbo_from_chunks_f64(np.empty((0, 0)), np.empty((0, 0)), np.array([]), np.empty((0, 0))) is None

    def test_nan_inf_inputs_fail_closed(self):
        """Test that NaN and Inf values fail closed and return None."""
        nan_arr = np.array([1.0, np.nan, 3.0, 4.0])
        valid_arr = np.array([1.0, 2.0, 3.0, 4.0])
        inf_arr = np.array([1.0, np.inf, 3.0, 4.0])

        assert vpin_fractional_f64(nan_arr, valid_arr, 5.0, 10) is None
        assert vpin_fractional_f64(valid_arr, inf_arr, 5.0, 10) is None

        assert kyle_lambda_ols_f64(nan_arr, valid_arr, 3) is None
        assert kyle_lambda_ols_f64(valid_arr, inf_arr, 3) is None

        assert tick_rule_cvd_f64(nan_arr, valid_arr) is None
        assert find_swings_f64(nan_arr, valid_arr, 1) is None
        assert find_swing_pivots_f64(nan_arr, valid_arr, 1) is None
