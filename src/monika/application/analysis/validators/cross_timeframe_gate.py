"""
File: analysis/validators/cross_timeframe_gate.py
Cross-Timeframe Confirmation Gate (HTF Alignment Sentinel).
Enforces H4 + H1 directional alignment before allowing intraday (M15) trade entry.
Rejects counter-trend entries (e.g. M15 BUY into dual H4+H1 bearish structure).
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

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
        dealing_range_pos: Optional[float] = None,
        regime_classification: Optional[str] = None,
        has_liquidity_sweep: bool = False,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Verify if decision ('buy' or 'sell') aligns with H4 and H1 structures.
        Supports Institutional Discount Accumulation (pos <= 0.38) and Premium Distribution (pos >= 0.65) protocols.
        Returns:
            (is_aligned: bool, reason: str, metadata: dict)
        """
        dec = decision.strip().lower()
        if dec not in ("buy", "sell"):
            return True, "Non-directional decision (wait/skip)", {}

        # Resolve spatial & regime context from parameters or data_bundle
        if dealing_range_pos is None and isinstance(data_bundle, dict):
            inv = data_bundle.get("precomputed_invariants")
            if isinstance(inv, dict) and "dealing_range_pos" in inv:
                try:
                    dealing_range_pos = float(inv["dealing_range_pos"])
                except TypeError, ValueError:
                    pass
            if dealing_range_pos is None and "dealing_range_pos" in data_bundle:
                try:
                    dealing_range_pos = float(data_bundle["dealing_range_pos"])
                except TypeError, ValueError:
                    pass

        if regime_classification is None and isinstance(data_bundle, dict):
            inv = data_bundle.get("precomputed_invariants")
            if isinstance(inv, dict) and inv.get("regime_classification"):
                regime_classification = str(inv["regime_classification"])
            if regime_classification is None and data_bundle.get("regime_classification"):
                regime_classification = str(data_bundle["regime_classification"])
            if regime_classification is None and data_bundle.get("market_regime"):
                mr = data_bundle["market_regime"]
                if isinstance(mr, dict):
                    regime_classification = str(mr.get(symbol) or mr.get("regime"))
                else:
                    regime_classification = str(mr)

        if not has_liquidity_sweep and isinstance(data_bundle, dict):
            inv = data_bundle.get("precomputed_invariants")
            if isinstance(inv, dict):
                has_liquidity_sweep = bool(inv.get("liquidity_sweep_detected") or inv.get("liquidity_sweep_bias"))
            if not has_liquidity_sweep:
                has_liquidity_sweep = bool(data_bundle.get("liquidity_sweep_detected"))

        h4_bias = cls._extract_timeframe_bias(data_bundle, tf="H4")
        h1_bias = cls._extract_timeframe_bias(data_bundle, tf="H1")
        reg_upper = str(regime_classification or "").upper()

        meta = {
            "h4_bias": h4_bias,
            "h1_bias": h1_bias,
            "decision": dec,
            "dealing_range_pos": dealing_range_pos,
            "regime_classification": regime_classification,
            "has_liquidity_sweep": has_liquidity_sweep,
        }

        # Case 1: Dual Higher Timeframe Conflict
        # If BUY, but BOTH H4 and H1 are bearish:
        # Permitted if in institutional discount accumulation zone (pos <= 0.38) or confirmed liquidity sweep
        if dec == "buy":
            if h4_bias == "bearish" and h1_bias == "bearish":
                is_discount_acc = (dealing_range_pos is not None and dealing_range_pos <= 0.38) or (
                    "DISCOUNT_ACCUMULATION" in reg_upper
                )
                if is_discount_acc or has_liquidity_sweep:
                    pos_str = f"pos={dealing_range_pos:.2f}" if dealing_range_pos is not None else "regime"
                    logger.info(
                        f"[{symbol}] CrossTimeframeGate: Permitted BUY under Discount Accumulation protocol "
                        f"({pos_str}, sweep={has_liquidity_sweep})"
                    )
                    return (
                        True,
                        f"HTF confirmation passed under Institutional Discount Accumulation protocol ({pos_str})",
                        meta,
                    )
                reason = (
                    "Dual HTF conflict: M15 BUY rejected because both H4 and H1 are strongly bearish outside discount"
                )
                logger.warning(f"[{symbol}] CrossTimeframeGate REJECT: {reason}")
                return False, reason, meta

        # If SELL, but BOTH H4 and H1 are bullish:
        # Permitted if in institutional premium distribution zone (pos >= 0.65) or confirmed liquidity sweep
        elif dec == "sell":
            if h4_bias == "bullish" and h1_bias == "bullish":
                is_premium_dist = (dealing_range_pos is not None and dealing_range_pos >= 0.65) or (
                    "PREMIUM_DISTRIBUTION" in reg_upper
                )
                if is_premium_dist or has_liquidity_sweep:
                    pos_str = f"pos={dealing_range_pos:.2f}" if dealing_range_pos is not None else "regime"
                    logger.info(
                        f"[{symbol}] CrossTimeframeGate: Permitted SELL under Premium Distribution protocol "
                        f"({pos_str}, sweep={has_liquidity_sweep})"
                    )
                    return (
                        True,
                        f"HTF confirmation passed under Institutional Premium Distribution protocol ({pos_str})",
                        meta,
                    )
                reason = (
                    "Dual HTF conflict: M15 SELL rejected because both H4 and H1 are strongly bullish outside premium"
                )
                logger.warning(f"[{symbol}] CrossTimeframeGate REJECT: {reason}")
                return False, reason, meta

        # Case 2: Direct major trend conflict if single TF pullback disallowed
        if not allow_single_tf_pullback:
            opp_bias = "bearish" if dec == "buy" else "bullish"
            if h4_bias == opp_bias:
                is_spatial_reversal = (
                    dec == "buy"
                    and ((dealing_range_pos is not None and dealing_range_pos <= 0.38) or has_liquidity_sweep)
                ) or (
                    dec == "sell"
                    and ((dealing_range_pos is not None and dealing_range_pos >= 0.65) or has_liquidity_sweep)
                )
                if not is_spatial_reversal:
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
        # 1. Technical Indicators (Fix 6.6: Do not fallback to H4 for H1)
        tech_key = f"get_technical_indicators_{tf}"
        tech = data_bundle.get(tech_key)
        if tech is None and tf == "H4":
            tech = data_bundle.get("get_technical_indicators")
        if isinstance(tech, dict):
            # Check explicit trend field
            trend = str(tech.get("trend") or "").lower()
            if "bull" in trend or "up" in trend:
                return "bullish"
            if "bear" in trend or "down" in trend:
                return "bearish"

            # Check EMA crossover / price relation
            ind_dict = tech.get("indicators") if isinstance(tech.get("indicators"), dict) else tech
            close_px = tech.get("close")
            if close_px is None:
                hist_b = data_bundle.get(f"get_price_history_{tf}")
                if isinstance(hist_b, dict) and hist_b.get("bars"):
                    close_px = hist_b["bars"][-1].get("close")

            def _get_val(k_list):
                if not isinstance(ind_dict, dict):
                    return None
                for k in k_list:
                    item = ind_dict.get(k)
                    if isinstance(item, dict):
                        v = item.get("value") or item.get("ema") or item.get("sma")
                        if v is not None:
                            return float(v)
                    elif isinstance(item, (int, float)):
                        return float(item)
                return None

            ema20 = _get_val(["EMA_20", "ema_20", "EMA20", "ema20", "SMA_20"])
            ema50 = _get_val(["EMA_50", "ema_50", "EMA50", "ema50", "SMA_50"])

            if close_px and ema50:
                if close_px > ema50 and (not ema20 or ema20 > ema50):
                    return "bullish"
                if close_px < ema50 and (not ema20 or ema20 < ema50):
                    return "bearish"

        # 2. Structure Breaks (SMC BOS / CHoCH)
        struct_key = f"get_structure_breaks_{tf}"
        struct = data_bundle.get(struct_key)
        if struct is None and tf == "H4":
            struct = data_bundle.get("get_structure_breaks")
        if isinstance(struct, dict):
            breaks = struct.get("breaks") or struct.get("structure_breaks") or []
            if isinstance(breaks, list) and breaks:
                # Get the latest break by checking both index 0 and -1 timestamp
                latest_break = breaks[0] if isinstance(breaks[0], dict) else {}
                if len(breaks) > 1 and isinstance(breaks[-1], dict):
                    t0 = str(latest_break.get("time") or latest_break.get("formed_at") or "")
                    t_last = str(breaks[-1].get("time") or breaks[-1].get("formed_at") or "")
                    if t_last > t0:
                        latest_break = breaks[-1]

                b_type = str(latest_break.get("type", "")).lower()
                b_dir = str(latest_break.get("direction", "")).lower()
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
