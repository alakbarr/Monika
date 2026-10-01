# ==============================================================================
# File: indicators/candlestick_patterns.py
# ==============================================================================

"""
Algorithmic Candlestick Pattern Detection Engine.
Identifies high-probability reversal and continuation price action formations:
- Pin Bar / Hammer / Inverted Hammer / Shooting Star
- Bullish & Bearish Engulfing
- Standard Doji, Long-legged Doji, Dragonfly Doji, Gravestone Doji
- Morning Star & Evening Star
"""

from typing import List, Dict, Any, Optional
import math


def detect_candlestick_patterns(candles: List[Dict[str, Any]], lookback: int = 5) -> Dict[str, Any]:
    """
    Analyzes candlestick sequence to detect classical price action patterns.

    Args:
        candles: List of dicts with keys: 'open', 'high', 'low', 'close', 'time'/'timestamp'
        lookback: Number of recent candles to evaluate for patterns (default: 5)

    Returns:
        Dict containing detected patterns, latest pattern summary, and bullish/bearish score.
    """
    if candles is None or len(candles) < 2:
        return {
            "detected_patterns": [],
            "latest_pattern": None,
            "overall_bias": "neutral",
            "bullish_patterns_count": 0,
            "bearish_patterns_count": 0,
        }

    # Convert DataFrame to list of dicts if needed
    if hasattr(candles, "to_dict"):
        candle_list = candles.to_dict(orient="records")
    else:
        candle_list = list(candles)

    formatted_candles = []
    for c in candle_list:
        try:
            o = float(c.get("open", 0))
            h = float(c.get("high", 0))
            l = float(c.get("low", 0))
            cl = float(c.get("close", 0))
            t = c.get("time") or c.get("timestamp") or ""
            formatted_candles.append({"open": o, "high": h, "low": l, "close": cl, "time": str(t)})
        except (ValueError, TypeError):
            continue

    n = len(formatted_candles)
    if n < 2:
        return {
            "detected_patterns": [],
            "latest_pattern": None,
            "overall_bias": "neutral",
            "bullish_patterns_count": 0,
            "bearish_patterns_count": 0,
        }

    eval_start = max(1, n - lookback)
    patterns = []

    for i in range(eval_start, n):
        cur = formatted_candles[i]
        prev = formatted_candles[i - 1]
        prev2 = formatted_candles[i - 2] if i >= 2 else None

        c_open, c_high, c_low, c_close = cur["open"], cur["high"], cur["low"], cur["close"]
        p_open, p_high, p_low, p_close = prev["open"], prev["high"], prev["low"], prev["close"]

        total_range = c_high - c_low
        if total_range <= 1e-7:
            continue

        body_top = max(c_open, c_close)
        body_bottom = min(c_open, c_close)
        body_size = body_top - body_bottom
        upper_shadow = c_high - body_top
        lower_shadow = body_bottom - c_low
        is_bullish = c_close >= c_open

        # 1. Doji Detection (Body <= 10% of total range)
        if body_size <= total_range * 0.10:
            doji_type = "Standard Doji"
            if upper_shadow <= total_range * 0.10 and lower_shadow >= total_range * 0.70:
                doji_type = "Dragonfly Doji (Bullish Rejection)"
                bias = "bullish"
            elif lower_shadow <= total_range * 0.10 and upper_shadow >= total_range * 0.70:
                doji_type = "Gravestone Doji (Bearish Rejection)"
                bias = "bearish"
            else:
                bias = "neutral"

            patterns.append({
                "index": i,
                "candle_time": cur["time"],
                "pattern": doji_type,
                "bias": bias,
                "confidence": 0.75,
                "description": f"{doji_type} detected with body {body_size/total_range:.1%} of candle range.",
            })

        # 2. Pin Bar / Hammer / Shooting Star Detection
        # Bullish Pin Bar / Hammer (lower shadow >= 60%, upper shadow <= 20%)
        if lower_shadow >= total_range * 0.60 and upper_shadow <= total_range * 0.20:
            patterns.append({
                "index": i,
                "candle_time": cur["time"],
                "pattern": "Bullish Pin Bar / Hammer",
                "bias": "bullish",
                "confidence": 0.85,
                "description": f"Long lower rejection wick ({lower_shadow/total_range:.1%}) indicating strong demand absorption.",
            })
        # Bearish Pin Bar / Shooting Star (upper shadow >= 60%, lower shadow <= 20%)
        elif upper_shadow >= total_range * 0.60 and lower_shadow <= total_range * 0.20:
            patterns.append({
                "index": i,
                "candle_time": cur["time"],
                "pattern": "Bearish Pin Bar / Shooting Star",
                "bias": "bearish",
                "confidence": 0.85,
                "description": f"Long upper rejection wick ({upper_shadow/total_range:.1%}) indicating heavy supply overhang.",
            })

        # 3. Engulfing Patterns
        p_body_top = max(p_open, p_close)
        p_body_bottom = min(p_open, p_close)
        p_body_size = p_body_top - p_body_bottom
        p_is_bullish = p_close >= p_open

        # Bullish Engulfing: previous was red, current is green and engulfs previous body
        if not p_is_bullish and is_bullish:
            if c_close > p_body_top and c_open <= p_body_bottom and body_size > p_body_size * 1.1:
                patterns.append({
                    "index": i,
                    "candle_time": cur["time"],
                    "pattern": "Bullish Engulfing",
                    "bias": "bullish",
                    "confidence": 0.88,
                    "description": "Bullish candle body completely engulfs the prior bearish candle body.",
                })

        # Bearish Engulfing: previous was green, current is red and engulfs previous body
        if p_is_bullish and not is_bullish:
            if c_open >= p_body_top and c_close < p_body_bottom and body_size > p_body_size * 1.1:
                patterns.append({
                    "index": i,
                    "candle_time": cur["time"],
                    "pattern": "Bearish Engulfing",
                    "bias": "bearish",
                    "confidence": 0.88,
                    "description": "Bearish candle body completely engulfs the prior bullish candle body.",
                })

        # 4. 3-Bar Patterns: Morning Star & Evening Star
        if prev2 is not None:
            p2_open, p2_close = prev2["open"], prev2["close"]
            p2_body = abs(p2_close - p2_open)
            p2_is_bear = p2_close < p2_open
            p2_is_bull = p2_close > p2_open

            # Morning Star: 1=large bear, 2=small body (indecision), 3=large bull closing > 50% into bar 1
            if p2_is_bear and p_body_size < p2_body * 0.4 and is_bullish and c_close > (p2_open + p2_close) / 2:
                patterns.append({
                    "index": i,
                    "candle_time": cur["time"],
                    "pattern": "Morning Star",
                    "bias": "bullish",
                    "confidence": 0.90,
                    "description": "3-candle bullish reversal: Bearish plunge -> Indecision base -> Strong Bullish recovery.",
                })

            # Evening Star: 1=large bull, 2=small body, 3=large bear closing > 50% into bar 1
            if p2_is_bull and p_body_size < p2_body * 0.4 and not is_bullish and c_close < (p2_open + p2_close) / 2:
                patterns.append({
                    "index": i,
                    "candle_time": cur["time"],
                    "pattern": "Evening Star",
                    "bias": "bearish",
                    "confidence": 0.90,
                    "description": "3-candle bearish reversal: Bullish rally -> Indecision peak -> Strong Bearish breakdown.",
                })

    bull_count = sum(1 for p in patterns if p["bias"] == "bullish")
    bear_count = sum(1 for p in patterns if p["bias"] == "bearish")

    overall_bias = "neutral"
    if bull_count > bear_count:
        overall_bias = "bullish"
    elif bear_count > bull_count:
        overall_bias = "bearish"

    latest_pat = patterns[-1] if patterns else None

    return {
        "detected_patterns": patterns,
        "latest_pattern": latest_pat,
        "overall_bias": overall_bias,
        "bullish_patterns_count": bull_count,
        "bearish_patterns_count": bear_count,
        "candles_analyzed": min(lookback, n),
    }
