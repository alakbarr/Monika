#!/usr/bin/env python3
"""
Monika Specialized Asset & Carry Trade Calculator (asset_special_calc.py)

Zero-dependency Python Standard Library CLI for evaluating asset-specific quantitative metrics:
- Brent-WTI Spread Statistical Arbitrage (Z-Score)
- 3:2:1 Refinery Crack Spread
- FX Carry-to-Risk Ratio (CR)
- Bitcoin ETF & Perpetual Funding Regime
- Gold Real Yield Non-Linearity
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any, Dict, Optional


def evaluate_asset_special(
    asset_type: str,
    # Oil Parameters
    brent_price: Optional[float] = None,
    wti_price: Optional[float] = None,
    mean_spread: float = 4.50,
    std_spread: float = 0.85,
    gasoline_price: Optional[float] = None,
    distillate_price: Optional[float] = None,
    crude_price: Optional[float] = None,
    # Crypto Parameters
    etf_net_inflow_m: Optional[float] = None,
    funding_rate_8h_pct: Optional[float] = None,
    open_interest_chg_pct: Optional[float] = None,
    # Carry Parameters
    long_rate: Optional[float] = None,
    short_rate: Optional[float] = None,
    implied_vol_pct: Optional[float] = None,
    vix: float = 16.0,
    # Gold Parameters
    tips10y: Optional[float] = None,
    dxy: Optional[float] = None,
    shanghai_premium_usd: Optional[float] = None,
) -> Dict[str, Any]:
    asset = asset_type.upper().strip()

    # 1. CRUDE OIL: Brent-WTI Stat-Arb & 3:2:1 Crack Spread
    if asset in ("OIL", "CRUDE", "XTIUSD", "XBRUSD"):
        spread_val: Optional[float] = None
        z_score: Optional[float] = None
        arb_signal = "NEUTRAL_IN_BAND"

        if brent_price is not None and wti_price is not None:
            spread_val = round(brent_price - wti_price, 2)
            z_score = round((spread_val - mean_spread) / max(1e-5, std_spread), 2)
            if z_score >= 2.0:
                arb_signal = "SHORT_BRENT_LONG_WTI (Spread over-extended, expect mean reversion)"
            elif z_score <= -2.0:
                arb_signal = "LONG_BRENT_SHORT_WTI (Spread under-extended, expect widening)"

        crack_spread_321: Optional[float] = None
        if gasoline_price is not None and distillate_price is not None and crude_price is not None:
            # 3:2:1 Crack Spread = ((2 * Gasoline/gal * 42) + (1 * Distillate/gal * 42) - (3 * Crude/bbl)) / 3
            crack_spread_321 = round(
                ((2 * gasoline_price * 42) + (1 * distillate_price * 42) - (3 * crude_price)) / 3, 2
            )

        return {
            "asset_class": "CRUDE_OIL",
            "brent_wti_spread": {
                "brent_price": brent_price,
                "wti_price": wti_price,
                "current_spread": spread_val,
                "historical_mean": mean_spread,
                "historical_std": std_spread,
                "z_score": z_score,
                "statistical_arbitrage_verdict": arb_signal,
            },
            "crack_spread_3_2_1_usd_bbl": crack_spread_321,
        }

    # 2. CRYPTO: BTC Derivatives & ETF Regimes
    elif asset in ("BTC", "BTCUSD", "CRYPTO"):
        etf_stance = "NEUTRAL"
        if etf_net_inflow_m is not None:
            if etf_net_inflow_m > 200.0:
                etf_stance = "HEAVY_INSTITUTIONAL_INFLOW"
            elif etf_net_inflow_m < -150.0:
                etf_stance = "INSTITUTIONAL_OUTFLOW_PRESSURE"

        funding_stance = "NORMAL"
        if funding_rate_8h_pct is not None:
            if funding_rate_8h_pct >= 0.05:
                funding_stance = "OVERHEATED_LONG_LEVERAGE (Squeeze Danger)"
            elif funding_rate_8h_pct <= -0.02:
                funding_stance = "EXTREME_SHORT_SQUEEZE_POTENTIAL"

        return {
            "asset_class": "BITCOIN_CRYPTO",
            "spot_etf_flow_millions": etf_net_inflow_m,
            "etf_flow_regime": etf_stance,
            "perpetual_funding_8h_pct": funding_rate_8h_pct,
            "funding_regime": funding_stance,
            "open_interest_change_pct": open_interest_chg_pct,
        }

    # 3. FX CARRY TRADE: Carry-to-Risk & Unwind Ladder
    elif asset in ("CARRY", "CARRY_TRADE", "FX_CARRY"):
        cr_ratio: Optional[float] = None
        if long_rate is not None and short_rate is not None and implied_vol_pct is not None:
            rate_diff = long_rate - short_rate
            cr_ratio = round(rate_diff / max(1e-5, implied_vol_pct), 3)

        carry_stance = "ATTRACTIVE" if (cr_ratio is not None and cr_ratio >= 0.50) else "UNATTRACTIVE"

        # Carry Unwind Ladder based on VIX
        if vix > 28.0:
            unwind_status = "FULL_EMERGENCY_UNWIND (Close all Long Carry, Reverse to Long JPY/CHF)"
        elif vix > 22.0:
            unwind_status = "DEFENSIVE_HAIRCUT (Cut Carry exposure by 50%)"
        else:
            unwind_status = "SAFE_STABLE_CARRY_ENVIRONMENT"

        return {
            "asset_class": "FX_CARRY_TRADE",
            "rate_differential_pct": (
                round(long_rate - short_rate, 3) if (long_rate is not None and short_rate is not None) else None
            ),
            "implied_volatility_pct": implied_vol_pct,
            "carry_to_risk_ratio_cr": cr_ratio,
            "carry_attractiveness": carry_stance,
            "vix_level": vix,
            "unwind_ladder_protocol": unwind_status,
        }

    # 4. GOLD: XAUUSD Real Yield Non-Linearity
    elif asset in ("GOLD", "XAU", "XAUUSD"):
        regime = "NORMAL_NEGATIVE_CORRELATION"
        if tips10y is not None:
            if tips10y > 2.0:
                regime = "SOVEREIGN_DEBT_STRESS_REGIME (Gold decouples and rises despite high Real Yields)"
            elif tips10y < 1.0:
                regime = "NEGATIVE_REAL_YIELD_TAILWIND (Gold rallies aggressively)"

        return {
            "asset_class": "GOLD_XAUUSD",
            "tips_10y_real_yield": tips10y,
            "dxy_index": dxy,
            "shanghai_gold_premium_usd": shanghai_premium_usd,
            "gold_macro_regime": regime,
        }

    return {"error": f"Unsupported asset class: '{asset_type}'"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika Specialized Asset & Carry Calculator")
    parser.add_argument(
        "--asset",
        type=str,
        required=True,
        help="Asset type or symbol: OIL/CRUDE/XTIUSD, BTC/BTCUSD, CARRY/FX_CARRY, GOLD/XAUUSD",
    )
    parser.add_argument("--brent-price", type=float, default=None)
    parser.add_argument("--wti-price", type=float, default=None)
    parser.add_argument("--mean-spread", type=float, default=4.50)
    parser.add_argument("--std-spread", type=float, default=0.85)
    parser.add_argument("--gasoline-price", type=float, default=None)
    parser.add_argument("--distillate-price", type=float, default=None)
    parser.add_argument("--crude-price", type=float, default=None)
    parser.add_argument("--etf-net-inflow-m", type=float, default=None)
    parser.add_argument("--funding-rate-8h", type=float, default=None)
    parser.add_argument("--open-interest-chg-pct", type=float, default=None)
    parser.add_argument("--long-rate", type=float, default=None)
    parser.add_argument("--short-rate", type=float, default=None)
    parser.add_argument("--implied-vol", type=float, default=None)
    parser.add_argument("--vix", type=float, default=16.0)
    parser.add_argument("--tips10y", type=float, default=None)
    parser.add_argument("--dxy", type=float, default=None)
    parser.add_argument("--shanghai-premium", type=float, default=None)

    args = parser.parse_args()
    out = evaluate_asset_special(
        asset_type=args.asset,
        brent_price=args.brent_price,
        wti_price=args.wti_price,
        mean_spread=args.mean_spread,
        std_spread=args.std_spread,
        gasoline_price=args.gasoline_price,
        distillate_price=args.distillate_price,
        crude_price=args.crude_price,
        etf_net_inflow_m=args.etf_net_inflow_m,
        funding_rate_8h_pct=args.funding_rate_8h,
        open_interest_chg_pct=args.open_interest_chg_pct,
        long_rate=args.long_rate,
        short_rate=args.short_rate,
        implied_vol_pct=args.implied_vol,
        vix=args.vix,
        tips10y=args.tips10y,
        dxy=args.dxy,
        shanghai_premium_usd=args.shanghai_premium,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
