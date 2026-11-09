#!/usr/bin/env python3
"""
Monika Institutional Quantitative Invariant & Risk Engine (monika_quant_engine.py)

Zero-dependency, Python Standard Library-only CLI engine for algorithmic trading
invariants, pre-computed brackets, fixed-fractional Decimal position sizing,
and 12-point RiskGate pre-execution auditing.

Replicates the deterministic mathematical fortress of Monika in standalone AI Agent skills.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, UTC
from decimal import Decimal, ROUND_FLOOR, InvalidOperation
import json
import math
import sys
from typing import Any, Dict, List, Optional, Tuple

# ==============================================================================
# 1. ASSET SPECIFICATIONS & INSTRUMENT DICTIONARY
# ==============================================================================

DEFAULT_INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "EURUSD": {
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "099741",
    },
    "GBPUSD": {
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "096742",
    },
    "USDJPY": {
        "pip_size": 0.01,
        "pip_value_usd": 6.67,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 3,
        "cot_code": "097741",
    },
    "AUDUSD": {
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "232741",
    },
    "USDCAD": {
        "pip_size": 0.0001,
        "pip_value_usd": 7.41,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "090741",
    },
    "USDCHF": {
        "pip_size": 0.0001,
        "pip_value_usd": 11.10,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "092741",
    },
    "XAUUSD": {
        "pip_size": 0.01,
        "pip_value_usd": 1.0,
        "contract_size": 100,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 2,
        "cot_code": "088691",
    },
    "XTIUSD": {
        "pip_size": 0.01,
        "pip_value_usd": 10.0,
        "contract_size": 1000,
        "min_lot": 0.01,
        "max_lot": 50.0,
        "lot_step": 0.01,
        "digits": 2,
        "cot_code": "067651",
    },
    "XBRUSD": {
        "pip_size": 0.01,
        "pip_value_usd": 10.0,
        "contract_size": 1000,
        "min_lot": 0.01,
        "max_lot": 50.0,
        "lot_step": 0.01,
        "digits": 2,
        "cot_code": "06765T",
    },
    "BTCUSD": {
        "pip_size": 1.0,
        "pip_value_usd": 1.0,
        "contract_size": 1,
        "min_lot": 0.01,
        "max_lot": 10.0,
        "lot_step": 0.01,
        "digits": 1,
        "cot_code": "133741",
    },
}


def get_asset_spec(symbol: str) -> Dict[str, Any]:
    sym = (symbol or "").strip().upper()
    if sym in DEFAULT_INSTRUMENTS:
        return DEFAULT_INSTRUMENTS[sym]
    if any(k in sym for k in ("JPY", "XAG", "XTI", "XBR", "BRENT", "WTI")):
        digits = 3 if "JPY" in sym else 2
        return {
            "pip_size": 0.01,
            "pip_value_usd": 10.0 if ("XTI" in sym or "XBR" in sym) else 6.67,
            "contract_size": 1000 if ("XTI" in sym or "XBR" in sym) else 100000,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "digits": digits,
            "cot_code": "UNKNOWN",
        }
    if any(k in sym for k in ("XAU", "GOLD", "ETH")):
        return {
            "pip_size": 0.01,
            "pip_value_usd": 1.0,
            "contract_size": 100,
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "digits": 2,
            "cot_code": "088691",
        }
    if "BTC" in sym:
        return {
            "pip_size": 1.0,
            "pip_value_usd": 1.0,
            "contract_size": 1,
            "min_lot": 0.01,
            "max_lot": 10.0,
            "lot_step": 0.01,
            "digits": 1,
            "cot_code": "133741",
        }
    return {
        "pip_size": 0.0001,
        "pip_value_usd": 10.0,
        "contract_size": 100000,
        "min_lot": 0.01,
        "max_lot": 100.0,
        "lot_step": 0.01,
        "digits": 5,
        "cot_code": "UNKNOWN",
    }


def extract_price_precision(symbol: str) -> int:
    return int(get_asset_spec(symbol)["digits"])


# ==============================================================================
# DETERMINISTIC BRACKET GENERATOR
# ==============================================================================


def generate_brackets(
    symbol: str,
    price: float,
    atr14: float,
    adr5d: Optional[float] = None,
    demand_level: Optional[float] = None,
    supply_level: Optional[float] = None,
    target_rr: float = 1.80,
    regime: Optional[str] = None,
    impulse_atr: Optional[float] = None,
) -> Dict[str, Any]:
    prec = extract_price_precision(symbol)
    curr_px = float(price)
    atr_val = float(atr14) if atr14 > 0 else curr_px * 0.005
    adr_val = float(adr5d) if adr5d and adr5d > 0 else atr_val * 2.0
    min_rr = max(1.50, float(target_rr))

    sym_clean = symbol.upper()
    is_high_vol = any(k in sym_clean for k in ("BTC", "ETH", "SOL", "XAU", "XAG", "XTI", "XBR", "BRENT", "WTI"))
    noise_floor_mult = 1.35 if is_high_vol else 1.25
    target_noise_dist = noise_floor_mult * atr_val

    max_sl_dist = min(2.5 * atr_val, max(target_noise_dist, 0.35 * adr_val))

    # 1. Long Option A
    long_entry = round(
        demand_level if demand_level and (curr_px - 0.75 * atr_val) <= demand_level <= curr_px else curr_px, prec
    )
    long_sl_dist = min(max_sl_dist, max(target_noise_dist, 0.35 * adr_val))
    long_sl = round(long_entry - long_sl_dist, prec)
    long_risk = abs(long_entry - long_sl)
    if long_risk <= 0.0:
        long_risk = round(target_noise_dist, prec)
        long_sl = round(long_entry - long_risk, prec)

    long_tp_dist = round(long_risk * min_rr, prec)
    long_tp = round(long_entry + long_tp_dist, prec)
    actual_long_rr = round(long_tp_dist / long_risk, 2)

    # 2. Short Option B
    short_entry = round(
        supply_level if supply_level and curr_px <= supply_level <= (curr_px + 0.75 * atr_val) else curr_px, prec
    )
    short_sl_dist = min(max_sl_dist, max(target_noise_dist, 0.35 * adr_val))
    short_sl = round(short_entry + short_sl_dist, prec)
    short_risk = abs(short_sl - short_entry)
    if short_risk <= 0.0:
        short_risk = round(target_noise_dist, prec)
        short_sl = round(short_entry + short_risk, prec)

    short_tp_dist = round(short_risk * min_rr, prec)
    short_tp = round(short_entry - short_tp_dist, prec)
    actual_short_rr = round(short_tp_dist / short_risk, 2)

    return {
        "symbol": sym_clean,
        "current_price": curr_px,
        "precision": prec,
        "atr_14": round(atr_val, prec),
        "adr_5d": round(adr_val, prec),
        "noise_floor_atr": noise_floor_mult,
        "long_option_a": {
            "name": "LONG_OPTION_A",
            "direction": "buy",
            "entry": long_entry,
            "stop_loss": long_sl,
            "take_profit": long_tp,
            "risk_distance": round(long_risk, prec),
            "rr_ratio": actual_long_rr,
            "sl_distance_atr": round(long_risk / atr_val, 2),
        },
        "short_option_b": {
            "name": "SHORT_OPTION_B",
            "direction": "sell",
            "entry": short_entry,
            "stop_loss": short_sl,
            "take_profit": short_tp,
            "risk_distance": round(short_risk, prec),
            "rr_ratio": actual_short_rr,
            "sl_distance_atr": round(short_risk / atr_val, 2),
        },
    }


# ==============================================================================
# FIXED-FRACTIONAL DECIMAL POSITION SIZING
# ==============================================================================


def calculate_position_size(
    equity: float,
    base_risk_pct: float,
    entry: float,
    sl: float,
    symbol: str = "EURUSD",
    vix_mult: float = 1.0,
    judge_mult: float = 1.0,
    ttl_mult: float = 1.0,
    synergy_mult: float = 1.0,
) -> Dict[str, Any]:
    spec = get_asset_spec(symbol)
    min_lot = Decimal(str(spec["min_lot"]))
    max_lot = Decimal(str(spec["max_lot"]))
    lot_step = Decimal(str(spec["lot_step"]))
    pip_size = Decimal(str(spec["pip_size"]))
    pip_val_usd = Decimal(str(spec["pip_value_usd"]))

    d_equity = Decimal(str(equity))
    d_base_risk = Decimal(str(base_risk_pct))
    d_vix = Decimal(str(vix_mult))
    d_judge = Decimal(str(judge_mult))
    d_ttl = Decimal(str(ttl_mult))
    d_synergy = Decimal(str(synergy_mult))

    eff_risk_pct = min(Decimal("2.0"), d_base_risk * d_vix * d_judge * d_ttl * d_synergy)
    dollar_risk_budget = (d_equity * eff_risk_pct) / Decimal("100")

    d_entry = Decimal(str(entry))
    d_sl = Decimal(str(sl))
    sl_distance = abs(d_entry - d_sl)

    if sl_distance <= Decimal("0") or dollar_risk_budget <= Decimal("0"):
        return {
            "symbol": symbol.upper(),
            "recommended_lots": 0.0,
            "effective_risk_pct": float(eff_risk_pct),
            "dollar_risk_budget": float(dollar_risk_budget),
            "actual_dollar_risk": 0.0,
            "is_valid": False,
            "rejection_reason": "Zero or negative stop distance / risk budget",
        }

    sl_pips = sl_distance / pip_size
    raw_lots = dollar_risk_budget / (sl_pips * pip_val_usd)

    steps = (raw_lots / lot_step).quantize(Decimal("1"), rounding=ROUND_FLOOR)
    floored_lots = steps * lot_step

    if floored_lots < min_lot:
        is_valid = False
        rejection = f"Calculated lots ({floored_lots}) < minimum allowed ({min_lot})"
        final_lots = Decimal("0.0")
    elif floored_lots > max_lot:
        final_lots = max_lot
        is_valid = True
        rejection = ""
    else:
        final_lots = floored_lots
        is_valid = True
        rejection = ""

    actual_dollar_risk = float((final_lots * sl_pips * pip_val_usd).quantize(Decimal("0.01"), rounding=ROUND_FLOOR))

    return {
        "symbol": symbol.upper(),
        "recommended_lots": float(final_lots),
        "raw_lots": float(raw_lots),
        "effective_risk_pct": float(eff_risk_pct),
        "dollar_risk_budget": float(dollar_risk_budget),
        "actual_dollar_risk": actual_dollar_risk,
        "is_valid": is_valid,
        "rejection_reason": rejection,
    }


# ==============================================================================
# 12-POINT RISKGATE PRE-EXECUTION AUDIT
# ==============================================================================


def audit_risk_gate(
    symbol: str,
    direction: str,
    entry: float,
    sl: float,
    tp: float,
    atr14: float,
    adr5d: float,
    pos: float,
    equity: float,
    daily_drawdown_pct: float = 0.0,
    vix: float = 16.0,
    spread_ratio: float = 1.0,
    now_utc_str: Optional[str] = None,
    event_delta_mins: Optional[float] = None,
    hy_oas_bps: float = 340.0,
    stale_data: bool = False,
) -> Dict[str, Any]:
    checks_passed: List[str] = []
    checks_failed: List[str] = []
    reasons: List[str] = []

    dir_clean = direction.strip().lower()
    sym_clean = symbol.strip().upper()

    vals = [entry, sl, tp, atr14, adr5d, pos, equity]
    if any(not math.isfinite(v) or v <= 0.0 for v in vals if v is not pos):
        checks_failed.append("valid_finite_inputs")
        reasons.append("Inputs contain NaN, infinite, or non-positive values")
    else:
        checks_passed.append("valid_finite_inputs")

    if dir_clean in ("buy", "long"):
        if sl < entry < tp:
            checks_passed.append("directional_bracket_ordering")
        else:
            checks_failed.append("directional_bracket_ordering")
            reasons.append(f"Inverted BUY bracket: require SL ({sl}) < Entry ({entry}) < TP ({tp})")
    elif dir_clean in ("sell", "short"):
        if tp < entry < sl:
            checks_passed.append("directional_bracket_ordering")
        else:
            checks_failed.append("directional_bracket_ordering")
            reasons.append(f"Inverted SELL bracket: require TP ({tp}) < Entry ({entry}) < SL ({sl})")
    else:
        checks_failed.append("directional_bracket_ordering")
        reasons.append(f"Invalid direction: '{direction}'")

    is_high_vol = any(k in sym_clean for k in ("BTC", "ETH", "SOL", "XAU", "XAG", "XTI", "XBR", "BRENT", "WTI"))
    min_noise_mult = 1.35 if is_high_vol else 1.25
    sl_dist = abs(entry - sl)
    if sl_dist >= (min_noise_mult * atr14 * 0.98):
        checks_passed.append("noise_floor_protection")
    else:
        checks_failed.append("noise_floor_protection")
        reasons.append(
            f"SL distance ({sl_dist:.5f}) below {min_noise_mult:.2f}x ATR noise floor ({min_noise_mult * atr14:.5f})"
        )

    if sl_dist <= (3.0 * atr14) and sl_dist <= adr5d:
        checks_passed.append("max_stop_cap")
    else:
        checks_failed.append("max_stop_cap")
        reasons.append(f"SL distance ({sl_dist:.5f}) exceeds max cap (3.0x ATR or 1.0x ADR)")

    tp_dist = abs(tp - entry)
    rr_ratio = tp_dist / max(1e-7, sl_dist)
    if rr_ratio >= 1.48:
        checks_passed.append("minimum_rr_ratio")
    else:
        checks_failed.append("minimum_rr_ratio")
        reasons.append(f"R:R ratio ({rr_ratio:.2f}) < 1.50 minimum institutional threshold")

    if dir_clean in ("buy", "long") and pos > 0.85:
        checks_failed.append("spatial_dealing_range_anti_chasing")
        reasons.append(f"Anti-chasing violation: BUY blocked at extreme premium dealing range (pos={pos:.2f} > 0.85)")
    elif dir_clean in ("sell", "short") and pos < 0.15:
        checks_failed.append("spatial_dealing_range_anti_chasing")
        reasons.append(f"Anti-chasing violation: SELL blocked at extreme discount dealing range (pos={pos:.2f} < 0.15)")
    else:
        checks_passed.append("spatial_dealing_range_anti_chasing")

    if daily_drawdown_pct >= 3.0:
        checks_failed.append("daily_drawdown_limit")
        reasons.append(f"Daily drawdown limit breached ({daily_drawdown_pct:.2f}% >= 3.00%)")
    else:
        checks_passed.append("daily_drawdown_limit")

    if spread_ratio > 2.0:
        checks_failed.append("spread_spike_gate")
        reasons.append(f"Spread expansion spike ({spread_ratio:.2f}x > 2.0x typical spread)")
    else:
        checks_passed.append("spread_spike_gate")

    now = datetime.fromisoformat(now_utc_str.replace("Z", "+00:00")) if now_utc_str else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    minute_of_day = now.hour * 60 + now.minute
    if 1315 <= minute_of_day <= 1335:
        checks_failed.append("rollover_blackout_window")
        reasons.append(f"Daily rollover blackout active at {now.strftime('%H:%M UTC')} (21:55 - 22:15 UTC)")
    else:
        checks_passed.append("rollover_blackout_window")

    if event_delta_mins is not None and -15.0 <= event_delta_mins <= 30.0:
        checks_failed.append("event_blackout_window")
        reasons.append(f"High-impact news event window active (~{event_delta_mins:.0f}m away)")
    else:
        checks_passed.append("event_blackout_window")

    if vix > 30.0 or hy_oas_bps >= 450.0:
        checks_failed.append("systemic_crisis_gate")
        reasons.append(f"Systemic crisis gate active (VIX={vix:.1f}, HY OAS={hy_oas_bps:.0f} bps)")
    else:
        checks_passed.append("systemic_crisis_gate")

    if stale_data:
        checks_passed.append("stale_data_scaled")
    else:
        checks_passed.append("stale_data_verified")

    approved = len(checks_failed) == 0

    return {
        "verdict": "APPROVED" if approved else "REJECTED",
        "approved": approved,
        "symbol": sym_clean,
        "direction": dir_clean.upper(),
        "total_checks": 12,
        "passed_count": len(checks_passed),
        "failed_count": len(checks_failed),
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "rejection_reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika Deterministic Risk Engine CLI")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # 1. brackets
    p_brk = subparsers.add_parser("brackets")
    p_brk.add_argument("--symbol", type=str, required=True)
    p_brk.add_argument("--price", type=float, required=True)
    p_brk.add_argument("--atr14", type=float, required=True)
    p_brk.add_argument("--adr5d", type=float, default=None)
    p_brk.add_argument("--demand-level", type=float, default=None)
    p_brk.add_argument("--supply-level", type=float, default=None)
    p_brk.add_argument("--target-rr", type=float, default=1.80)

    # 2. size
    p_sz = subparsers.add_parser("size")
    p_sz.add_argument("--equity", type=float, required=True)
    p_sz.add_argument("--base-risk-pct", type=float, required=True)
    p_sz.add_argument("--entry", type=float, required=True)
    p_sz.add_argument("--sl", type=float, required=True)
    p_sz.add_argument("--symbol", type=str, default="EURUSD")
    p_sz.add_argument("--vix-mult", type=float, default=1.0)
    p_sz.add_argument("--judge-mult", type=float, default=1.0)
    p_sz.add_argument("--ttl-mult", type=float, default=1.0)
    p_sz.add_argument("--synergy-mult", type=float, default=1.0)

    # 3. risk-gate
    p_rg = subparsers.add_parser("risk-gate")
    p_rg.add_argument("--symbol", type=str, required=True)
    p_rg.add_argument("--direction", type=str, required=True)
    p_rg.add_argument("--entry", type=float, required=True)
    p_rg.add_argument("--sl", type=float, required=True)
    p_rg.add_argument("--tp", type=float, required=True)
    p_rg.add_argument("--atr14", type=float, required=True)
    p_rg.add_argument("--adr5d", type=float, required=True)
    p_rg.add_argument("--pos", type=float, required=True)
    p_rg.add_argument("--equity", type=float, required=True)
    p_rg.add_argument("--daily-drawdown-pct", type=float, default=0.0)
    p_rg.add_argument("--vix", type=float, default=16.0)
    p_rg.add_argument("--spread-ratio", type=float, default=1.0)
    p_rg.add_argument("--now-utc", type=str, default=None)
    p_rg.add_argument("--event-delta-mins", type=float, default=None)
    p_rg.add_argument("--hy-oas", type=float, default=340.0)
    p_rg.add_argument("--stale-data", action="store_true")

    args = parser.parse_args()

    if args.subcommand == "brackets":
        out = generate_brackets(
            symbol=args.symbol,
            price=args.price,
            atr14=args.atr14,
            adr5d=args.adr5d,
            demand_level=args.demand_level,
            supply_level=args.supply_level,
            target_rr=args.target_rr,
        )
    elif args.subcommand == "size":
        out = calculate_position_size(
            equity=args.equity,
            base_risk_pct=args.base_risk_pct,
            entry=args.entry,
            sl=args.sl,
            symbol=args.symbol,
            vix_mult=args.vix_mult,
            judge_mult=args.judge_mult,
            ttl_mult=args.ttl_mult,
            synergy_mult=args.synergy_mult,
        )
    elif args.subcommand == "risk-gate":
        out = audit_risk_gate(
            symbol=args.symbol,
            direction=args.direction,
            entry=args.entry,
            sl=args.sl,
            tp=args.tp,
            atr14=args.atr14,
            adr5d=args.adr5d,
            pos=args.pos,
            equity=args.equity,
            daily_drawdown_pct=args.daily_drawdown_pct,
            vix=args.vix,
            spread_ratio=args.spread_ratio,
            now_utc_str=args.now_utc,
            event_delta_mins=args.event_delta_mins,
            hy_oas_bps=args.hy_oas,
            stale_data=args.stale_data,
        )

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
