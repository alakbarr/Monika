"""
Unit tests for backtest/statistical_tests.py (PSR, E[max], DSR, sample moments).
"""
import pytest
from backtest.statistical_tests import (
    probabilistic_sharpe_ratio,
    expected_max_sharpe,
    deflated_sharpe_ratio,
    compute_sample_moments,
)


def test_probabilistic_sharpe_ratio_normal():
    # Observed Sharpe = 1.5, benchmark = 0, n_obs = 100
    psr = probabilistic_sharpe_ratio(observed_sr=1.5, benchmark_sr=0.0, n_obs=100)
    assert 0.99 <= psr <= 1.0

    # Negative Sharpe against 0 benchmark
    psr_neg = probabilistic_sharpe_ratio(observed_sr=-0.5, benchmark_sr=0.0, n_obs=100)
    assert psr_neg < 0.05

    # Exactly matching benchmark
    psr_eq = probabilistic_sharpe_ratio(observed_sr=1.0, benchmark_sr=1.0, n_obs=100)
    assert abs(psr_eq - 0.5) < 1e-4


def test_probabilistic_sharpe_ratio_edge_cases():
    # Too few observations
    assert probabilistic_sharpe_ratio(observed_sr=2.0, n_obs=2) == 0.5

    # Fat-tail negative skew
    psr_skew = probabilistic_sharpe_ratio(
        observed_sr=1.0, benchmark_sr=0.0, n_obs=100, skew=-1.5, excess_kurt=4.0
    )
    assert 0.0 < psr_skew < 1.0


def test_expected_max_sharpe():
    # 1 trial = 0.0
    assert expected_max_sharpe(n_trials=1) == 0.0

    # Multiple trials monotonic increase
    e_10 = expected_max_sharpe(n_trials=10, sr_std=0.5)
    e_100 = expected_max_sharpe(n_trials=100, sr_std=0.5)
    e_1000 = expected_max_sharpe(n_trials=1000, sr_std=0.5)

    assert 0.0 < e_10 < e_100 < e_1000


def test_deflated_sharpe_ratio():
    # Single trial DSR equals PSR against 0.0
    dsr_1 = deflated_sharpe_ratio(observed_sr=1.2, n_trials=1, n_obs=50)
    psr_1 = probabilistic_sharpe_ratio(observed_sr=1.2, benchmark_sr=0.0, n_obs=50)
    assert abs(dsr_1 - psr_1) < 1e-5

    # When 50 trials tested, DSR drops because E[max] is positive
    dsr_50 = deflated_sharpe_ratio(observed_sr=1.2, n_trials=50, n_obs=50, sr_std=0.5)
    assert dsr_50 < dsr_1


def test_compute_sample_moments():
    data = [0.01, 0.02, -0.01, 0.03, -0.02, 0.01, 0.0]
    mean, std, skew, kurt = compute_sample_moments(data)
    assert abs(mean - (sum(data) / len(data))) < 1e-6
    assert std > 0.0

    # Constant data
    m_const, s_const, sk_const, k_const = compute_sample_moments([0.05, 0.05, 0.05])
    assert s_const == 0.0
    assert sk_const == 0.0


def test_bailey_lopez_de_prado_variance_term():
    """Verify variance adjustment term includes the +0.5*SR^2 component from Bailey & Lopez de Prado (2012)."""
    import math
    import statistics
    norm = statistics.NormalDist(0.0, 1.0)

    # For Gaussian distribution: skew=0, excess_kurt=0
    # var_term = 1 - 0 + ((0 + 2)/4)*SR^2 = 1 + 0.5*SR^2
    # With SR=2.0: var_term = 1 + 0.5*4 = 3.0
    # se = sqrt(3.0 / 99)
    # z = 2.0 / sqrt(3.0 / 99)
    sr = 2.0
    n_obs = 100
    expected_var = 1.0 + 0.5 * (sr ** 2)  # 3.0
    expected_se = math.sqrt(expected_var / (n_obs - 1))
    expected_z = sr / expected_se
    expected_psr = norm.cdf(expected_z)

    actual_psr = probabilistic_sharpe_ratio(observed_sr=sr, benchmark_sr=0.0, n_obs=n_obs, skew=0.0, excess_kurt=0.0)
    assert abs(actual_psr - expected_psr) < 1e-6
