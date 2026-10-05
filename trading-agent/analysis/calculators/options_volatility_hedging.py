# ==============================================================================
# File: analysis/calculators/options_volatility_hedging.py
# ==============================================================================

"""
Options Implied Volatility Surface & Spot Delta-Hedging Calculator (Async & Sync).
Implements Garman-Kohlhagen FX option pricing, full analytical Greeks
(Delta, Gamma, Vega, Theta), IV surface interpolation from RR/BF quotes,
and spot delta-neutral portfolio rebalancing recommendations (Q141).
"""

import math
import logging
from typing import Any, Dict, List, Optional, Tuple

import utils.clock as clock

logger = logging.getLogger("TradingAgent.OptionsVolatilityHedging")


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


class OptionsVolatilityHedgingEngine:
    """
    Institutional Options & Volatility Hedging Desk Engine.
    Provides research-grade pricing, Greeks, and spot hedging without requiring direct option broker execution.
    """

    def calculate_greeks(
        self,
        spot: float,
        strike: float,
        time_to_maturity_years: float,
        volatility: float,
        domestic_rate: float = 0.05,
        foreign_rate: float = 0.035,
        option_type: str = "CALL",
    ) -> Dict[str, float]:
        """
        Garman-Kohlhagen analytical pricing and Greeks for FX/Equity options.
        """
        S = max(1e-5, spot)
        K = max(1e-5, strike)
        T = max(1e-4, time_to_maturity_years)
        sigma = max(1e-4, volatility)
        r_d = domestic_rate
        r_f = foreign_rate
        is_call = option_type.upper().startswith("C")

        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r_d - r_f + 0.5 * sigma * sigma) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        exp_rf = math.exp(-r_f * T)
        exp_rd = math.exp(-r_d * T)

        # Premium
        if is_call:
            price = S * exp_rf * _norm_cdf(d1) - K * exp_rd * _norm_cdf(d2)
            delta = exp_rf * _norm_cdf(d1)
            theta_annual = (
                -(S * exp_rf * _norm_pdf(d1) * sigma) / (2.0 * sqrt_T)
                + r_f * S * exp_rf * _norm_cdf(d1)
                - r_d * K * exp_rd * _norm_cdf(d2)
            )
            rho_d = K * T * exp_rd * _norm_cdf(d2) * 0.01
        else:
            price = K * exp_rd * _norm_cdf(-d2) - S * exp_rf * _norm_cdf(-d1)
            delta = -exp_rf * _norm_cdf(-d1)
            theta_annual = (
                -(S * exp_rf * _norm_pdf(d1) * sigma) / (2.0 * sqrt_T)
                - r_f * S * exp_rf * _norm_cdf(-d1)
                + r_d * K * exp_rd * _norm_cdf(-d2)
            )
            rho_d = -K * T * exp_rd * _norm_cdf(-d2) * 0.01

        gamma = (exp_rf * _norm_pdf(d1)) / (S * sigma * sqrt_T)
        vega_1pct = (S * exp_rf * sqrt_T * _norm_pdf(d1)) * 0.01  # Per 1% (0.01) vol change
        theta_daily = theta_annual / 365.0

        return {
            "price": round(price, 5),
            "delta": round(delta, 4),
            "gamma": round(gamma, 6),
            "vega_per_1pct": round(vega_1pct, 4),
            "theta_daily": round(theta_daily, 5),
            "rho_d": round(rho_d, 4),
            "d1": round(d1, 4),
            "d2": round(d2, 4),
        }

    def construct_iv_surface(
        self,
        spot: float,
        atm_vol: float,
        risk_reversal_25d: float,
        butterfly_25d: float,
        tenor_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Constructs a 3-point FX implied volatility smile:
        25D Put Vol, ATM Vol, 25D Call Vol.
        Formula:
          Vol(25D Call) = ATM + BF_25 + 0.5 * RR_25
          Vol(25D Put)  = ATM + BF_25 - 0.5 * RR_25
        """
        T = tenor_days / 365.0
        sigma_atm = atm_vol
        rr = risk_reversal_25d
        bf = butterfly_25d

        vol_call_25d = sigma_atm + bf + 0.5 * rr
        vol_put_25d = sigma_atm + bf - 0.5 * rr

        # Approximate strikes
        # Strike for 25D Call: approx S * exp(0.674 * sigma_atm * sqrt(T))
        strike_call = round(spot * math.exp(0.674 * sigma_atm * math.sqrt(T)), 4)
        strike_put = round(spot * math.exp(-0.674 * sigma_atm * math.sqrt(T)), 4)

        skew_sentiment = "BULLISH_SKEW" if rr > 0 else ("BEARISH_SKEW" if rr < 0 else "SYMMETRIC")

        return {
            "spot": spot,
            "tenor_days": tenor_days,
            "atm_vol_pct": round(sigma_atm * 100.0, 2),
            "surface_points": [
                {"delta": "25D_PUT", "strike": strike_put, "iv_pct": round(vol_put_25d * 100.0, 2)},
                {"delta": "50D_ATM", "strike": round(spot, 4), "iv_pct": round(sigma_atm * 100.0, 2)},
                {"delta": "25D_CALL", "strike": strike_call, "iv_pct": round(vol_call_25d * 100.0, 2)},
            ],
            "skew_metrics": {
                "risk_reversal_25d": round(rr * 100.0, 2),
                "butterfly_25d": round(bf * 100.0, 2),
                "market_sentiment": skew_sentiment,
            },
        }

    def compute_spot_delta_hedge(
        self,
        positions: List[Dict[str, Any]],
        spot_price: float,
        contract_size: float = 100000.0,
    ) -> Dict[str, Any]:
        """
        Given a list of option positions, calculates total portfolio delta
        and exact spot order lot-size required to achieve delta-neutrality (Delta = 0).
        positions: [
            {"type": "CALL", "strike": 1.10, "vol": 0.08, "ttm_days": 30, "qty_contracts": 5},
            ...
        ]
        """
        total_delta_units = 0.0
        position_breakdown = []

        for pos in positions:
            ttm_years = pos.get("ttm_days", 30) / 365.0
            greeks = self.calculate_greeks(
                spot=spot_price,
                strike=pos["strike"],
                time_to_maturity_years=ttm_years,
                volatility=pos.get("vol", 0.10),
                option_type=pos.get("type", "CALL"),
            )
            qty = pos.get("qty_contracts", 1.0)
            contract_units = qty * contract_size
            pos_delta_units = greeks["delta"] * contract_units
            total_delta_units += pos_delta_units

            position_breakdown.append({
                "strike": pos["strike"],
                "type": pos.get("type", "CALL"),
                "qty": qty,
                "unit_delta": greeks["delta"],
                "total_delta_units": round(pos_delta_units, 2),
                "gamma": greeks["gamma"],
                "vega_usd": round(greeks["vega_per_1pct"] * contract_units, 2),
            })

        # Required hedge in spot units: -total_delta_units
        hedge_units = -total_delta_units
        hedge_lots = round(abs(hedge_units) / contract_size, 2)
        hedge_action = "SELL" if hedge_units < 0 else "BUY"

        recommendation = (
            f"To achieve delta-neutrality (Delta = 0), {hedge_action} {hedge_lots} standard lots "
            f"of spot at current market price ({spot_price:.5f})."
        )

        return {
            "spot_price": spot_price,
            "total_portfolio_delta_units": round(total_delta_units, 2),
            "net_delta_lots": round(total_delta_units / contract_size, 2),
            "hedge_recommendation": {
                "action": hedge_action,
                "lots": hedge_lots,
                "nominal_units": round(abs(hedge_units), 2),
                "instruction": recommendation,
            },
            "positions_analyzed": len(positions),
            "breakdown": position_breakdown,
        }
