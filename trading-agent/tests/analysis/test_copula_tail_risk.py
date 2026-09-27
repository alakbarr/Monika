# ==============================================================================
# File: tests/analysis/test_copula_tail_risk.py
# Monika Copula Tail Risk Engine Test Suite
# ==============================================================================

import numpy as np
import pandas as pd
import pytest

from analysis.calculators.copula_tail_risk import (
    empirical_cdf,
    clayton_copula_cdf,
    gumbel_copula_cdf,
    fit_copula_from_tau,
    evaluate_joint_tail_risk,
)


def test_empirical_cdf():
    series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    u = empirical_cdf(series)
    assert len(u) == 5
    assert (u > 0.0).all() and (u < 1.0).all()
    # Rank ordering should be strictly monotonic
    assert np.all(np.diff(u) > 0)


def test_clayton_copula_cdf_boundaries():
    theta = 2.0
    # C(u, 1) should equal u
    val_u = clayton_copula_cdf(0.4, 1.0, theta)
    assert val_u == pytest.approx(0.4, abs=1e-4)

    # C(0, v) should equal 0
    val_zero = clayton_copula_cdf(1e-10, 0.5, theta)
    assert val_zero == pytest.approx(0.0, abs=1e-4)

    with pytest.raises(ValueError):
        clayton_copula_cdf(0.5, 0.5, -1.0)


def test_gumbel_copula_cdf_boundaries():
    theta = 2.0
    # C(1, 1) should equal 1
    val_one = gumbel_copula_cdf(0.9999, 0.9999, theta)
    assert val_one == pytest.approx(1.0, abs=1e-3)

    # C(u, 1) should equal u
    val_u = gumbel_copula_cdf(0.5, 0.9999, theta)
    assert val_u == pytest.approx(0.5, abs=1e-2)

    with pytest.raises(ValueError):
        gumbel_copula_cdf(0.5, 0.5, 0.5)


def test_fit_copula_from_tau():
    np.random.seed(42)
    # Generate positively co-moving variables
    x = np.random.randn(200)
    y = x + np.random.randn(200) * 0.2
    u = empirical_cdf(x)
    v = empirical_cdf(y)

    theta_c, lambda_l = fit_copula_from_tau(u, v, copula_type="clayton")
    assert theta_c > 0.0
    assert 0.0 < lambda_l < 1.0

    theta_g, lambda_u = fit_copula_from_tau(u, v, copula_type="gumbel")
    assert theta_g >= 1.0
    assert 0.0 < lambda_u < 1.0


def test_evaluate_joint_tail_risk():
    np.random.seed(42)
    n = 300
    # Strongly coupled crash asset returns
    market_crash = np.random.randn(n)
    ret_a = pd.Series(0.8 * market_crash + 0.2 * np.random.randn(n))
    ret_b = pd.Series(0.8 * market_crash + 0.2 * np.random.randn(n))

    report = evaluate_joint_tail_risk(ret_a, ret_b, tail_quantile=0.05)
    assert report["crash_excess_ratio"] > 2.0
    assert report["recommended_haircut"] <= 0.80
    assert report["risk_level"] in ("MODERATE_TAIL_DEPENDENCE", "ELEVATED_CRASH_RISK")

    # Independent uncorrelated returns
    ret_c = pd.Series(np.random.randn(n))
    ret_d = pd.Series(np.random.randn(n))
    report_indep = evaluate_joint_tail_risk(ret_c, ret_d, tail_quantile=0.05)
    assert report_indep["recommended_haircut"] == 1.00
    assert report_indep["risk_level"] == "NORMAL"
