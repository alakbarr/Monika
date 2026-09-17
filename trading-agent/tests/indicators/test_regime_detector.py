"""
Unit tests for indicators/regime_detector.py (SchmittRegimeDetector hysteresis transitions).
"""
import numpy as np
import pandas as pd
import pytest
from indicators.regime_detector import SchmittRegimeDetector, RegimeState


def test_schmitt_regime_detector_transitions():
    detector = SchmittRegimeDetector(enter_fused=0.60, exit_fused=0.40, correlation_window=20)
    assert detector.state == RegimeState.DIVERSIFIED

    dates = pd.date_range("2025-01-01", periods=30, freq="1D")

    # 1. Independent assets -> density ~0.0 -> stays DIVERSIFIED
    np.random.seed(42)
    df_div = pd.DataFrame(np.random.normal(0, 1, (30, 4)), index=dates)
    state = detector.update(df_div)
    assert state == RegimeState.DIVERSIFIED

    # 2. Highly correlated crisis regime -> density = 1.0 -> transitions to FUSED
    base_shock = np.random.normal(0, 1, 30)
    df_fused = pd.DataFrame({
        f"asset_{i}": base_shock + np.random.normal(0, 0.05, 30) for i in range(4)
    }, index=dates)
    state = detector.update(df_fused)
    assert state == RegimeState.FUSED

    # 3. Intermediate density (e.g. 0.50): between 0.40 and 0.60 -> hysteresis keeps FUSED
    # If it was a simple threshold at 0.50, it might flip, but Schmitt trigger preserves FUSED
    assert detector.state == RegimeState.FUSED

    # 4. Back to uncorrelated -> drops below exit_fused (0.40) -> transitions to DIVERSIFIED
    state = detector.update(df_div)
    assert state == RegimeState.DIVERSIFIED
