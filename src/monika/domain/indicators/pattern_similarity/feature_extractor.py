# ==============================================================================
# File: indicators/pattern_similarity/feature_extractor.py
# ==============================================================================

"""
Structural feature extraction from OHLCV bars for enhanced pattern characterization.
Pure NumPy implementation.
"""

from dataclasses import dataclass
import numpy as np


@dataclass
class FeatureVector:
    """Extracted structural features characterizing a candlestick segment."""
    trend_slope: float
    volatility_ratio: float
    range_position: float
    body_ratio_mean: float
    upper_wick_ratio: float
    lower_wick_ratio: float
    volume_trend: float
    swing_count: int

    def to_array(self) -> np.ndarray:
        return np.array([
            self.trend_slope,
            self.volatility_ratio,
            self.range_position,
            self.body_ratio_mean,
            self.upper_wick_ratio,
            self.lower_wick_ratio,
            self.volume_trend,
            float(self.swing_count) / 10.0,
        ], dtype=float)


class FeatureExtractor:
    """Extracts structural features from (N, 6) TOHLCV arrays."""

    def extract(self, bars: np.ndarray) -> FeatureVector:
        """
        Extracts structural features.
        bars: shape (N, 6) with columns [timestamp, open, high, low, close, volume]
        """
        if len(bars) < 5:
            return FeatureVector(0.0, 0.0, 0.5, 0.5, 0.25, 0.25, 0.0, 0)

        opens = bars[:, 1]
        highs = bars[:, 2]
        lows = bars[:, 3]
        closes = bars[:, 4]
        volumes = bars[:, 5]

        n = len(closes)
        x = np.arange(n, dtype=float)

        # 1. Trend slope normalized by standard deviation
        close_std = np.std(closes)
        if close_std > 1e-8:
            slope = np.polyfit(x, closes, 1)[0]
            trend_slope = float(np.clip(slope / close_std, -3.0, 3.0))
        else:
            trend_slope = 0.0

        # 2. Volatility ratio (approximate ATR over mean close)
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(np.abs(highs[1:] - closes[:-1]), np.abs(lows[1:] - closes[:-1]))
        )
        atr = np.mean(tr) if len(tr) > 0 else (highs[-1] - lows[-1])
        mean_close = np.mean(closes)
        volatility_ratio = float(atr / (mean_close + 1e-8))

        # 3. Range position of the last close
        window_high = np.max(highs)
        window_low = np.min(lows)
        rng = window_high - window_low
        range_position = float((closes[-1] - window_low) / rng) if rng > 1e-8 else 0.5

        # 4. Candlestick component ratios
        total_candle_ranges = np.maximum(highs - lows, 1e-8)
        body_sizes = np.abs(closes - opens)
        body_ratio_mean = float(np.mean(body_sizes / total_candle_ranges))

        upper_wicks = highs - np.maximum(opens, closes)
        upper_wick_ratio = float(np.mean(upper_wicks / total_candle_ranges))

        lower_wicks = np.minimum(opens, closes) - lows
        lower_wick_ratio = float(np.mean(lower_wicks / total_candle_ranges))

        # 5. Volume trend slope
        vol_std = np.std(volumes)
        if vol_std > 1e-8:
            vol_slope = np.polyfit(x, volumes, 1)[0]
            volume_trend = float(np.clip(vol_slope / vol_std, -3.0, 3.0))
        else:
            volume_trend = 0.0

        # 6. Directional swing count (zigzag changes)
        diffs = np.diff(closes)
        signs = np.sign(diffs)
        signs = signs[signs != 0]
        swing_count = int(np.sum(signs[1:] != signs[:-1])) if len(signs) > 1 else 0

        return FeatureVector(
            trend_slope=trend_slope,
            volatility_ratio=volatility_ratio,
            range_position=range_position,
            body_ratio_mean=body_ratio_mean,
            upper_wick_ratio=upper_wick_ratio,
            lower_wick_ratio=lower_wick_ratio,
            volume_trend=volume_trend,
            swing_count=swing_count,
        )

    def compute_feature_similarity(self, f1: FeatureVector, f2: FeatureVector) -> float:
        """Computes cosine similarity between two feature vectors."""
        v1 = f1.to_array()
        v2 = f2.to_array()
        dot = np.dot(v1, v2)
        norm = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm < 1e-10:
            return 0.5
        sim = float(dot / norm)
        # Scale from [-1, 1] to [0, 1]
        return float(np.clip((sim + 1.0) / 2.0, 0.0, 1.0))
