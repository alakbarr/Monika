"""
Deterministic Invariant Engine.

Pre-computes deterministic mathematical bounding boxes (SL ranges, TP ranges,
R:R thresholds, TimesFM bounds) and identifies valid structural anchor candidates
BEFORE invoking the LLM.

Eliminates LLM mental arithmetic and floating-point calculation hallucinations,
converting decision-making into structured discrete anchor selection.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TradingAgent.InvariantCalculator")


def extract_price_precision(symbol: str) -> int:
    """Returns price decimal precision based on asset class."""
    sym = (symbol or "").strip().upper()
    if any(k in sym for k in ("JPY", "XAG", "XTI", "XBR", "BRENT")):
        return 3
    if any(k in sym for k in ("XAU", "ETH")):
        return 2
    if "BTC" in sym:
        return 1
    return 5


def compute_trade_invariants(
    symbol: str,
    current_price: float,
    atr: float,
    adr_5d: float,
    smc_zones: Optional[List[Dict[str, Any]]] = None,
    sr_zones: Optional[List[Any]] = None,
    timesfm_envelope: Optional[Dict[str, Any]] = None,
    min_rr: float = 1.3,
    max_adr_sl_pct: float = 0.35,
    tp_adr_min_pct: float = 0.50,
    tp_adr_max_pct: float = 0.80,
) -> Dict[str, Any]:
    """
    Computes strict deterministic invariants for BUY and SELL scenarios.
    
    Args:
        symbol: Trading instrument (e.g. 'EURUSD', 'XAUUSD')
        current_price: Latest market / candle close price
        atr: 14-period Average True Range (H4)
        adr_5d: 5-day Average Daily Range
        smc_zones: SMC zones (FVG, OB, Liquidity Sweeps)
        sr_zones: Support / Resistance levels
        timesfm_envelope: TimesFM statistical quantile envelope ({'q10': float, 'q90': float})
        min_rr: Minimum required Risk:Reward ratio
        max_adr_sl_pct: Maximum SL distance as fraction of ADR
        tp_adr_min_pct: Minimum TP distance as fraction of ADR
        tp_adr_max_pct: Maximum TP distance as fraction of ADR
        
    Returns:
        Structured dictionary containing exact bounding boxes, candidate anchors, and guidance.
    """
    prec = extract_price_precision(symbol)
    curr_px = float(current_price) if current_price else 0.0
    atr_val = float(atr) if atr and atr > 0 else (curr_px * 0.005 if curr_px > 0 else 1.0)
    adr_val = float(adr_5d) if adr_5d and adr_5d > 0 else (atr_val * 2.0)

    # --- BUY BOUNDS ---
    # SL must be at least 1.0x ATR below entry, max 35% of ADR or 2.5x ATR
    buy_sl_max = round(curr_px - (1.0 * atr_val), prec)
    max_sl_dist = min(2.5 * atr_val, max_adr_sl_pct * adr_val if adr_val > 0 else 2.5 * atr_val)
    buy_sl_min = round(curr_px - max_sl_dist, prec)

    # TP must be within 50-80% of ADR
    buy_tp_min = round(curr_px + (tp_adr_min_pct * adr_val if adr_val > 0 else 1.5 * atr_val), prec)
    buy_tp_max = round(curr_px + (tp_adr_max_pct * adr_val if adr_val > 0 else 3.0 * atr_val), prec)

    # TimesFM statistical cap for BUY (do not target above Q90)
    if timesfm_envelope and isinstance(timesfm_envelope, dict):
        q90 = timesfm_envelope.get("q90") or timesfm_envelope.get("upper_bound")
        if q90 is not None:
            try:
                q90_val = float(q90)
                if q90_val > curr_px:
                    buy_tp_max = round(min(buy_tp_max, q90_val), prec)
            except (ValueError, TypeError):
                pass

    # --- SELL BOUNDS ---
    # SL must be at least 1.0x ATR above entry, max 35% of ADR or 2.5x ATR
    sell_sl_min = round(curr_px + (1.0 * atr_val), prec)
    sell_sl_max = round(curr_px + max_sl_dist, prec)

    # TP must be within 50-80% of ADR below entry
    sell_tp_max = round(curr_px - (tp_adr_min_pct * adr_val if adr_val > 0 else 1.5 * atr_val), prec)
    sell_tp_min = round(curr_px - (tp_adr_max_pct * adr_val if adr_val > 0 else 3.0 * atr_val), prec)

    # TimesFM statistical cap for SELL (do not target below Q10)
    if timesfm_envelope and isinstance(timesfm_envelope, dict):
        q10 = timesfm_envelope.get("q10") or timesfm_envelope.get("lower_bound")
        if q10 is not None:
            try:
                q10_val = float(q10)
                if q10_val < curr_px:
                    sell_tp_min = round(max(sell_tp_min, q10_val), prec)
            except (ValueError, TypeError):
                pass

    # --- EXTRACT DISCRETE STRUCTURAL ANCHORS ---
    anchors: List[Dict[str, Any]] = []
    max_search_dist = 2.0 * atr_val

    # Parse SMC zones
    if smc_zones and isinstance(smc_zones, list):
        for z in smc_zones:
            if not isinstance(z, dict):
                continue
            z_px = z.get("price") or z.get("level") or z.get("low") or z.get("high")
            if z_px is not None:
                try:
                    px_f = float(z_px)
                    dist = abs(px_f - curr_px)
                    if dist <= max_search_dist:
                        anchors.append({
                            "type": z.get("type", "SMC_ZONE"),
                            "price": round(px_f, prec),
                            "distance_atr": round(dist / atr_val, 2),
                            "basis": f"SMC {z.get('type', 'Zone')} @ {px_f:.{prec}f}"
                        })
                except (ValueError, TypeError):
                    continue

    # Parse S/R zones
    if sr_zones and isinstance(sr_zones, list):
        for r in sr_zones:
            px_f = None
            if isinstance(r, dict):
                px_f = r.get("price") or r.get("level")
            elif isinstance(r, (int, float)):
                px_f = float(r)
            if px_f is not None:
                try:
                    px_f = float(px_f)
                    dist = abs(px_f - curr_px)
                    if dist <= max_search_dist:
                        anchors.append({
                            "type": "SR_LEVEL",
                            "price": round(px_f, prec),
                            "distance_atr": round(dist / atr_val, 2),
                            "basis": f"S/R Level @ {px_f:.{prec}f}"
                        })
                except (ValueError, TypeError):
                    continue

    # Sort anchors by distance to current price
    anchors.sort(key=lambda a: a["distance_atr"])
    unique_anchors = []
    seen_px = set()
    for a in anchors:
        if a["price"] not in seen_px:
            unique_anchors.append(a)
            seen_px.add(a["price"])

    return {
        "symbol": symbol,
        "current_price": curr_px,
        "atr_14": round(atr_val, prec),
        "adr_5d": round(adr_val, prec),
        "min_rr_ratio": min_rr,
        "buy_bounds": {
            "sl_range": [buy_sl_min, buy_sl_max],
            "tp_range": [buy_tp_min, buy_tp_max],
            "guidance": f"SL: [{buy_sl_min}..{buy_sl_max}], TP: [{buy_tp_min}..{buy_tp_max}] (>= {min_rr} R:R)"
        },
        "sell_bounds": {
            "sl_range": [sell_sl_min, sell_sl_max],
            "tp_range": [sell_tp_min, sell_tp_max],
            "guidance": f"SL: [{sell_sl_min}..{sell_sl_max}], TP: [{sell_tp_min}..{sell_tp_max}] (>= {min_rr} R:R)"
        },
        "structural_anchors": unique_anchors[:8],
        "precision": prec
    }


def format_invariants_for_prompt(invariants: Dict[str, Any]) -> str:
    """
    Renders pre-computed invariants into a dense telegraphic prompt block.
    """
    sym = invariants.get("symbol", "")
    px = invariants.get("current_price", 0.0)
    atr = invariants.get("atr_14", 0.0)
    adr = invariants.get("adr_5d", 0.0)
    min_rr = invariants.get("min_rr_ratio", 1.3)
    b_sl = invariants.get("buy_bounds", {}).get("sl_range", [0, 0])
    b_tp = invariants.get("buy_bounds", {}).get("tp_range", [0, 0])
    s_sl = invariants.get("sell_bounds", {}).get("sl_range", [0, 0])
    s_tp = invariants.get("sell_bounds", {}).get("tp_range", [0, 0])
    anchors = invariants.get("structural_anchors", [])

    lines = [
        f"=== PRE-COMPUTED TRADE INVARIANTS ({sym} @ {px}) ===",
        f"Microstructure: ATR_14={atr} | 5-day ADR={adr} | Min R:R={min_rr:.1f}",
        f"BUY INVARIANTS : SL MUST be in [{b_sl[0]} - {b_sl[1]}], TP MUST be in [{b_tp[0]} - {b_tp[1]}]",
        f"SELL INVARIANTS: SL MUST be in [{s_sl[0]} - {s_sl[1]}], TP MUST be in [{s_tp[0]} - {s_tp[1]}]",
    ]

    if anchors:
        lines.append("VALID STRUCTURAL ANCHORS (select from these verified levels):")
        for a in anchors[:5]:
            lines.append(f"  * {a['type']} @ {a['price']} ({a['distance_atr']}x ATR) -> {a['basis']}")
    else:
        lines.append("VALID STRUCTURAL ANCHORS: No immediate zone within 2x ATR. Require extra confirmation.")

    lines.append("MANDATE: Select SL and TP that conform strictly to these pre-computed bounds. Zero manual floating-point math.")
    lines.append("=== END INVARIANTS ===")
    return "\n".join(lines)
