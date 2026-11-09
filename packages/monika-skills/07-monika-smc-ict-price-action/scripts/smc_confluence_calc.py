#!/usr/bin/env python3
"""
Monika SMC/ICT Dealing Range & 20-Point Confluence Calculator (smc_confluence_calc.py)

Zero-dependency Python Standard Library CLI for evaluating 3-Zone Spatial Dealing Range (pos),
Anti-Chasing restrictions, and scoring trade setups against Monika's 20-Point Confluence Scorecard.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional


def evaluate_smc_setup(
    close: float,
    high20: float,
    low20: float,
    atr14: float,
    pdl: Optional[float] = None,
    pdh: Optional[float] = None,
    confluence_score: int = 12,
    has_active_impulse: bool = False,
    regime_type: str = "regime_a_trend",
) -> Dict[str, Any]:
    hi = max(float(high20), float(low20))
    lo = min(float(high20), float(low20))
    rng = hi - lo
    pos = 0.50 if rng <= 0.0 else (close - lo) / rng
    pos = round(max(0.0, min(1.0, pos)), 4)
    safe_atr = max(1e-7, float(atr14))

    is_discount = pos <= 0.35 or (pdl is not None and (close - pdl) <= 0.50 * safe_atr and pos <= 0.40)
    is_premium = pos >= 0.65 or (pdh is not None and (pdh - close) <= 0.50 * safe_atr and pos >= 0.60)
    is_equilibrium = not is_discount and not is_premium

    anti_chasing_buy = pos > 0.85
    anti_chasing_sell = pos < 0.15

    if is_discount:
        zone = "DISCOUNT_ZONE"
        allowed_dir = "BUY" if not anti_chasing_buy else "HOLD"
    elif is_premium:
        zone = "PREMIUM_ZONE"
        allowed_dir = "SELL" if not anti_chasing_sell else "HOLD"
    else:
        zone = "EQUILIBRIUM_CHOP"
        allowed_dir = "BUY_OR_SELL_IMPULSE" if has_active_impulse else "HOLD"

    # Confluence Thresholds
    if confluence_score >= 13:
        conf_tier = "FULL_CONFLUENCE"
        conf_mult = 1.00
    elif confluence_score >= 11:
        conf_tier = "STRONG_CONFLUENCE"
        conf_mult = 0.75
    elif confluence_score >= 10:
        conf_tier = "MODERATE_CONFLUENCE"
        conf_mult = 0.50
    else:
        conf_tier = "SUB_THRESHOLD_REJECT"
        conf_mult = 0.00

    return {
        "spatial_dealing_range": {
            "close": close,
            "high_20": high20,
            "low_20": low20,
            "dealing_range_pos": pos,
            "classified_zone": zone,
            "is_discount": is_discount,
            "is_premium": is_premium,
            "is_equilibrium": is_equilibrium,
            "permitted_direction": allowed_dir,
            "anti_chasing_buy_block": anti_chasing_buy,
            "anti_chasing_sell_block": anti_chasing_sell,
        },
        "confluence_scorecard": {
            "raw_score": confluence_score,
            "max_possible_core": 14,
            "max_possible_total": 20,
            "confluence_tier": conf_tier,
            "confluence_multiplier": conf_mult,
            "meets_execution_minimum": confluence_score >= 10,
        },
        "engine_recommendation": (
            "ENGINE_1_TREND_CONTINUATION (Enter at unmitigated OB/FVG in Discount/Premium)"
            if "trend" in regime_type.lower() and not is_equilibrium
            else "ENGINE_2_TURTLE_SOUP_SWEEP (Wait for liquidity sweep of PDH/PDL + MSS M15)"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika SMC Dealing Range & Confluence Calculator")
    parser.add_argument("--close", type=float, required=True)
    parser.add_argument("--high20", type=float, required=True)
    parser.add_argument("--low20", type=float, required=True)
    parser.add_argument("--atr14", type=float, required=True)
    parser.add_argument("--pdl", type=float, default=None)
    parser.add_argument("--pdh", type=float, default=None)
    parser.add_argument("--confluence-score", type=int, default=12)
    parser.add_argument("--has-active-impulse", action="store_true")
    parser.add_argument("--regime-type", type=str, default="regime_a_trend")

    args = parser.parse_args()
    out = evaluate_smc_setup(
        close=args.close,
        high20=args.high20,
        low20=args.low20,
        atr14=args.atr14,
        pdl=args.pdl,
        pdh=args.pdh,
        confluence_score=args.confluence_score,
        has_active_impulse=args.has_active_impulse,
        regime_type=args.regime_type,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
