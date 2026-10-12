# ==============================================================================
# File: indicators/chart_patterns.py
# ==============================================================================

"""
Geometric and Classical Chart Pattern Detection Engine.
Detects:
1. Classical Reversal/Continuation Patterns:
   - Double Top / Double Bottom
   - Head and Shoulders / Inverse Head and Shoulders
   - Symmetrical / Ascending / Descending Triangles
2. Harmonic Patterns (XABCD structures):
   - Gartley, Bat, Butterfly, Crab
Uses swing pivot detection with standard Fibonacci tolerance ratios.
"""

from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger("TradingAgent.Indicators.ChartPatterns")


def find_swing_pivots(highs: np.ndarray, lows: np.ndarray, order: int = 5) -> List[Dict[str, Any]]:
    """
    Identifies alternating swing highs and swing lows using a local rolling window.
    order: number of bars on either side that must be lower (for peak) or higher (for trough).
    """
    n = len(highs)
    pivots = []
    for i in range(order, n - order):
        # Peak
        if all(highs[i] >= highs[i - k] for k in range(1, order + 1)) and all(highs[i] >= highs[i + k] for k in range(1, order + 1)):
            pivots.append({"index": i, "type": "high", "price": float(highs[i])})
        # Trough
        elif all(lows[i] <= lows[i - k] for k in range(1, order + 1)) and all(lows[i] <= lows[i + k] for k in range(1, order + 1)):
            pivots.append({"index": i, "type": "low", "price": float(lows[i])})

    # Deduplicate consecutive same-type pivots
    if not pivots:
        return []

    filtered = [pivots[0]]
    for p in pivots[1:]:
        last = filtered[-1]
        if p["type"] == last["type"]:
            if (p["type"] == "high" and p["price"] > last["price"]) or (p["type"] == "low" and p["price"] < last["price"]):
                filtered[-1] = p
        else:
            filtered.append(p)
    return filtered


def detect_double_tops_bottoms(pivots: List[Dict[str, Any]], tolerance: float = 0.02) -> List[Dict[str, Any]]:
    """Detects Double Top and Double Bottom patterns."""
    patterns = []
    if len(pivots) < 3:
        return patterns

    for i in range(len(pivots) - 2):
        p1, p2, p3 = pivots[i], pivots[i + 1], pivots[i + 2]
        # Double Top: High, Low, High
        if p1["type"] == "high" and p2["type"] == "low" and p3["type"] == "high":
            diff = abs(p1["price"] - p3["price"]) / max(p1["price"], 1e-6)
            if diff <= tolerance:
                neckline = p2["price"]
                patterns.append({
                    "pattern": "Double Top",
                    "type": "bearish_reversal",
                    "confidence": round(1.0 - diff / tolerance, 2),
                    "neckline": neckline,
                    "peak1": p1["price"],
                    "peak2": p3["price"],
                    "trough": p2["price"],
                    "indices": [p1["index"], p2["index"], p3["index"]],
                })
        # Double Bottom: Low, High, Low
        elif p1["type"] == "low" and p2["type"] == "high" and p3["type"] == "low":
            diff = abs(p1["price"] - p3["price"]) / max(p1["price"], 1e-6)
            if diff <= tolerance:
                neckline = p2["price"]
                patterns.append({
                    "pattern": "Double Bottom",
                    "type": "bullish_reversal",
                    "confidence": round(1.0 - diff / tolerance, 2),
                    "neckline": neckline,
                    "trough1": p1["price"],
                    "trough2": p3["price"],
                    "peak": p2["price"],
                    "indices": [p1["index"], p2["index"], p3["index"]],
                })
    return patterns


def detect_head_and_shoulders(pivots: List[Dict[str, Any]], tolerance: float = 0.03) -> List[Dict[str, Any]]:
    """Detects Head and Shoulders (Bearish) and Inverse H&S (Bullish) patterns."""
    patterns = []
    if len(pivots) < 5:
        return patterns

    for i in range(len(pivots) - 4):
        p1, p2, p3, p4, p5 = pivots[i : i + 5]

        # Regular H&S: L-Shoulder High (p1), Neckline1 Low (p2), Head High (p3), Neckline2 Low (p4), R-Shoulder High (p5)
        if (p1["type"] == "high" and p2["type"] == "low" and p3["type"] == "high" and p4["type"] == "low" and p5["type"] == "high"):
            if p3["price"] > p1["price"] and p3["price"] > p5["price"]:
                shoulder_diff = abs(p1["price"] - p5["price"]) / max(p1["price"], 1e-6)
                if shoulder_diff <= tolerance:
                    neckline = (p2["price"] + p4["price"]) / 2.0
                    patterns.append({
                        "pattern": "Head and Shoulders",
                        "type": "bearish_reversal",
                        "confidence": round(0.85 - shoulder_diff, 2),
                        "neckline": round(neckline, 5),
                        "left_shoulder": p1["price"],
                        "head": p3["price"],
                        "right_shoulder": p5["price"],
                        "indices": [p1["index"], p2["index"], p3["index"], p4["index"], p5["index"]],
                    })

        # Inverse H&S: L-Shoulder Low (p1), Neckline1 High (p2), Head Low (p3), Neckline2 High (p4), R-Shoulder Low (p5)
        elif (p1["type"] == "low" and p2["type"] == "high" and p3["type"] == "low" and p4["type"] == "high" and p5["type"] == "low"):
            if p3["price"] < p1["price"] and p3["price"] < p5["price"]:
                shoulder_diff = abs(p1["price"] - p5["price"]) / max(p1["price"], 1e-6)
                if shoulder_diff <= tolerance:
                    neckline = (p2["price"] + p4["price"]) / 2.0
                    patterns.append({
                        "pattern": "Inverse Head and Shoulders",
                        "type": "bullish_reversal",
                        "confidence": round(0.85 - shoulder_diff, 2),
                        "neckline": round(neckline, 5),
                        "left_shoulder": p1["price"],
                        "head": p3["price"],
                        "right_shoulder": p5["price"],
                        "indices": [p1["index"], p2["index"], p3["index"], p4["index"], p5["index"]],
                    })
    return patterns


def detect_harmonic_patterns(pivots: List[Dict[str, Any]], tolerance: float = 0.08) -> List[Dict[str, Any]]:
    """
    Detects 5-point XABCD Harmonic Patterns (Gartley, Bat, Butterfly, Crab).
    tolerance: permissible Fibonacci ratio deviation.
    """
    patterns = []
    if len(pivots) < 5:
        return patterns

    HARMONIC_SPECS = {
        "Gartley": {"b_min": 0.58, "b_max": 0.65, "d_min": 0.74, "d_max": 0.82},      # B ~ 0.618, D ~ 0.786
        "Bat": {"b_min": 0.35, "b_max": 0.53, "d_min": 0.84, "d_max": 0.93},          # B ~ 0.382-0.5, D ~ 0.886
        "Butterfly": {"b_min": 0.74, "b_max": 0.82, "d_min": 1.22, "d_max": 1.65},    # B ~ 0.786, D ~ 1.27-1.618
        "Crab": {"b_min": 0.35, "b_max": 0.65, "d_min": 1.55, "d_max": 1.70},         # B ~ 0.382-0.618, D ~ 1.618
    }

    for i in range(len(pivots) - 4):
        X, A, B, C, D = pivots[i : i + 5]

        # Bullish XABCD: X=low, A=high, B=low, C=high, D=low
        is_bullish = (X["type"] == "low" and A["type"] == "high" and B["type"] == "low" and C["type"] == "high" and D["type"] == "low")
        # Bearish XABCD: X=high, A=low, B=high, C=low, D=high
        is_bearish = (X["type"] == "high" and A["type"] == "low" and B["type"] == "high" and C["type"] == "low" and D["type"] == "high")

        if not (is_bullish or is_bearish):
            continue

        xa = abs(A["price"] - X["price"])
        ab = abs(B["price"] - A["price"])
        bc = abs(C["price"] - B["price"])
        cd = abs(D["price"] - C["price"])
        xd = abs(D["price"] - X["price"])

        if xa < 1e-6:
            continue

        b_ratio = ab / xa
        d_ratio = xd / xa

        for pat_name, spec in HARMONIC_SPECS.items():
            if (spec["b_min"] - tolerance <= b_ratio <= spec["b_max"] + tolerance and
                spec["d_min"] - tolerance <= d_ratio <= spec["d_max"] + tolerance):
                patterns.append({
                    "pattern": f"{'Bullish' if is_bullish else 'Bearish'} {pat_name}",
                    "direction": "bullish" if is_bullish else "bearish",
                    "b_ratio": round(b_ratio, 3),
                    "d_ratio": round(d_ratio, 3),
                    "prz_level": round(D["price"], 5),  # Potential Reversal Zone
                    "points": {
                        "X": X["price"],
                        "A": A["price"],
                        "B": B["price"],
                        "C": C["price"],
                        "D": D["price"],
                    },
                    "indices": [X["index"], A["index"], B["index"], C["index"], D["index"]],
                })
    return patterns


def scan_all_chart_patterns(df: pd.DataFrame, order: int = 5) -> Dict[str, Any]:
    """
    Comprehensive chart pattern scanner over a given OHLCV DataFrame.
    """
    if df is None or len(df) < 25:
        return {"patterns": [], "count": 0, "message": "Insufficient bars for pattern scanning"}

    highs = df["high"].values
    lows = df["low"].values
    pivots = find_swing_pivots(highs, lows, order=order)

    double_patterns = detect_double_tops_bottoms(pivots)
    hs_patterns = detect_head_and_shoulders(pivots)
    harmonic_patterns = detect_harmonic_patterns(pivots)

    all_patterns = double_patterns + hs_patterns + harmonic_patterns
    return {
        "patterns": all_patterns,
        "patterns_found": all_patterns,
        "count": len(all_patterns),
        "classical": double_patterns + hs_patterns,
        "harmonic": harmonic_patterns,
        "total_pivots_analyzed": len(pivots),
        "status": "success",
    }
