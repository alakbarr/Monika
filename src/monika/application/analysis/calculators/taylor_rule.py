# ==============================================================================
# File: analysis/calculators/taylor_rule.py
# ==============================================================================

"""
Taylor Rule Implied Policy Rate Calculator.
Computes standard Taylor (1993), Inertial (Clarida-Gali-Gertler), and Mankiw rules
to evaluate whether central bank monetary policy is overly restrictive, neutral, or behind the curve.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Calculators.TaylorRule")


@dataclass
class TaylorRuleResult:
    central_bank: str  # "Federal Reserve", "ECB", "BOE", etc.
    actual_policy_rate: float  # Current Fed Funds / Cash Rate
    taylor_implied_rate: float  # Classical Taylor (1993) rate
    inertial_implied_rate: float  # Rate with policy inertia smoothing (rho)
    rate_gap: float  # actual - taylor_implied
    policy_stance: str  # "RESTRICTIVE", "NEUTRAL", "ACCOMMODATIVE"
    neutral_rate_r_star: float  # r* assumption
    inflation_rate: float  # pi (e.g. Core PCE / CPI)
    inflation_target: float  # pi* (2.0%)
    output_gap: float  # y - y*
    unemployment_gap: Optional[float] = None  # u - u*
    formula_breakdown: Dict[str, float] = field(default_factory=dict)
    market_implications: Dict[str, str] = field(default_factory=dict)
    interpretation: str = ""


import math

CENTRAL_BANK_DEFAULTS = {
    "Federal Reserve": {"r_star": 1.0, "target": 2.0, "nairu": 4.2},
    "ECB": {"r_star": 0.5, "target": 2.0, "nairu": 6.5},
    "BOE": {"r_star": 1.25, "target": 2.0, "nairu": 4.5},
    "BOJ": {"r_star": -0.25, "target": 2.0, "nairu": 2.5},
    "SNB": {"r_star": 0.25, "target": 1.0, "nairu": 2.2},
    "RBA": {"r_star": 1.25, "target": 2.5, "nairu": 4.0},
    "BOC": {"r_star": 1.0, "target": 2.0, "nairu": 6.0},
}


class TaylorRuleCalculator:
    """
    Computes Taylor Rule equilibrium rate benchmarks.
    """

    @classmethod
    def calculate_fed_taylor_rule(
        cls,
        actual_effr: float,
        current_inflation: float,
        r_star: float = 1.0,  # Neutral real interest rate (Laubach-Williams r-star ~0.8-1.2%)
        inflation_target: float = 2.0,
        output_gap: Optional[float] = None,
        unemployment_rate: Optional[float] = None,
        natural_unemployment_u_star: float = 4.2,  # CBO estimate of NAIRU
        alpha_inflation: float = 0.5,
        alpha_output: float = 0.5,
        smoothing_rho: float = 0.80,
        previous_effr: Optional[float] = None,
        central_bank: str = "Federal Reserve",
    ) -> TaylorRuleResult:
        """
        Calculates Fed Taylor Rule implied rate:
        Standard: R = r* + pi + alpha_pi*(pi - pi*) + alpha_y*(y - y*)
        If output_gap is None, estimates output gap via Okun's Law: y - y* = -2.0 * (u - u*)
        """
        if not math.isfinite(actual_effr) or not math.isfinite(current_inflation):
            return TaylorRuleResult(
                central_bank=central_bank,
                actual_policy_rate=actual_effr if math.isfinite(actual_effr) else 0.0,
                taylor_implied_rate=0.0,
                inertial_implied_rate=0.0,
                rate_gap=0.0,
                policy_stance="DATA_UNAVAILABLE",
                neutral_rate_r_star=r_star,
                inflation_rate=current_inflation if math.isfinite(current_inflation) else 0.0,
                inflation_target=inflation_target,
                output_gap=0.0,
                interpretation="Inflation or policy rate data missing or non-finite; cannot calculate Taylor Rule.",
            )
        # Determine output gap
        u_gap = None
        if output_gap is None:
            if unemployment_rate is not None:
                u_gap = round(unemployment_rate - natural_unemployment_u_star, 2)
                # Okun's law coefficient roughly -2.0
                effective_output_gap = round(-2.0 * u_gap, 2)
            else:
                effective_output_gap = 0.0  # Assumes closed output gap if unstated
        else:
            effective_output_gap = output_gap

        # Inflation gap: pi - pi*
        infl_gap = round(current_inflation - inflation_target, 2)

        # Classical Taylor Rule formula:
        # R = r* + pi + 0.5*(pi - pi*) + 0.5*(output_gap)
        taylor_rate = r_star + current_inflation + (alpha_inflation * infl_gap) + (alpha_output * effective_output_gap)
        taylor_rate = round(taylor_rate, 2)

        # Inertial rule (Clarida et al. 2000): R_t = rho*R_{t-1} + (1-rho)*R*_taylor
        prev = previous_effr if previous_effr is not None else actual_effr
        inertial_rate = round((smoothing_rho * prev) + ((1.0 - smoothing_rho) * taylor_rate), 2)

        # Rate Gap: Actual - Taylor
        rate_gap = round(actual_effr - taylor_rate, 2)

        if rate_gap > 0.75:
            stance = "OVERLY RESTRICTIVE"
            interp = (
                f"Actual Fed Funds Rate ({actual_effr:.2f}%) is {rate_gap:+.2f}% HIGHER than Taylor Rule implied rate "
                f"({taylor_rate:.2f}%). The Fed is exerting significant restrictive drag; rate cuts are fundamentally justified."
            )
        elif rate_gap < -0.75:
            stance = "ACCOMMODATIVE / BEHIND THE CURVE"
            interp = (
                f"Actual Fed Funds Rate ({actual_effr:.2f}%) is {abs(rate_gap):.2f}% LOWER than Taylor Rule implied rate "
                f"({taylor_rate:.2f}%). Policy remains loose relative to macroeconomic pressures."
            )
        else:
            stance = "NEUTRAL / WELL-CALIBRATED"
            interp = (
                f"Actual Fed Funds Rate ({actual_effr:.2f}%) is closely aligned with Taylor Rule implied rate "
                f"({taylor_rate:.2f}% with delta {rate_gap:+.2f}%). Monetary policy matches economic fundamentals."
            )

        market_impl = {
            "USD (DXY)": "DOWNSIDE PRESSURE"
            if rate_gap > 0.75
            else ("UPSIDE SUPPORT" if rate_gap < -0.75 else "BALANCED"),
            "US 10Y Yields": "LOWER BOUND REPRICING" if rate_gap > 0.75 else "BEARISH STEEPENER RISK",
            "XAUUSD (Gold)": "BULLISH LONG-TERM" if rate_gap > 0.75 else "HEADWIND FROM HIGHER RATES",
            "Rate Cut Outlook": f"Taylor Rule projects neutral target of {taylor_rate:.2f}%, suggesting ~{max(0, int(round(rate_gap / 0.25)))} cuts of 25bps."
            if rate_gap > 0
            else "No cuts implied.",
        }

        breakdown = {
            "r_star": r_star,
            "inflation_rate": current_inflation,
            "inflation_target": inflation_target,
            "inflation_gap": infl_gap,
            "inflation_penalty": round(alpha_inflation * infl_gap, 2),
            "output_gap": effective_output_gap,
            "output_penalty": round(alpha_output * effective_output_gap, 2),
            "classical_taylor_rate": taylor_rate,
            "inertial_smoothed_rate": inertial_rate,
            "actual_effr": actual_effr,
            "rate_gap": rate_gap,
        }

        return TaylorRuleResult(
            central_bank=central_bank,
            actual_policy_rate=actual_effr,
            taylor_implied_rate=taylor_rate,
            inertial_implied_rate=inertial_rate,
            rate_gap=rate_gap,
            policy_stance=stance,
            neutral_rate_r_star=r_star,
            inflation_rate=current_inflation,
            inflation_target=inflation_target,
            output_gap=effective_output_gap,
            unemployment_gap=u_gap,
            formula_breakdown=breakdown,
            market_implications=market_impl,
            interpretation=interp,
        )

    @classmethod
    def calculate_central_bank_taylor_rule(
        cls,
        central_bank: str,
        actual_rate: float,
        current_inflation: float,
        output_gap: Optional[float] = None,
        unemployment_rate: Optional[float] = None,
        previous_rate: Optional[float] = None,
    ) -> TaylorRuleResult:
        """Calculates Taylor Rule using calibrated parameters for specified central bank."""
        cb_conf = CENTRAL_BANK_DEFAULTS.get(central_bank, CENTRAL_BANK_DEFAULTS["Federal Reserve"])
        return cls.calculate_fed_taylor_rule(
            actual_effr=actual_rate,
            current_inflation=current_inflation,
            r_star=cb_conf["r_star"],
            inflation_target=cb_conf["target"],
            output_gap=output_gap,
            unemployment_rate=unemployment_rate,
            natural_unemployment_u_star=cb_conf["nairu"],
            previous_effr=previous_rate,
            central_bank=central_bank,
        )
