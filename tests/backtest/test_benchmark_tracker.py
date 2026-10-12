"""
Unit tests for BenchmarkTracker and Benjamini-Hochberg FDR correction.
"""
import pytest
from backtest.benchmark_tracker import BenchmarkTracker, BenchmarkMetrics
from backtest.statistical_tests import benjamini_hochberg


def test_benchmark_tracker_calculations():
    tracker = BenchmarkTracker(benchmark_symbol="SPX500", ann_factor=252.0)

    # Strategy that moves with beta ~ 1.5 and positive alpha
    bench_returns = [0.01, -0.005, 0.02, -0.01, 0.015, 0.005, -0.02, 0.01]
    strat_returns = [0.015, -0.007, 0.03, -0.012, 0.022, 0.008, -0.025, 0.016]

    metrics = tracker.compute_metrics(strat_returns, bench_returns)

    assert isinstance(metrics, BenchmarkMetrics)
    assert metrics.benchmark_symbol == "SPX500"
    assert metrics.beta > 1.0
    assert metrics.strategy_return_ann_pct > metrics.benchmark_return_ann_pct
    assert metrics.alpha_ann_pct > 0.0
    assert metrics.tracking_error_pct > 0.0
    assert metrics.up_capture_pct > 0.0
    assert metrics.down_capture_pct > 0.0

    d = metrics.to_dict()
    assert "alpha_ann_pct" in d
    assert "beta" in d
    assert "tracking_error_pct" in d


def test_benchmark_tracker_short_series():
    tracker = BenchmarkTracker()
    metrics = tracker.compute_metrics([0.01], [0.01])
    assert metrics.beta == 0.0
    assert metrics.strategy_return_ann_pct == 0.0


def test_benjamini_hochberg_fdr():
    # p-values: 2 strong discoveries, 1 marginal, 2 clear nulls
    # With alpha=0.05 and m=5:
    # rank 1: 0.001 <= 1/5 * 0.05 = 0.01 (OK)
    # rank 2: 0.008 <= 2/5 * 0.05 = 0.02 (OK)
    # rank 3: 0.04 > 3/5 * 0.05 = 0.03 (Not OK)
    # rank 4: 0.25 > 4/5 * 0.05 = 0.04 (Not OK)
    # rank 5: 0.80 > 5/5 * 0.05 = 0.05 (Not OK)
    p_vals = [0.25, 0.001, 0.80, 0.008, 0.04]
    rejected = benjamini_hochberg(p_vals, alpha=0.05)

    assert rejected == [False, True, False, True, False]


def test_benjamini_hochberg_empty():
    assert benjamini_hochberg([]) == []
