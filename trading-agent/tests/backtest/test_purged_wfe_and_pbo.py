# ==============================================================================
# File: tests/backtest/test_purged_wfe_and_pbo.py
# Monika Purged Walk-Forward & Probability of Backtest Overfitting (PBO) Tests
# ==============================================================================

from datetime import datetime, timezone, timedelta
import numpy as np
import pytest

from backtest.walk_forward_engine import WalkForwardEngine
from backtest.statistical_tests import (
    benjamini_hochberg_adjusted_p,
    probability_of_backtest_overfitting,
)


def test_detect_boundary_leakage():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # 1. Direct temporal overlap
    is_end = base + timedelta(days=90)
    oos_start = base + timedelta(days=85)
    is_leak, msg = WalkForwardEngine.detect_boundary_leakage(is_end, oos_start, purge_days=4)
    assert is_leak is True
    assert "overlap" in msg

    # 2. Insufficient purge gap
    is_end2 = base + timedelta(days=88)
    oos_start2 = base + timedelta(days=90)  # gap = 2 days < 4 days
    is_leak2, msg2 = WalkForwardEngine.detect_boundary_leakage(is_end2, oos_start2, purge_days=4)
    assert is_leak2 is True
    assert "Purge gap violation" in msg2

    # 3. Clean boundary with full 4-day purge gap
    is_end3 = base + timedelta(days=86)
    oos_start3 = base + timedelta(days=90)  # gap = 4 days
    is_leak3, msg3 = WalkForwardEngine.detect_boundary_leakage(is_end3, oos_start3, purge_days=4)
    assert is_leak3 is False
    assert "Clean boundary" in msg3


def test_benjamini_hochberg_adjusted_p():
    raw_p = [0.001, 0.01, 0.04, 0.20, 0.80]
    q_vals = benjamini_hochberg_adjusted_p(raw_p)

    assert len(q_vals) == len(raw_p)
    # Adjusted p-values must be >= raw p-values and <= 1.0
    for p, q in zip(raw_p, q_vals):
        assert q >= p
        assert q <= 1.0

    # First one should remain highly significant
    assert q_vals[0] < 0.01


def test_probability_of_backtest_overfitting_random_noise():
    np.random.seed(42)
    T = 200
    N = 10
    # Pure Gaussian noise: strategies are overfit by construction
    noise_returns = np.random.randn(T, N) * 0.01

    res = probability_of_backtest_overfitting(noise_returns, n_partitions=8, max_combinations=70)
    assert "pbo" in res
    assert 0.0 <= res["pbo"] <= 1.0
    # Over pure random noise, PBO is substantial
    assert res["pbo"] >= 0.30
    assert res["n_combinations"] > 0


def test_probability_of_backtest_overfitting_dominant_alpha():
    np.random.seed(42)
    T = 200
    N = 10
    # Strategy 0 has persistent positive drift (+0.05 per bar with small variance)
    returns = np.random.randn(T, N) * 0.01
    returns[:, 0] += 0.05

    res = probability_of_backtest_overfitting(returns, n_partitions=8, max_combinations=70)
    # Dominant true alpha should have low PBO and high median OOS rank
    assert res["pbo"] <= 0.10
    assert res["is_overfit"] is False
    assert res["median_oos_rank"] >= 0.90
