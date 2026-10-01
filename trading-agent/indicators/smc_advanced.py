"""
Advanced Deterministic Smart Money Concepts (SMC) & ICT Primitives Suite.

Pure quantitative and geometric algorithms for institutional market structure:
1. Inducement (IDM) & Validated Order Block confirmation
2. Breaker Block polarity inversion detection
3. Judas Swing (London 08:00 UTC Open false expansion)
4. Engineered Liquidity Pools (Equal Highs EQH / Equal Lows EQL)
5. Spatial Geometric Confluence (OB + FVG Overlap)
6. Implied / Wick-to-Wick Fair Value Gaps
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger("TradingAgent.Indicators.SMCAdvanced")


@dataclass
class InducementResult:
    """Outcome of Inducement (IDM) detection."""
    idm_detected: bool = False
    idm_price: float = 0.0
    idm_time: Optional[str] = None
    is_swept: bool = False
    sweep_time: Optional[str] = None
    valid_ob_low: Optional[float] = None
    valid_ob_high: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BreakerBlockResult:
    """Detected Breaker Block (failed order block with flipped polarity)."""
    breaker_detected: bool = False
    direction: str = ""  # "BULLISH_SUPPORT" | "BEARISH_RESISTANCE"
    price_low: float = 0.0
    price_high: float = 0.0
    original_ob_time: Optional[str] = None
    broken_at: Optional[str] = None
    retested: bool = False
    strength: float = 1.0


@dataclass
class JudasSwingResult:
    """Outcome of London Open (08:00 UTC) Judas Swing trap detection."""
    judas_detected: bool = False
    trap_direction: str = ""  # "BEARISH_TRAP" (swept Asian High, expected dump) | "BULLISH_TRAP"
    expansion_extreme: float = 0.0
    rejection_ratio: float = 0.0
    asian_high: float = 0.0
    asian_low: float = 0.0
    timestamp: Optional[str] = None
    details: str = ""


@dataclass
class EqualPoolResult:
    """Engineered Liquidity Pool formed by Equal Highs (EQH) or Equal Lows (EQL)."""
    pool_type: str = ""  # "EQH" (Buy-Side Liquidity) | "EQL" (Sell-Side Liquidity)
    price_level: float = 0.0
    touch_count: int = 0
    tolerance_pips: float = 0.0
    swing_times: List[str] = field(default_factory=list)
    is_swept: bool = False


def detect_inducement(
    df: pd.DataFrame,
    swings: List[Dict[str, Any]],
    trend: str = "bullish"
) -> InducementResult:
    """
    Identifies the first minor internal pullback swing (Inducement / IDM).
    In SMC/ICT:
    - Bullish: IDM is the first internal swing low after forming a new High.
      When price sweeps this low, the High is confirmed and Order Blocks below become valid.
    - Bearish: IDM is the first internal swing high after forming a new Low.
    """
    if df is None or len(df) < 5 or not swings:
        return InducementResult()

    trend_lower = trend.lower()
    recent_swings = [s for s in swings if s.get("type")]
    if len(recent_swings) < 2:
        return InducementResult()

    if "bull" in trend_lower:
        # Cari swing low pertama yang terbentuk setelah swing high tertinggi terakhir
        highs = [s for s in recent_swings if "high" in s.get("type", "")]
        lows = [s for s in recent_swings if "low" in s.get("type", "")]
        if not highs or not lows:
            return InducementResult()

        last_high = highs[-1]
        lh_idx = last_high.get("index", 0)
        # Lows that occurred after or just before the high as pullback
        valid_idm_lows = [l for l in lows if l.get("index", 0) >= lh_idx - 5]
        if not valid_idm_lows:
            valid_idm_lows = lows[-2:] if len(lows) >= 2 else lows

        idm_target = valid_idm_lows[-1]
        idm_price = float(idm_target.get("price", 0.0))
        idm_time = str(idm_target.get("time", ""))

        # Check if subsequent price dipped below idm_price
        current_low = float(df["low"].iloc[-1])
        recent_min = float(df["low"].iloc[-5:].min())
        is_swept = bool(recent_min < idm_price)

        return InducementResult(
            idm_detected=True,
            idm_price=round(idm_price, 5),
            idm_time=idm_time,
            is_swept=is_swept,
            details={"trend": "bullish", "last_high": last_high.get("price")}
        )
    else:
        # Bearish: first internal swing high
        highs = [s for s in recent_swings if "high" in s.get("type", "")]
        lows = [s for s in recent_swings if "low" in s.get("type", "")]
        if not highs or not lows:
            return InducementResult()

        last_low = lows[-1]
        ll_idx = last_low.get("index", 0)
        valid_idm_highs = [h for h in highs if h.get("index", 0) >= ll_idx - 5]
        if not valid_idm_highs:
            valid_idm_highs = highs[-2:] if len(highs) >= 2 else highs

        idm_target = valid_idm_highs[-1]
        idm_price = float(idm_target.get("price", 0.0))
        idm_time = str(idm_target.get("time", ""))

        recent_max = float(df["high"].iloc[-5:].max())
        is_swept = bool(recent_max > idm_price)

        return InducementResult(
            idm_detected=True,
            idm_price=round(idm_price, 5),
            idm_time=idm_time,
            is_swept=is_swept,
            details={"trend": "bearish", "last_low": last_low.get("price")}
        )


def detect_breaker_blocks(
    df: pd.DataFrame,
    order_blocks: List[Any]
) -> List[BreakerBlockResult]:
    """
    Identifies Order Blocks that were violated with strong displacement and have flipped polarity.
    - Bullish OB broken downward becomes Bearish Resistance Breaker.
    - Bearish OB broken upward becomes Bullish Support Breaker.
    """
    breakers: List[BreakerBlockResult] = []
    if df is None or df.empty or not order_blocks:
        return breakers

    last_close = float(df["close"].iloc[-1])

    for ob in order_blocks:
        ob_type = getattr(ob, "type", "") or (ob.get("type") if isinstance(ob, dict) else "")
        price_low = getattr(ob, "price_low", 0.0) or (ob.get("price_low", 0.0) if isinstance(ob, dict) else 0.0)
        price_high = getattr(ob, "price_high", 0.0) or (ob.get("price_high", 0.0) if isinstance(ob, dict) else 0.0)
        ob_time = str(getattr(ob, "time", "") or (ob.get("time", "") if isinstance(ob, dict) else ""))

        if not price_low or not price_high:
            continue

        if "bull" in ob_type.lower():
            # Bullish OB tertembus ke bawah (close < price_low)
            broken_candles = df[df["close"] < price_low]
            if not broken_candles.empty:
                broken_time = str(broken_candles.index[-1])
                retested = bool(df["high"].iloc[-5:].max() >= price_low and last_close <= price_high)
                breakers.append(BreakerBlockResult(
                    breaker_detected=True,
                    direction="BEARISH_RESISTANCE",
                    price_low=round(price_low, 5),
                    price_high=round(price_high, 5),
                    original_ob_time=ob_time,
                    broken_at=broken_time,
                    retested=retested,
                    strength=1.2 if retested else 1.0
                ))
        elif "bear" in ob_type.lower():
            # Bearish OB tertembus ke atas (close > price_high)
            broken_candles = df[df["close"] > price_high]
            if not broken_candles.empty:
                broken_time = str(broken_candles.index[-1])
                retested = bool(df["low"].iloc[-5:].min() <= price_high and last_close >= price_low)
                breakers.append(BreakerBlockResult(
                    breaker_detected=True,
                    direction="BULLISH_SUPPORT",
                    price_low=round(price_low, 5),
                    price_high=round(price_high, 5),
                    original_ob_time=ob_time,
                    broken_at=broken_time,
                    retested=retested,
                    strength=1.2 if retested else 1.0
                ))

    return breakers


def detect_judas_swing(
    df_m15: pd.DataFrame,
    asian_high: float,
    asian_low: float,
    d1_bias: str = "bullish"
) -> JudasSwingResult:
    """
    Detects false London Open expansion (08:00 - 08:45 UTC) designed to hunt retail stops.
    """
    if df_m15 is None or len(df_m15) < 1 or not asian_high or not asian_low:
        return JudasSwingResult()

    # Scan all recent bars in M15
    for idx, row in df_m15.iterrows():
        bar_high = float(row["high"])
        bar_low = float(row["low"])
        bar_open = float(row["open"])
        bar_close = float(row["close"])
        candle_range = max(bar_high - bar_low, 1e-6)

        # Case 1: Bearish Trap (Swept Asian High)
        if bar_high > asian_high and bar_close < asian_high:
            upper_wick = bar_high - max(bar_open, bar_close)
            rejection_ratio = upper_wick / candle_range
            if rejection_ratio >= 0.35:
                ts_str = str(row.get("timestamp", idx))
                return JudasSwingResult(
                    judas_detected=True,
                    trap_direction="BEARISH_TRAP",
                    expansion_extreme=round(bar_high, 5),
                    rejection_ratio=round(rejection_ratio, 3),
                    asian_high=round(asian_high, 5),
                    asian_low=round(asian_low, 5),
                    timestamp=ts_str,
                    details=f"Swept Asian High {asian_high} at London Open with {round(rejection_ratio*100, 1)}% rejection wick."
                )

        # Case 2: Bullish Trap (Swept Asian Low)
        if bar_low < asian_low and bar_close > asian_low:
            lower_wick = min(bar_open, bar_close) - bar_low
            rejection_ratio = lower_wick / candle_range
            if rejection_ratio >= 0.35:
                ts_str = str(row.get("timestamp", idx))
                return JudasSwingResult(
                    judas_detected=True,
                    trap_direction="BULLISH_TRAP",
                    expansion_extreme=round(bar_low, 5),
                    rejection_ratio=round(rejection_ratio, 3),
                    asian_high=round(asian_high, 5),
                    asian_low=round(asian_low, 5),
                    timestamp=ts_str,
                    details=f"Swept Asian Low {asian_low} at London Open with {round(rejection_ratio*100, 1)}% rejection wick."
                )

    return JudasSwingResult()


def detect_equal_highs_lows(
    data: Union[pd.DataFrame, List[Dict[str, Any]]],
    atr: float = 0.0,
    tolerance_ratio: float = 0.12,
    tolerance_pips: float = 3.0,
    min_touches: int = 2,
) -> List[EqualPoolResult]:
    """
    Clusters swing points or candles that have near-identical price levels (Equal Highs EQH / Equal Lows EQL).
    These represent high-density stop-loss pools engineered by liquidity providers.
    """
    pools: List[EqualPoolResult] = []
    if data is None or len(data) < 2:
        return pools

    if isinstance(data, pd.DataFrame):
        # Extract swings from DataFrame
        swings = []
        for i in range(1, len(data) - 1):
            if data["high"].iloc[i] >= data["high"].iloc[i-1] and data["high"].iloc[i] >= data["high"].iloc[i+1]:
                swings.append({"type": "high", "price": float(data["high"].iloc[i]), "time": str(data.index[i])})
            if data["low"].iloc[i] <= data["low"].iloc[i-1] and data["low"].iloc[i] <= data["low"].iloc[i+1]:
                swings.append({"type": "low", "price": float(data["low"].iloc[i]), "time": str(data.index[i])})
        if atr <= 0:
            atr = float(np.mean(data["high"] - data["low"])) if len(data) > 0 else 0.001
    else:
        swings = data

    if not swings:
        return pools

    highs = [s for s in swings if "high" in s.get("type", "")]
    lows = [s for s in swings if "low" in s.get("type", "")]
    tol = (atr * tolerance_ratio) if atr > 0 else (tolerance_pips * 0.0001)

    # Cluster Highs (EQH)
    used_h = [False] * len(highs)
    for i in range(len(highs)):
        if used_h[i]:
            continue
        cluster = [highs[i]]
        used_h[i] = True
        for j in range(i + 1, len(highs)):
            if abs(float(highs[i]["price"]) - float(highs[j]["price"])) <= tol:
                cluster.append(highs[j])
                used_h[j] = True
        if len(cluster) >= min_touches:
            avg_price = sum(float(c["price"]) for c in cluster) / len(cluster)
            pools.append(EqualPoolResult(
                pool_type="EQH",
                price_level=round(avg_price, 5),
                touch_count=len(cluster),
                tolerance_pips=round(tol * 10000, 2),
                swing_times=[str(c.get("time", "")) for c in cluster]
            ))

    # Cluster Lows (EQL)
    used_l = [False] * len(lows)
    for i in range(len(lows)):
        if used_l[i]:
            continue
        cluster = [lows[i]]
        used_l[i] = True
        for j in range(i + 1, len(lows)):
            if abs(float(lows[i]["price"]) - float(lows[j]["price"])) <= tol:
                cluster.append(lows[j])
                used_l[j] = True
        if len(cluster) >= min_touches:
            avg_price = sum(float(c["price"]) for c in cluster) / len(cluster)
            pools.append(EqualPoolResult(
                pool_type="EQL",
                price_level=round(avg_price, 5),
                touch_count=len(cluster),
                tolerance_pips=round(tol * 10000, 2),
                swing_times=[str(c.get("time", "")) for c in cluster]
            ))

    return pools


def compute_ob_fvg_confluence(*args, **kwargs) -> Any:
    """
    Computes precise spatial geometric overlap between Order Blocks and Fair Value Gaps.
    Supports signatures:
      1. compute_ob_fvg_confluence(obs: List[Any], fvgs: List[Any]) -> List[Any]
      2. compute_ob_fvg_confluence(ob_high, ob_low, fvg_high, fvg_low) -> dict
    """
    if len(args) == 4 or ("ob_high" in kwargs and "ob_low" in kwargs):
        ob_high = float(args[0] if len(args) > 0 else kwargs.get("ob_high", 0.0))
        ob_low = float(args[1] if len(args) > 1 else kwargs.get("ob_low", 0.0))
        fvg_high = float(args[2] if len(args) > 2 else kwargs.get("fvg_high", 0.0))
        fvg_low = float(args[3] if len(args) > 3 else kwargs.get("fvg_low", 0.0))

        ob_range = max(ob_high - ob_low, 1e-6)
        overlap_low = max(ob_low, fvg_low)
        overlap_high = min(ob_high, fvg_high)

        if overlap_low < overlap_high:
            overlap_size = overlap_high - overlap_low
            overlap_pct = round(min(100.0, (overlap_size / ob_range) * 100.0), 2)
            return {
                "confluent": True,
                "overlap_pct": overlap_pct,
                "confluent_zone": [round(overlap_low, 5), round(overlap_high, 5)]
            }
        return {
            "confluent": False,
            "overlap_pct": 0.0,
            "confluent_zone": None
        }

    # List mode
    obs = args[0] if len(args) > 0 else kwargs.get("obs", [])
    fvgs = args[1] if len(args) > 1 else kwargs.get("fvgs", [])
    if not obs or not fvgs:
        return obs

    for ob in obs:
        ob_low = getattr(ob, "price_low", 0.0) or (ob.get("price_low", 0.0) if isinstance(ob, dict) else 0.0)
        ob_high = getattr(ob, "price_high", 0.0) or (ob.get("price_high", 0.0) if isinstance(ob, dict) else 0.0)
        ob_range = max(ob_high - ob_low, 1e-6)

        for fvg in fvgs:
            fvg_low = getattr(fvg, "gap_low", 0.0) or (fvg.get("gap_low", 0.0) if isinstance(fvg, dict) else 0.0)
            fvg_high = getattr(fvg, "gap_high", 0.0) or (fvg.get("gap_high", 0.0) if isinstance(fvg, dict) else 0.0)

            overlap_low = max(ob_low, fvg_low)
            overlap_high = min(ob_high, fvg_high)

            if overlap_low < overlap_high:
                overlap_size = overlap_high - overlap_low
                overlap_pct = min(1.0, overlap_size / ob_range)
                if isinstance(ob, dict):
                    ob["has_confluent_fvg"] = True
                    ob["confluent_fvg_overlap_pct"] = round(overlap_pct, 3)
                    ob["confluent_fvg_zone"] = [round(overlap_low, 5), round(overlap_high, 5)]
                else:
                    setattr(ob, "has_confluent_fvg", True)
                    setattr(ob, "confluent_fvg_overlap_pct", round(overlap_pct, 3))
                    setattr(ob, "confluent_fvg_zone", [round(overlap_low, 5), round(overlap_high, 5)])

    return obs


def find_wick_to_wick_fvg(df: pd.DataFrame, min_atr: float = 0.0) -> List[Dict[str, Any]]:
    """
    Detects Implied / Wick-to-Wick Fair Value Gaps where candle wicks leave unmitigated gaps.
    """
    implied_fvgs = []
    if df is None or len(df) < 3:
        return implied_fvgs

    for i in range(2, len(df)):
        c1 = df.iloc[i - 2]
        c3 = df.iloc[i]

        # Bullish Implied FVG: c3.low > c1.high
        if c3["low"] > c1["high"]:
            gap_size = c3["low"] - c1["high"]
            if min_atr <= 0 or gap_size >= min_atr * 0.2:
                implied_fvgs.append({
                    "type": "bullish_implied_fvg",
                    "gap_low": round(float(c1["high"]), 5),
                    "gap_high": round(float(c3["low"]), 5),
                    "midpoint": round(float(c1["high"] + c3["low"]) / 2.0, 5),
                    "time": str(df.index[i - 1]),
                    "gap_size_pips": round(gap_size * 10000, 2)
                })

        # Bearish Implied FVG: c3.high < c1.low
        elif c3["high"] < c1["low"]:
            gap_size = c1["low"] - c3["high"]
            if min_atr <= 0 or gap_size >= min_atr * 0.2:
                implied_fvgs.append({
                    "type": "bearish_implied_fvg",
                    "gap_low": round(float(c3["high"]), 5),
                    "gap_high": round(float(c1["low"]), 5),
                    "midpoint": round(float(c1["low"] + c3["high"]) / 2.0, 5),
                    "time": str(df.index[i - 1]),
                    "gap_size_pips": round(gap_size * 10000, 2)
                })

    return implied_fvgs
