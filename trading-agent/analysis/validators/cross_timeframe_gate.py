"""
File: analysis/validators/cross_timeframe_gate.py
Cross-Timeframe Confirmation Gate (HTF Alignment Sentinel).
Enforces H4 + H1 directional alignment before allowing intraday (M15) trade entry.
Rejects counter-trend entries (e.g. M15 BUY into dual H4+H1 bearish structure).
"""

from typing import Dict, Any, Tuple, Optional, List
import logging

logger = logging.getLogger("TradingAgent.Analysis.CrossTimeframeGate")


class CrossTimeframeConfirmationGate:
    """
    Validates that intraday entry decisions (BUY / SELL) are confirmed by higher timeframes (H4 and H1).
    Strictly forbids knife-catching against dual-timeframe higher timeframe trends.
    """

    @classmethod
    def verify_htf_alignment(
        cls,
        decision: str,
        data_bundle: Dict[str, Any],
        symbol: str = "",
        allow_single_tf_pullback: bool = True,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Verify if decision ('buy' or 'sell') aligns with H4 and H1 structures.
        Returns:
            (is_aligned: bool, reason: str, metadata: dict)
        """
        dec = decision.strip().lower()
        if dec not in ("buy", "sell"):
            return True, "Non-directional decision (wait/skip)", {}

        h4_bias = cls._extract_timeframe_bias(data_bundle, tf="H4")
        h1_bias = cls._extract_timeframe_bias(data_bundle, tf="H1")

        meta = {
            "h4_bias": h4_bias,
            "h1_bias": h1_bias,
            "decision": dec,
        }

        # Case 1: Dual Higher Timeframe Conflict
        # If BUY, but BOTH H4 and H1 are bearish -> Severe counter-trend entry
        if dec == "buy":
            if h4_bias == "bearish" and h1_bias == "bearish":
                reason = "Dual HTF conflict: M15 BUY rejected because both H4 and H1 are strongly bearish"
                logger.warning(f"[{symbol}] CrossTimeframeGate REJECT: {reason}")
                return False, reason, meta

        # If SELL, but BOTH H4 and H1 are bullish -> Severe counter-trend entry
        elif dec == "sell":
            if h4_bias == "bullish" and h1_bias == "bullish":
                reason = "Dual HTF conflict: M15 SELL rejected because both H4 and H1 are strongly bullish"
                logger.warning(f"[{symbol}] CrossTimeframeGate REJECT: {reason}")
                return False, reason, meta

        # Case 2: Direct major trend conflict if single TF pullback disallowed
        if not allow_single_tf_pullback:
            opp_bias = "bearish" if dec == "buy" else "bullish"
            if h4_bias == opp_bias:
                reason = f"HTF conflict: M15 {dec.upper()} conflicts with H4 {h4_bias}"
                return False, reason, meta

        return True, "HTF confirmation passed", meta

    @classmethod
    def _extract_timeframe_bias(cls, data_bundle: Dict[str, Any], tf: str) -> str:
        """
        Extract directional bias ('bullish', 'bearish', or 'neutral') from data bundle for timeframe tf.
        Checks:
        1. get_technical_indicators_{tf} (EMA20, EMA50, RSI, MACD, trend)
        2. get_structure_breaks_{tf} (BOS, CHoCH)
        3. get_price_history_{tf} (close vs EMA or multi-bar momentum)
        """
        # 1. Technical Indicators
        tech_key = f"get_technical_indicators_{tf}"
        tech = data_bundle.get(tech_key) or data_bundle.get("get_technical_indicators")
        if isinstance(tech, dict):
            # Check explicit trend field
            trend = str(tech.get("trend") or "").lower()
            if "bull" in trend or "up" in trend:
                return "bullish"
            if "bear" in trend or "down" in trend:
                return "bearish"

            # Check EMA crossover / price relation
            close_px = tech.get("close")
            ema20 = tech.get("ema_20") or tech.get("ema20")
            ema50 = tech.get("ema_50") or tech.get("ema50")
            if close_px and ema50:
                if close_px > ema50 and (not ema20 or ema20 > ema50):
                    return "bullish"
                if close_px < ema50 and (not ema20 or ema20 < ema50):
                    return "bearish"

        # 2. Structure Breaks (SMC BOS / CHoCH)
        struct_key = f"get_structure_breaks_{tf}"
        struct = data_bundle.get(struct_key) or data_bundle.get("get_structure_breaks")
        if isinstance(struct, dict):
            breaks = struct.get("breaks") or struct.get("structure_breaks") or []
            if isinstance(breaks, list) and breaks:
                last_break = breaks[-1] if isinstance(breaks[-1], dict) else {}
                b_type = str(last_break.get("type", "")).lower()
                b_dir = str(last_break.get("direction", "")).lower()
                if "bull" in b_dir or "bullish" in b_type:
                    return "bullish"
                if "bear" in b_dir or "bearish" in b_type:
                    return "bearish"

        # 3. Price History Trend (Last vs 10 bars ago)
        hist_key = f"get_price_history_{tf}"
        hist = data_bundle.get(hist_key)
        if isinstance(hist, dict):
            bars = hist.get("bars", [])
            if isinstance(bars, list) and len(bars) >= 10:
                c_now = bars[-1].get("close")
                c_prev = bars[-10].get("close")
                if c_now and c_prev:
                    pct_chg = (c_now - c_prev) / c_prev
                    if pct_chg > 0.008:
                        return "bullish"
                    if pct_chg < -0.008:
                        return "bearish"

        return "neutral"
