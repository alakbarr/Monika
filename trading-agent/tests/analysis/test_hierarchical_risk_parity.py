# ==============================================================================
# File: tests/analysis/test_hierarchical_risk_parity.py
# Monika Hierarchical Risk Parity (HRP) Test Suite
# ==============================================================================

import numpy as np
import pandas as pd
import pytest

from analysis.calculators.hierarchical_risk_parity import (
    correlation_distance_matrix,
    compute_hrp_weights,
)


def test_correlation_distance_matrix():
    corr = np.array([
        [1.0, 0.5, -0.2],
        [0.5, 1.0, 0.1],
        [-0.2, 0.1, 1.0],
    ])
    dist = correlation_distance_matrix(corr)

    assert dist.shape == (3, 3)
    assert np.allclose(np.diag(dist), 0.0)
    assert np.allclose(dist, dist.T)
    assert (dist >= 0.0).all() and (dist <= 1.0).all()


def test_compute_hrp_weights_basic():
    np.random.seed(42)
    n = 200
    # Create 4 assets:
    # Asset A: low vol (sigma = 0.01)
    # Asset B: medium vol (sigma = 0.02)
    # Asset C: high vol (sigma = 0.05)
    # Asset D: very high vol (sigma = 0.10)
    rets = pd.DataFrame({
        "LOW_VOL": np.random.randn(n) * 0.01,
        "MED_VOL": np.random.randn(n) * 0.02,
        "HIGH_VOL": np.random.randn(n) * 0.05,
        "CRYPTO_VOL": np.random.randn(n) * 0.10,
    })

    weights = compute_hrp_weights(rets)

    assert len(weights) == 4
    assert pytest.approx(weights.sum(), abs=1e-5) == 1.0
    assert (weights > 0.0).all()

    # Risk parity ordering: Lower volatility should receive higher weight than extreme volatility
    assert weights["LOW_VOL"] > weights["HIGH_VOL"]
    assert weights["MED_VOL"] > weights["CRYPTO_VOL"]


def test_compute_hrp_weights_single_asset():
    rets = pd.DataFrame({"XAUUSD": [0.01, -0.02, 0.03]})
    w = compute_hrp_weights(rets)
    assert len(w) == 1
    assert w["XAUUSD"] == 1.0
