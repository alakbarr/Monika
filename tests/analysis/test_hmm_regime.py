"""
Unit tests for HMMRegimeClassifier deterministic statistical regime classification.
"""

from __future__ import annotations

import numpy as np
import pytest

from monika.application.analysis.calculators.hmm_regime import HMMRegimeClassifier


def test_hmm_classifier_insufficient_data():
    clf = HMMRegimeClassifier()
    res = clf.fit_predict_features(np.array([0.001, 0.002]), np.array([0.01, 0.01]))
    assert res["current_regime"] == "CHOP_RANGING"
    assert res["method"] == "insufficient_data_fallback"


def test_hmm_classifier_bull_trend_statistical():
    clf = HMMRegimeClassifier()
    # 20 observations of steadily positive returns
    returns = np.array([0.002 + i * 0.0003 for i in range(20)])
    ranges = np.full(20, 0.01)

    res = clf.fit_predict_features(returns, ranges)
    assert res["current_regime"] == "BULL_TREND"
    assert res["regime_probabilities"]["BULL"] > res["regime_probabilities"]["BEAR"]
    assert res["confidence"] > 0.4
    assert res["method"] in ("statistical_gaussian_mixture", "gaussian_hmm")


def test_hmm_classifier_bear_trend_statistical():
    clf = HMMRegimeClassifier()
    # 20 observations of steadily negative returns
    returns = np.array([-0.002 - i * 0.0003 for i in range(20)])
    ranges = np.full(20, 0.01)

    res = clf.fit_predict_features(returns, ranges)
    assert res["current_regime"] == "BEAR_TREND"
    assert res["regime_probabilities"]["BEAR"] > res["regime_probabilities"]["BULL"]
    assert res["confidence"] > 0.4
    assert res["method"] in ("statistical_gaussian_mixture", "gaussian_hmm")


def test_hmm_classifier_chop_ranging():
    clf = HMMRegimeClassifier()
    # 20 observations of oscillating near-zero returns
    returns = np.array([0.0001, -0.0001] * 10)
    ranges = np.full(20, 0.01)

    res = clf.fit_predict_features(returns, ranges)
    assert res["current_regime"] == "CHOP_RANGING"
    assert res["regime_probabilities"]["CHOP"] >= res["regime_probabilities"]["BULL"]
