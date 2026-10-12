"""
Unit tests for Platt Scaling, Isotonic PAV, and Statistical Confidence Calibration.
"""
import pytest
import math
from utils.calibration.confidence_calibrator import (
    fit_platt_scaling,
    fit_isotonic_pav,
    calibrate_probability
)


def test_fit_platt_scaling_monotone_positive():
    """Verify that Platt Scaling fits positive slope A > 0 when higher confidence predicts wins."""
    # Synthetic well-calibrated dataset: higher confidence = higher win probability
    confidences = [0.60, 0.62, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]
    outcomes =    [0,    0,    0,    1,    1,    1,    1,    1,    1]

    a, b = fit_platt_scaling(confidences, outcomes)
    
    # Sigmoid should have positive slope A > 0
    assert a > 0.0
    
    # Check calibrated values are monotonically increasing
    p_low = calibrate_probability(0.60, platt_params=(a, b))
    p_high = calibrate_probability(0.90, platt_params=(a, b))
    assert p_low < p_high
    assert 0.0 <= p_low <= 1.0
    assert 0.0 <= p_high <= 1.0


def test_fit_isotonic_pav_monotonicity():
    """Verify that Pool-Adjacent-Violators produces non-decreasing piecewise probabilities."""
    confidences = [0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
    # Non-monotonic raw outcomes: 1, 0, 1, 0, 1, 1
    outcomes = [1, 0, 1, 0, 1, 1]

    pav_bins = fit_isotonic_pav(confidences, outcomes)
    assert len(pav_bins) >= 1

    # Verify every subsequent bin has calibrated_prob >= previous bin
    for i in range(len(pav_bins) - 1):
        assert pav_bins[i]['calibrated_prob'] <= pav_bins[i + 1]['calibrated_prob']

    # Verify evaluation
    p_cal = calibrate_probability(0.72, pav_bins=pav_bins)
    assert 0.0 <= p_cal <= 1.0


def test_calibrate_probability_boundary_clamping():
    """Verify boundary clamping and fallback behavior."""
    assert calibrate_probability(1.5) == 1.0
    assert calibrate_probability(-0.5) == 0.0
    assert calibrate_probability(0.75) == 0.75
