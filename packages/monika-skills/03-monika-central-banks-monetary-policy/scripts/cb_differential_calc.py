#!/usr/bin/env python3
"""
Monika Central Bank Differential & FX Sign Invariant Calculator (cb_differential_calc.py)

Zero-dependency Python Standard Library CLI for evaluating monetary policy divergence,
neutral rate stances (r*), and computing the FX Algebraic Sign Invariant:
Bias(BASE/QUOTE) = Bias(BASE) - Bias(QUOTE)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional

# Central Bank Reference Benchmarks
CB_PROFILES: Dict[str, Dict[str, Any]] = {
    "USD": {"name": "Federal Reserve", "target_inflation": 2.0, "default_r_star": 2.875},
    "EUR": {"name": "European Central Bank", "target_inflation": 2.0, "default_r_star": 2.125},
    "GBP": {"name": "Bank of England", "target_inflation": 2.0, "default_r_star": 3.375},
    "JPY": {"name": "Bank of Japan", "target_inflation": 2.0, "default_r_star": 0.875},
    "AUD": {"name": "Reserve Bank of Australia", "target_inflation": 2.5, "default_r_star": 3.625},
    "CAD": {"name": "Bank of Canada", "target_inflation": 2.0, "default_r_star": 2.75},
    "CHF": {"name": "Swiss National Bank", "target_inflation": 1.0, "default_r_star": 1.00},
}


def compute_cb_differential(
    base_currency: str,
    quote_currency: str,
    base_rate: float,
    quote_rate: float,
    base_r_star: Optional[float] = None,
    quote_r_star: Optional[float] = None,
    base_inflation: Optional[float] = None,
    quote_inflation: Optional[float] = None,
    base_unemp_chg: float = 0.0,
    quote_unemp_chg: float = 0.0,
) -> Dict[str, Any]:
    b_curr = base_currency.strip().upper()
    q_curr = quote_currency.strip().upper()

    b_prof = CB_PROFILES.get(b_curr, {"name": f"CB_{b_curr}", "target_inflation": 2.0, "default_r_star": 2.5})
    q_prof = CB_PROFILES.get(q_curr, {"name": f"CB_{q_curr}", "target_inflation": 2.0, "default_r_star": 2.5})

    r_star_b = base_r_star if base_r_star is not None else b_prof["default_r_star"]
    r_star_q = quote_r_star if quote_r_star is not None else q_prof["default_r_star"]

    inf_b = base_inflation if base_inflation is not None else b_prof["target_inflation"]
    inf_q = quote_inflation if quote_inflation is not None else q_prof["target_inflation"]

    # Stance relative to neutral rate
    stance_b = base_rate - r_star_b
    stance_q = quote_rate - r_star_q

    # Inflation gap from target
    inf_gap_b = inf_b - b_prof["target_inflation"]
    inf_gap_q = inf_q - q_prof["target_inflation"]

    # Hawkishness Score (-10 to +10)
    score_b = max(-10.0, min(10.0, (stance_b * 1.5) + (inf_gap_b * 1.2) - (base_unemp_chg * 3.0)))
    score_q = max(-10.0, min(10.0, (stance_q * 1.5) + (inf_gap_q * 1.2) - (quote_unemp_chg * 3.0)))

    # Net Pair Bias (Algebraic Sign Invariant)
    net_bias = round(score_b - score_q, 2)

    if net_bias >= 2.5:
        bias_verdict = "BULLISH"
    elif net_bias <= -2.5:
        bias_verdict = "BEARISH"
    else:
        bias_verdict = "NEUTRAL"

    return {
        "pair": f"{b_curr}{q_curr}",
        "base": {
            "currency": b_curr,
            "central_bank": b_prof["name"],
            "policy_rate": base_rate,
            "neutral_r_star": r_star_b,
            "policy_stance": round(stance_b, 2),
            "inflation": inf_b,
            "macro_score": round(score_b, 2),
        },
        "quote": {
            "currency": q_curr,
            "central_bank": q_prof["name"],
            "policy_rate": quote_rate,
            "neutral_r_star": r_star_q,
            "policy_stance": round(stance_q, 2),
            "inflation": inf_q,
            "macro_score": round(score_q, 2),
        },
        "nominal_rate_differential_bps": round((base_rate - quote_rate) * 100, 1),
        "net_pair_bias_score": net_bias,
        "structural_macro_bias": bias_verdict,
        "algebraic_sign_invariant_formula": f"Bias({b_curr}/{q_curr}) = Bias({b_curr}) [{score_b:+.1f}] - Bias({q_curr}) [{score_q:+.1f}] = {net_bias:+.1f}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monika Central Bank Differential Calculator")
    parser.add_argument("--base-currency", type=str, required=True)
    parser.add_argument("--quote-currency", type=str, required=True)
    parser.add_argument("--base-rate", type=float, required=True)
    parser.add_argument("--quote-rate", type=float, required=True)
    parser.add_argument("--base-r-star", type=float, default=None)
    parser.add_argument("--quote-r-star", type=float, default=None)
    parser.add_argument("--base-inflation", type=float, default=None)
    parser.add_argument("--quote-inflation", type=float, default=None)
    parser.add_argument("--base-unemp-chg", type=float, default=0.0)
    parser.add_argument("--quote-unemp-chg", type=float, default=0.0)

    args = parser.parse_args()
    out = compute_cb_differential(
        base_currency=args.base_currency,
        quote_currency=args.quote_currency,
        base_rate=args.base_rate,
        quote_rate=args.quote_rate,
        base_r_star=args.base_r_star,
        quote_r_star=args.quote_r_star,
        base_inflation=args.base_inflation,
        quote_inflation=args.quote_inflation,
        base_unemp_chg=args.base_unemp_chg,
        quote_unemp_chg=args.quote_unemp_chg,
    )
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
