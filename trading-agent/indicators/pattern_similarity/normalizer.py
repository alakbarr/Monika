# ==============================================================================
# File: indicators/pattern_similarity/normalizer.py
# ==============================================================================

"""
Pure NumPy series normalizers for amplitude and scale invariant pattern matching.
Zero external library dependencies beyond standard NumPy.
"""

import numpy as np


class PriceNormalizer:
    """Normalizes time-series price data for scale-invariant pattern comparisons."""

    @staticmethod
    def z_normalize(series: np.ndarray) -> np.ndarray:
        """
        Z-score normalization: mean=0, std=1.
        Preserves relative pattern shape while eliminating absolute price level.
        """
        if len(series) == 0:
            return np.array([], dtype=float)
        std = np.std(series)
        if std < 1e-10:
            return np.zeros_like(series, dtype=float)
        return (series - np.mean(series)) / std

    @staticmethod
    def min_max_normalize(series: np.ndarray) -> np.ndarray:
        """Min-Max normalization scaling values between 0.0 and 1.0."""
        if len(series) == 0:
            return np.array([], dtype=float)
        s_min = np.min(series)
        s_max = np.max(series)
        rng = s_max - s_min
        if rng < 1e-10:
            return np.zeros_like(series, dtype=float)
        return (series - s_min) / rng

    @staticmethod
    def log_return_normalize(series: np.ndarray) -> np.ndarray:
        """Computes cumulative log returns from price series."""
        if len(series) < 2:
            return np.zeros_like(series, dtype=float)
        log_rets = np.diff(np.log(np.maximum(series, 1e-8)))
        cum_rets = np.concatenate(([0.0], np.cumsum(log_rets)))
        return cum_rets

    @staticmethod
    def atr_normalize(series: np.ndarray, atr_val: float) -> np.ndarray:
        """Normalizes series displacements by current ATR."""
        if atr_val < 1e-10 or len(series) == 0:
            return np.zeros_like(series, dtype=float)
        return (series - series[0]) / atr_val
