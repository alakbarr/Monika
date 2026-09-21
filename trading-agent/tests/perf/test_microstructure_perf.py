"""
Microstructure Performance Gate (Phase 5.4).
Enforces hard performance budgets on market structure detection:
Processes 5,000 candle bars in under 100ms to ensure low-latency execution in production.
"""

import time
import numpy as np
import pytest


def detect_swings_and_fvg(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray) -> dict:
    """Vectorized / optimized swing high/low and Fair Value Gap (FVG) detector."""
    n = len(highs)
    if n < 3:
        return {"fvgs": 0, "swing_highs": 0, "swing_lows": 0}

    # Vectorized FVG detection
    # Bullish FVG: Low of bar i > High of bar i-2
    bullish_fvg = lows[2:] > highs[:-2]
    # Bearish FVG: High of bar i < Low of bar i-2
    bearish_fvg = highs[2:] < lows[:-2]
    total_fvgs = int(np.count_nonzero(bullish_fvg) + np.count_nonzero(bearish_fvg))

    # Swing high: bar i-1 is local maximum between i-2, i-1, i
    swing_highs = (highs[1:-1] > highs[:-2]) & (highs[1:-1] > highs[2:])
    # Swing low: bar i-1 is local minimum between i-2, i-1, i
    swing_lows = (lows[1:-1] < lows[:-2]) & (lows[1:-1] < lows[2:])
    total_swings = int(np.count_nonzero(swing_highs) + np.count_nonzero(swing_lows))

    return {
        "fvgs": total_fvgs,
        "swing_highs": int(np.count_nonzero(swing_highs)),
        "swing_lows": int(np.count_nonzero(swing_lows)),
        "total_swings": total_swings,
    }


def test_microstructure_processing_speed_budget():
    """Ensure market structure detection across 5,000 candles executes in under 100ms."""
    num_candles = 5000
    np.random.seed(42)

    # Generate synthetic price series
    returns = np.random.normal(0, 0.001, num_candles)
    price = 2000.0 * np.exp(np.cumsum(returns))
    noise = np.random.uniform(0.1, 1.0, num_candles)
    highs = price + noise
    lows = price - noise
    closes = price + np.random.uniform(-0.5, 0.5, num_candles)

    # Warm-up pass
    detect_swings_and_fvg(highs[:100], lows[:100], closes[:100])

    # Benchmarked pass
    start_time = time.perf_counter()
    result = detect_swings_and_fvg(highs, lows, closes)
    elapsed_seconds = time.perf_counter() - start_time

    assert result["total_swings"] > 0
    assert result["fvgs"] >= 0
    # Hard budget: 100ms ceiling
    assert elapsed_seconds < 0.100, f"Microstructure detection took {elapsed_seconds * 1000:.2f}ms (> 100ms budget)"
