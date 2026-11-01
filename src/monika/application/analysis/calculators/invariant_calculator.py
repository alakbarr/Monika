"""
Deterministic Invariant Engine.

Pre-computes deterministic mathematical bounding boxes (SL ranges, TP ranges,
R:R thresholds, TimesFM bounds) and identifies valid structural anchor candidates
BEFORE invoking the LLM.

Eliminates LLM mental arithmetic and floating-point calculation hallucinations,
converting decision-making into structured discrete anchor selection.
"""

import logging
from typing import Any, Dict, List, Optional

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


def _iter_smc_zone_dicts(smc_zones: Any) -> List[Dict[str, Any]]:
    """Normalizes SMC zones input (list of dicts or dict with order_blocks/fair_value_gaps) into active zone dicts."""
    raw_list: List[Any] = []
    if isinstance(smc_zones, list):
        raw_list = smc_zones
    elif isinstance(smc_zones, dict):
        for key in ("zones", "order_blocks", "fair_value_gaps", "fvg_zones"):
            val = smc_zones.get(key)
            if isinstance(val, list):
                raw_list.extend(val)

    active: List[Dict[str, Any]] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        if item.get("mitigated") is True or item.get("filled") is True:
            continue
        active.append(item)
    return active


def _extract_zone_direction_and_price(z: Dict[str, Any]) -> tuple[str, Optional[float], str]:
    """Extracts ('bull'|'bear'|'neutral', anchor_price, zone_label) from an SMC zone dict."""
    dir_str = str(z.get("direction", "") or "").lower()
    type_str = str(z.get("type", "") or z.get("zone_type", "") or "").lower()

    is_bull = ("bull" in dir_str) or any(
        k in type_str for k in ("demand", "fvg_bull", "ob_bull", "discount", "sweep_low", "bull")
    )
    is_bear = ("bear" in dir_str) or any(
        k in type_str for k in ("supply", "fvg_bear", "ob_bear", "premium", "sweep_high", "bear")
    )

    if is_bull:
        raw_px = (
            z.get("price")
            or z.get("level")
            or z.get("gap_high")
            or z.get("price_high")
            or z.get("low")
            or z.get("gap_low")
            or z.get("price_low")
        )
    elif is_bear:
        raw_px = (
            z.get("price")
            or z.get("level")
            or z.get("gap_low")
            or z.get("price_low")
            or z.get("high")
            or z.get("gap_high")
            or z.get("price_high")
        )
    else:
        raw_px = (
            z.get("price")
            or z.get("level")
            or z.get("gap_high")
            or z.get("price_high")
            or z.get("low")
            or z.get("high")
            or z.get("gap_low")
            or z.get("price_low")
        )

    px_val: Optional[float] = None
    if raw_px is not None:
        try:
            px_val = float(raw_px)
        except ValueError, TypeError:
            px_val = None

    explicit_type = z.get("type")
    if explicit_type and str(explicit_type).strip().lower() not in ("bullish", "bearish"):
        z_label = str(explicit_type)
    elif "gap_low" in z or "gap_high" in z:
        z_label = "FVG_BULL" if is_bull else ("FVG_BEAR" if is_bear else "FVG")
    elif "price_low" in z or "price_high" in z:
        z_label = "OB_BULL" if is_bull else ("OB_BEAR" if is_bear else "ORDER_BLOCK")
    else:
        z_label = str(explicit_type or "SMC_ZONE")

    polarity = "bull" if is_bull else ("bear" if is_bear else "neutral")
    return polarity, px_val, z_label


def compute_trade_invariants(
    symbol: str,
    current_price: float,
    atr: float,
    adr_5d: float,
    smc_zones: Optional[Any] = None,
    sr_zones: Optional[Any] = None,
    timesfm_envelope: Optional[Dict[str, Any]] = None,
    min_rr: float = 1.5,
    max_adr_sl_pct: float = 0.35,
    tp_adr_min_pct: float = 0.50,
    tp_adr_max_pct: float = 0.80,
    regime_classification: Optional[str] = None,
    h4_impulse_atr: Optional[float] = None,
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
    # SOTA: Floor max_sl_dist at 1.35x ATR on volatile/commodity/crypto and 1.25x ATR on FX to prevent inverted intervals
    sym_calc = str(symbol or "").upper()
    is_calc_high_vol = any(k in sym_calc for k in ("BTC", "ETH", "SOL", "XAU", "XAG", "XTI", "XBR", "BRENT", "WTI"))
    min_noise_floor = 1.35 * atr_val if is_calc_high_vol else 1.25 * atr_val
    max_sl_dist = max(min_noise_floor, max_adr_sl_pct * adr_val if adr_val > 0 else 2.5 * atr_val)
    max_sl_dist = min(2.5 * atr_val, max_sl_dist)
    buy_sl_max = round(curr_px - (1.0 * atr_val), prec)
    buy_sl_min = round(curr_px - max_sl_dist, prec)
    if buy_sl_min > buy_sl_max:
        buy_sl_min = round(buy_sl_max - (0.2 * atr_val), prec)

    # TP must be within 50-80% of ADR, expanded when ATR noise floor requires wider targets
    tp_min_dist = max(tp_adr_min_pct * adr_val if adr_val > 0 else 1.5 * atr_val, 1.0 * atr_val * min_rr)
    tp_max_dist = max(
        tp_adr_max_pct * adr_val if adr_val > 0 else 3.0 * atr_val,
        max_sl_dist * max(min_rr, 1.65),
        tp_min_dist,
    )
    buy_tp_min = round(curr_px + tp_min_dist, prec)
    buy_tp_max = round(curr_px + tp_max_dist, prec)

    # TimesFM statistical cap for BUY (do not target above Q90)
    if timesfm_envelope and isinstance(timesfm_envelope, dict):
        q90 = timesfm_envelope.get("q90") or timesfm_envelope.get("upper_bound")
        if q90 is not None:
            try:
                q90_val = float(q90)
                if q90_val > curr_px:
                    buy_tp_max = max(buy_tp_min, round(min(buy_tp_max, q90_val), prec))
            except ValueError, TypeError:
                pass

    # --- SELL BOUNDS ---
    # SL must be at least 1.0x ATR above entry, max 35% of ADR or 2.5x ATR
    sell_sl_min = round(curr_px + (1.0 * atr_val), prec)
    sell_sl_max = round(curr_px + max_sl_dist, prec)
    if sell_sl_max < sell_sl_min:
        sell_sl_max = round(sell_sl_min + (0.2 * atr_val), prec)

    # TP must be within 50-80% of ADR below entry, expanded when ATR noise floor requires wider targets
    sell_tp_max = round(curr_px - tp_min_dist, prec)
    sell_tp_min = round(curr_px - tp_max_dist, prec)

    # TimesFM statistical cap for SELL (do not target below Q10)
    if timesfm_envelope and isinstance(timesfm_envelope, dict):
        q10 = timesfm_envelope.get("q10") or timesfm_envelope.get("lower_bound")
        if q10 is not None:
            try:
                q10_val = float(q10)
                if q10_val < curr_px:
                    sell_tp_min = min(sell_tp_max, round(max(sell_tp_min, q10_val), prec))
            except ValueError, TypeError:
                pass

    # --- EXTRACT DISCRETE STRUCTURAL ANCHORS ---
    anchors: List[Dict[str, Any]] = []
    max_search_dist = 2.0 * atr_val

    # Parse SMC zones
    for z in _iter_smc_zone_dicts(smc_zones):
        _, px_f, z_label = _extract_zone_direction_and_price(z)
        if px_f is not None:
            dist = abs(px_f - curr_px)
            if dist <= max_search_dist:
                anchors.append(
                    {
                        "type": z_label,
                        "price": round(px_f, prec),
                        "distance_atr": round(dist / atr_val, 2),
                        "basis": f"SMC {z_label} @ {px_f:.{prec}f}",
                    }
                )

    # Parse S/R zones
    sr_list: List[Any] = []
    if isinstance(sr_zones, list):
        sr_list = sr_zones
    elif isinstance(sr_zones, dict):
        for k in ("sr_zones", "levels", "zones"):
            if isinstance(sr_zones.get(k), list):
                sr_list.extend(sr_zones[k])

    for r in sr_list:
        px_f = None
        if isinstance(r, dict):
            px_f = r.get("price") or r.get("level") or r.get("price_low") or r.get("price_high")
        elif isinstance(r, (int, float)):
            px_f = float(r)
        if px_f is not None:
            try:
                px_f = float(px_f)
                dist = abs(px_f - curr_px)
                if dist <= max_search_dist:
                    anchors.append(
                        {
                            "type": "SR_LEVEL",
                            "price": round(px_f, prec),
                            "distance_atr": round(dist / atr_val, 2),
                            "basis": f"S/R Level @ {px_f:.{prec}f}",
                        }
                    )
            except ValueError, TypeError:
                continue

    # Sort anchors by distance to current price
    anchors.sort(key=lambda a: a["distance_atr"])
    unique_anchors = []
    seen_px = set()
    for a in anchors:
        if a["price"] not in seen_px:
            unique_anchors.append(a)
            seen_px.add(a["price"])

    # Compute concrete zero-arithmetic bracket candidates (Long Option A vs Short Option B)
    bracket_options = generate_concrete_bracket_options(
        symbol=symbol,
        current_price=curr_px,
        atr=atr_val,
        adr_5d=adr_val,
        smc_zones=smc_zones,
        sr_zones=sr_zones,
        target_rr=max(1.55, min_rr),
        regime_classification=regime_classification,
        h4_impulse_atr=h4_impulse_atr,
    )

    long_opt = bracket_options.get("long_option_a", {})
    if (
        not timesfm_envelope
        and isinstance(long_opt, dict)
        and long_opt.get("stop_loss")
        and long_opt.get("take_profit")
    ):
        buy_sl_min = min(buy_sl_min, float(long_opt["stop_loss"]))
        buy_sl_max = max(buy_sl_max, float(long_opt["stop_loss"]))
        buy_tp_max = max(buy_tp_max, float(long_opt["take_profit"]))

    short_opt = bracket_options.get("short_option_b", {})
    if (
        not timesfm_envelope
        and isinstance(short_opt, dict)
        and short_opt.get("stop_loss")
        and short_opt.get("take_profit")
    ):
        sell_sl_min = min(sell_sl_min, float(short_opt["stop_loss"]))
        sell_sl_max = max(sell_sl_max, float(short_opt["stop_loss"]))
        sell_tp_min = min(sell_tp_min, float(short_opt["take_profit"]))

    return {
        "symbol": symbol,
        "current_price": curr_px,
        "atr_14": round(atr_val, prec),
        "adr_5d": round(adr_val, prec),
        "min_rr_ratio": min_rr,
        "buy_bounds": {
            "sl_range": [buy_sl_min, buy_sl_max],
            "tp_range": [buy_tp_min, buy_tp_max],
            "guidance": f"SL: [{buy_sl_min}..{buy_sl_max}], TP: [{buy_tp_min}..{buy_tp_max}] (>= {min_rr} R:R)",
        },
        "sell_bounds": {
            "sl_range": [sell_sl_min, sell_sl_max],
            "tp_range": [sell_tp_min, sell_tp_max],
            "guidance": f"SL: [{sell_sl_min}..{sell_sl_max}], TP: [{sell_tp_min}..{sell_tp_max}] (>= {min_rr} R:R)",
        },
        "structural_anchors": unique_anchors[:8],
        "bracket_options": bracket_options,
        "precision": prec,
    }


def generate_concrete_bracket_options(
    symbol: str,
    current_price: float,
    atr: float,
    adr_5d: Optional[float] = None,
    smc_zones: Optional[Any] = None,
    sr_zones: Optional[Any] = None,
    target_rr: float = 1.80,
    noise_buffer_atr: Optional[float] = None,
    regime_classification: Optional[str] = None,
    h4_impulse_atr: Optional[float] = None,
) -> Dict[str, Any]:
    """Generates concrete, mathematically verified SL/TP bracket options.

    Eliminates mental arithmetic by pre-computing exact levels with guaranteed
    R:R and noise floor protection. Supports market breakout execution on active impulse.
    """
    prec = extract_price_precision(symbol)
    curr_px = float(current_price) if current_price else 0.0
    atr_val = float(atr) if atr and atr > 0 else (curr_px * 0.005 if curr_px > 0 else 1.0)
    adr_val = float(adr_5d) if adr_5d is not None and float(adr_5d) > 0 else (2.0 * atr_val)
    eff_min_rr = max(1.50, float(target_rr or 1.50))

    sym_clean = str(symbol or "").upper()
    is_fx_major = any(sym_clean.startswith(fx) for fx in ("EUR", "GBP", "AUD", "NZD", "USD")) and not any(
        k in sym_clean for k in ("BTC", "ETH", "SOL", "XAU", "XAG", "XTI", "XBR")
    )
    is_high_vol = any(k in sym_clean for k in ("BTC", "ETH", "SOL", "XAU", "XAG", "XTI", "XBR", "BRENT", "WTI"))
    if noise_buffer_atr is None or float(noise_buffer_atr) <= 0.0:
        eff_noise_buffer = 1.35 if is_high_vol else 1.25
    else:
        eff_noise_buffer = float(noise_buffer_atr)

    impulse_thresh = 0.85 if is_fx_major else 1.25

    reg_str = str(regime_classification or "").upper()
    is_bullish_impulse = ("BULLISH_IMPULSE" in reg_str) or (
        h4_impulse_atr is not None and float(h4_impulse_atr) >= impulse_thresh
    )
    is_bearish_impulse = ("BEARISH_IMPULSE" in reg_str) or (
        h4_impulse_atr is not None and float(h4_impulse_atr) <= -impulse_thresh
    )

    # 1. Long Option A (Demand POI or Breakout Entry)
    zone_dicts = _iter_smc_zone_dicts(smc_zones)
    demand_prices: List[float] = []
    supply_prices: List[float] = []
    for z in zone_dicts:
        polarity, px_val, _ = _extract_zone_direction_and_price(z)
        if px_val is not None and px_val > 0:
            if polarity == "bull":
                demand_prices.append(px_val)
            elif polarity == "bear":
                supply_prices.append(px_val)

    demand_prices = [p for p in demand_prices if (curr_px - 0.75 * atr_val) <= p <= curr_px]
    supply_prices = [p for p in supply_prices if curr_px <= p <= (curr_px + 0.75 * atr_val)]

    if is_bullish_impulse:
        raw_long_entry = curr_px
    elif demand_prices:
        raw_long_entry = min(demand_prices, key=lambda px: abs(px - curr_px))
    else:
        raw_long_entry = curr_px

    long_entry = round(raw_long_entry, prec)
    target_noise_dist = eff_noise_buffer * atr_val
    harmonized_sl_max = max(0.35 * adr_val, target_noise_dist, 1.20 * atr_val)
    harmonized_tp_max = max(0.80 * adr_val, harmonized_sl_max * max(eff_min_rr, 1.65))
    base_sl_cap = min(0.35 * adr_val, target_noise_dist)
    base_sl_cap = min(base_sl_cap, harmonized_tp_max / eff_min_rr)

    long_sl_dist = min(harmonized_sl_max, max(target_noise_dist, base_sl_cap))
    long_sl = round(long_entry - long_sl_dist, prec)
    if long_sl <= 0.0:
        long_sl = round(long_entry * 0.95, prec)
    long_risk = abs(long_entry - long_sl)
    if long_risk <= 0.0:
        long_risk = round(atr_val, prec)
        long_sl = round(long_entry - long_risk, prec)

    if 0.72 * adr_val >= long_risk * eff_min_rr:
        target_long_tp_dist = max(long_risk * eff_min_rr, min(1.55 * atr_val, 0.72 * adr_val))
        eff_long_rr = round(target_long_tp_dist / long_risk, 2)
    else:
        eff_long_rr = eff_min_rr
        if harmonized_tp_max > 0 and (eff_long_rr * long_risk) > harmonized_tp_max * 1.02:
            eff_long_rr = max(1.50, round(harmonized_tp_max / long_risk, 2))
    long_tp = round(long_entry + (eff_long_rr * long_risk), prec)
    long_entry_type = "market" if (is_bullish_impulse or abs(long_entry - curr_px) <= 0.05 * atr_val) else "limit"

    # 2. Short Option B (Supply POI or Breakout Entry)
    if is_bearish_impulse:
        raw_short_entry = curr_px
    elif supply_prices:
        raw_short_entry = min(supply_prices, key=lambda px: abs(px - curr_px))
    else:
        raw_short_entry = curr_px

    short_entry = round(raw_short_entry, prec)
    short_sl_dist = min(harmonized_sl_max, max(target_noise_dist, base_sl_cap))
    short_sl = round(short_entry + short_sl_dist, prec)
    short_risk = abs(short_sl - short_entry)
    if short_risk <= 0.0:
        short_risk = round(atr_val, prec)
        short_sl = round(short_entry + short_risk, prec)

    if 0.72 * adr_val >= short_risk * eff_min_rr:
        target_short_tp_dist = max(short_risk * eff_min_rr, min(1.55 * atr_val, 0.72 * adr_val))
        eff_short_rr = round(target_short_tp_dist / short_risk, 2)
    else:
        eff_short_rr = eff_min_rr
        if harmonized_tp_max > 0 and (eff_short_rr * short_risk) > harmonized_tp_max * 1.02:
            eff_short_rr = max(1.50, round(harmonized_tp_max / short_risk, 2))
    short_tp = round(short_entry - (eff_short_rr * short_risk), prec)
    if short_tp <= 0.0:
        short_tp = round(short_entry * 0.5, prec)
    short_entry_type = "market" if (is_bearish_impulse or abs(short_entry - curr_px) <= 0.05 * atr_val) else "limit"

    long_desc = (
        f"Bullish impulse breakout market entry ({float(h4_impulse_atr or 0.0):+.2f}x ATR impulse) with {eff_long_rr:.2f} R:R and >= {eff_noise_buffer:.2f}x ATR noise buffer"
        if is_bullish_impulse
        else f"Demand POI {long_entry_type} entry with {eff_long_rr:.2f} R:R and >= {eff_noise_buffer:.2f}x ATR noise buffer"
    )
    short_desc = (
        f"Bearish impulse breakout market entry ({float(h4_impulse_atr or 0.0):+.2f}x ATR impulse) with {eff_short_rr:.2f} R:R and >= {eff_noise_buffer:.2f}x ATR noise buffer"
        if is_bearish_impulse
        else f"Supply POI {short_entry_type} entry with {eff_short_rr:.2f} R:R and >= {eff_noise_buffer:.2f}x ATR noise buffer"
    )

    return {
        "long_option_a": {
            "name": "LONG_OPTION_A",
            "direction": "buy",
            "entry": long_entry,
            "entry_type": long_entry_type,
            "stop_loss": long_sl,
            "take_profit": long_tp,
            "rr_ratio": eff_long_rr,
            "sl_distance_atr": round(long_risk / max(1e-7, atr_val), 2),
            "description": long_desc,
        },
        "short_option_b": {
            "name": "SHORT_OPTION_B",
            "direction": "sell",
            "entry": short_entry,
            "entry_type": short_entry_type,
            "stop_loss": short_sl,
            "take_profit": short_tp,
            "rr_ratio": eff_short_rr,
            "sl_distance_atr": round(short_risk / max(1e-7, atr_val), 2),
            "description": short_desc,
        },
    }


def resolve_bracket_choice(
    choice: Optional[str],
    bracket_options: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Normalizes a bracket choice identifier and extracts the matching pre-computed bracket.

    Accepts:
      - 'LONG_OPTION_A', 'OPTION_A', 'OPTION A', 'A', 'LONG', 'BUY'
      - 'SHORT_OPTION_B', 'OPTION_B', 'OPTION B', 'B', 'SHORT', 'SELL'
    Returns:
      A dictionary with keys {'name', 'direction', 'entry', 'stop_loss', 'take_profit', 'rr_ratio', 'sl_distance_atr'}
      or None if unresolvable.
    """
    if not choice or not bracket_options or not isinstance(bracket_options, dict):
        return None

    raw = str(choice).strip().upper()
    if any(k in raw for k in ("LONG_OPTION_A", "OPTION_A", "OPTION A")) or raw in ("A", "LONG", "BUY"):
        return bracket_options.get("long_option_a")
    if any(k in raw for k in ("SHORT_OPTION_B", "OPTION_B", "OPTION B")) or raw in ("B", "SHORT", "SELL"):
        return bracket_options.get("short_option_b")

    for key, val in bracket_options.items():
        if key.upper() == raw or key.replace("_", "").upper() == raw.replace("_", ""):
            return val
        if isinstance(val, dict) and str(val.get("name", "")).upper() == raw:
            return val

    return None


def format_invariants_for_prompt(invariants: Dict[str, Any]) -> str:
    """
    Renders pre-computed invariants into a dense telegraphic prompt block.
    """
    sym = invariants.get("symbol", "")
    px = invariants.get("current_price", 0.0)
    atr = invariants.get("atr_14", 0.0)
    adr = invariants.get("adr_5d", 0.0)
    min_rr = invariants.get("min_rr_ratio", 1.5)
    b_sl = invariants.get("buy_bounds", {}).get("sl_range", [0, 0])
    b_tp = invariants.get("buy_bounds", {}).get("tp_range", [0, 0])
    s_sl = invariants.get("sell_bounds", {}).get("sl_range", [0, 0])
    s_tp = invariants.get("sell_bounds", {}).get("tp_range", [0, 0])
    anchors = invariants.get("structural_anchors", [])
    bracket_options = invariants.get("bracket_options", {})

    lines = [
        f"=== PRE-COMPUTED TRADE INVARIANTS ({sym} @ {px}) ===",
        f"Microstructure: ATR_14={atr} | 5-day ADR={adr} | Min R:R={min_rr:.1f}",
        f"BUY INVARIANTS : SL MUST be in [{b_sl[0]} - {b_sl[1]}], TP MUST be in [{b_tp[0]} - {b_tp[1]}]",
        f"SELL INVARIANTS: SL MUST be in [{s_sl[0]} - {s_sl[1]}], TP MUST be in [{s_tp[0]} - {s_tp[1]}]",
    ]

    if bracket_options:
        long_b = bracket_options.get("long_option_a", {})
        short_b = bracket_options.get("short_option_b", {})
        lines.append(
            "=== PRE-COMPUTED VERIFIED BRACKET OPTIONS (Pre-Verified R:R >= 1.50, Zero Arithmetic Required) ==="
        )
        lines.append(
            f"  [LONG_OPTION_A] : Entry={long_b.get('entry')} | SL={long_b.get('stop_loss')} | TP={long_b.get('take_profit')} (Exact R:R={long_b.get('rr_ratio', 1.8):.2f})"
        )
        lines.append(
            f"  [SHORT_OPTION_B]: Entry={short_b.get('entry')} | SL={short_b.get('stop_loss')} | TP={short_b.get('take_profit')} (Exact R:R={short_b.get('rr_ratio', 1.8):.2f})"
        )
        lines.append(
            "  * INSTRUCTION: Adopt one of the verified options above (set adopted_bracket='LONG_OPTION_A' or 'SHORT_OPTION_B') to eliminate mental math errors, or specify explicit entry/stop_loss/take_profit conforming to bounds. Select WAIT only if market regime has no clear directional edge or invalidates both options."
        )

    if anchors:
        lines.append("VALID STRUCTURAL ANCHORS (select from these verified levels):")
        for a in anchors[:5]:
            lines.append(f"  * {a['type']} @ {a['price']} ({a['distance_atr']}x ATR) -> {a['basis']}")
    else:
        lines.append("VALID STRUCTURAL ANCHORS: No immediate zone within 2x ATR. Require extra confirmation.")

    opt_b = invariants.get("optimal_buy")
    opt_s = invariants.get("optimal_sell")
    if opt_b and opt_b.get("tp1") and opt_b.get("sl"):
        lines.append(
            f"RECOMMENDED BUY EXECUTION : Entry={opt_b.get('entry_price')} | SL={opt_b.get('sl')} | TP={opt_b.get('tp1')} (R:R={opt_b.get('selected_rr')})"
        )
    if opt_s and opt_s.get("tp1") and opt_s.get("sl"):
        lines.append(
            f"RECOMMENDED SELL EXECUTION: Entry={opt_s.get('entry_price')} | SL={opt_s.get('sl')} | TP={opt_s.get('tp1')} (R:R={opt_s.get('selected_rr')})"
        )

    lines.append(
        "MANDATE: Select SL and TP that conform strictly to these pre-computed bounds. Zero manual floating-point math."
    )
    lines.append("=== END INVARIANTS ===")
    return "\n".join(lines)
