#!/usr/bin/env python3
"""
Monika Macro Liquidity Plumbing & Yield Curve Calculator (macro_liquidity_calc.py)

Zero-dependency Python Standard Library CLI for evaluating US Net Systemic Liquidity
(WALCL - TGA - RRP), 4-Quadrant Yield Curve regimes, and VIX/Credit stress gates.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional


def evaluate_macro_plumbing(
    walcl_billions: Optional[float] = None,
    tga_billions: Optional[float] = None,
    rrp_billions: Optional[float] = None,
    prev_net_liq_billions: Optional[float] = None,
    us10y: Optional[float] = None,
    us2y: Optional[float] = None,
    tips10y: Optional[float] = None,
    vix: float = 16.0,
    hy_oas_bps: float = 340.0,
) -> Dict[str, Any]:
    # 1. Systemic Liquidity
    net_liq: Optional[float] = None
    net_liq_delta: Optional[float] = None
    liq_status = "NEUTRAL"

    if walcl_billions is not None and tga_billions is not None and rrp_billions is not None:
        net_liq = round(walcl_billions - tga_billions - rrp_billions, 2)
        if prev_net_liq_billions is not None:
            net_liq_delta = round(net_liq - prev_net_liq_billions, 2)
            if net_liq_delta > 25.0:
                liq_status = "EXPANDING (Bullish Risk Assets)"
            elif net_liq_delta < -25.0:
                liq_status = "CONTRACTING (Bearish Risk Assets)"

    # 2. Yield Curve 4-Quadrant Classification
    curve_regime = "UNKNOWN"
    slope_2s10s: Optional[float] = None
    breakeven_10y: Optional[float] = None

    if us10y is not None and us2y is not None:
        slope_2s10s = round(us10y - us2y, 3)
        if slope_2s10s > 0:
            curve_regime = "STEEPENER_NORMAL"
        else:
            curve_regime = "INVERTED_FLATTENER"

    if us10y is not None and tips10y is not None:
        breakeven_10y = round(us10y - tips10y, 3)

    # 3. VIX Volatility Regime & Multiplier
    vix_val = float(vix)
    if vix_val < 15.0:
        vix_regime = "RISK_ON"
        vix_mult = 1.00
    elif vix_val <= 20.0:
        vix_regime = "CARRY_RANGE"
        vix_mult = 1.00
    elif vix_val <= 25.0:
        vix_regime = "CAUTION"
        vix_mult = 0.75
    elif vix_val <= 30.0:
        vix_regime = "STRESS"
        vix_mult = 0.50
    else:
        vix_regime = "CRISIS"
        vix_mult = 0.25

    # 4. Credit Spread (HY OAS) Gate
    credit_veto = hy_oas_bps >= 450.0

    return {
        "systemic_liquidity": {
            "walcl_fed_assets_b": walcl_billions,
            "tga_treasury_cash_b": tga_billions,
            "on_rrp_reverse_repo_b": rrp_billions,
            "net_liquidity_billions": net_liq,
            "net_liquidity_delta_billions": net_liq_delta,
            "stance": liq_status,
        },
        "yield_curve": {
            "us10y": us10y,
            "us2y": us2y,
            "slope_2s10s_bps": round(slope_2s10s * 100, 1) if slope_2s10s is not None else None,
            "tips_10y_real_yield": tips10y,
            "breakeven_inflation_10y": breakeven_10y,
            "curve_regime": curve_regime,
        },
        "risk_environment": {
            "vix": vix_val,
            "vix_regime": vix_regime,
            "vix_position_multiplier": vix_mult,
            "hy_oas_spread_bps": hy_oas_bps,
            "credit_stress_hard_veto": credit_veto,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika Macro Liquidity & Yield Curve Calculator")
    parser.add_argument("--walcl", type=float, default=None)
    parser.add_argument("--tga", type=float, default=None)
    parser.add_argument("--rrp", type=float, default=None)
    parser.add_argument("--prev-net-liq", type=float, default=None)
    parser.add_argument("--us10y", type=float, default=None)
    parser.add_argument("--us2y", type=float, default=None)
    parser.add_argument("--tips10y", type=float, default=None)
    parser.add_argument("--vix", type=float, default=16.0)
    parser.add_argument("--hy-oas", type=float, default=340.0)

    args = parser.parse_args()
    out = evaluate_macro_plumbing(
        walcl_billions=args.walcl,
        tga_billions=args.tga,
        rrp_billions=args.rrp,
        prev_net_liq_billions=args.prev_net_liq,
        us10y=args.us10y,
        us2y=args.us2y,
        tips10y=args.tips10y,
        vix=args.vix,
        hy_oas_bps=args.hy_oas,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
