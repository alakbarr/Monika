# ==============================================================================
# File: analysis/calculators/copula_tail_risk.py
# Monika Archimedean Copula Extreme Tail Risk Engine
# ==============================================================================

"""
Archimedean Copula Tail Risk Engine.

Models non-linear asymmetric co-dependence and joint crash risk between
correlated MT5 asset classes (e.g. XAUUSD, XTIUSD, EURUSD, BTCUSD).
Uses numerically stable log-space formulations to eliminate underflow.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger("TradingAgent.Calculators.CopulaTailRisk")


def _kendall_tau_numpy(x: np.ndarray, y: np.ndarray) -> float:
    """Computes Kendall's tau rank correlation using pure vectorized NumPy."""
    n = len(x)
    if n < 2:
        return 0.0
    dx = x[:, None] - x[None, :]
    dy = y[:, None] - y[None, :]
    tri = np.triu_indices(n, k=1)
    prod = np.sign(dx[tri]) * np.sign(dy[tri])
    concordant = np.sum(prod > 0)
    discordant = np.sum(prod < 0)
    total_pairs = len(tri[0])
    if total_pairs == 0:
        return 0.0
    return float((concordant - discordant) / total_pairs)


def empirical_cdf(series: pd.Series | np.ndarray) -> np.ndarray:
    """
    Transforms continuous asset returns into uniform marginals in (0, 1)
    using the empirical cumulative distribution function (rank / (N + 1)).
    """
    arr = np.asarray(series, dtype=np.float64)
    valid_mask = ~np.isnan(arr)
    n = np.sum(valid_mask)
    if n < 5:
        return np.full_like(arr, np.nan)

    ranks = pd.Series(arr[valid_mask]).rank(method="average").to_numpy(dtype=np.float64)
    # Avoid exact 0.0 or 1.0 for numerical safety in log / power transforms
    u_valid = (ranks - 0.5) / n
    out = np.full_like(arr, np.nan)
    out[valid_mask] = u_valid
    return out


def clayton_copula_cdf(u: np.ndarray | float, v: np.ndarray | float, theta: float) -> np.ndarray | float:
    """
    Bivariate Clayton Copula CDF:
    C(u, v; theta) = max((u^(-theta) + v^(-theta) - 1)^(-1/theta), 0)
    
    Models Lower Tail Dependence (joint crashes).
    theta must be > 0.
    """
    if theta <= 0:
        raise ValueError(f"Clayton theta must be > 0, got {theta}")

    u_arr = np.clip(np.asarray(u, dtype=np.float64), 1e-12, 1.0)
    v_arr = np.clip(np.asarray(v, dtype=np.float64), 1e-12, 1.0)

    # Numerically stable log-space computation
    # u^(-theta) + v^(-theta)
    log_u_term = -theta * np.log(u_arr)
    log_v_term = -theta * np.log(v_arr)
    sum_terms = np.exp(np.logaddexp(log_u_term, log_v_term))
    
    bracket = np.maximum(sum_terms - 1.0, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        res = np.power(bracket, -1.0 / theta)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)

    if isinstance(u, (int, float)) and isinstance(v, (int, float)):
        return float(res)
    return res


def gumbel_copula_cdf(u: np.ndarray | float, v: np.ndarray | float, theta: float) -> np.ndarray | float:
    """
    Bivariate Gumbel Copula CDF:
    C(u, v; theta) = exp(-((-ln(u))^theta + (-ln(v))^theta)^(1/theta))
    
    Models Upper Tail Dependence (joint surges).
    theta must be >= 1.0.
    """
    if theta < 1.0:
        raise ValueError(f"Gumbel theta must be >= 1.0, got {theta}")

    u_arr = np.clip(np.asarray(u, dtype=np.float64), 1e-12, 1.0 - 1e-12)
    v_arr = np.clip(np.asarray(v, dtype=np.float64), 1e-12, 1.0 - 1e-12)

    neg_log_u = -np.log(u_arr)
    neg_log_v = -np.log(v_arr)
    sum_pow = np.power(neg_log_u, theta) + np.power(neg_log_v, theta)
    res = np.exp(-np.power(sum_pow, 1.0 / theta))

    if isinstance(u, (int, float)) and isinstance(v, (int, float)):
        return float(res)
    return res


def fit_copula_from_tau(
    u: pd.Series | np.ndarray,
    v: pd.Series | np.ndarray,
    copula_type: str = "clayton",
) -> Tuple[float, float]:
    """
    Inverts empirical Kendall's tau to calibrate copula parameter theta
    and returns (theta, tail_dependence_lambda).
    
    Clayton:
      tau = theta / (theta + 2) => theta = 2*tau / (1 - tau)
      lambda_L = 2^(-1 / theta)
      
    Gumbel:
      tau = 1 - 1 / theta => theta = 1 / (1 - tau)
      lambda_U = 2 - 2^(1 / theta)
    """
    u_arr = np.asarray(u, dtype=np.float64)
    v_arr = np.asarray(v, dtype=np.float64)
    valid = ~np.isnan(u_arr) & ~np.isnan(v_arr)

    if np.sum(valid) < 10:
        return (1.0, 0.0)

    tau = _kendall_tau_numpy(u_arr[valid], v_arr[valid])
    if np.isnan(tau):
        tau = 0.0

    # Bound tau away from boundaries to avoid divide-by-zero
    tau_clipped = float(np.clip(tau, 0.01, 0.95))

    c_type = copula_type.lower().strip()
    if c_type == "clayton":
        theta = (2.0 * tau_clipped) / (1.0 - tau_clipped)
        lambda_l = float(2.0 ** (-1.0 / theta))
        return (theta, lambda_l)
    elif c_type == "gumbel":
        theta = 1.0 / (1.0 - tau_clipped)
        lambda_u = float(2.0 - 2.0 ** (1.0 / theta))
        return (theta, lambda_u)
    else:
        raise ValueError(f"Unsupported copula type: {copula_type}")


def evaluate_joint_tail_risk(
    returns_a: pd.Series,
    returns_b: pd.Series,
    tail_quantile: float = 0.05,
) -> Dict[str, Any]:
    """
    Evaluates joint crash probability and tail dependence between two assets.
    Returns quantitative tail risk report and risk haircut multiplier.
    """
    u = empirical_cdf(returns_a)
    v = empirical_cdf(returns_b)

    theta, lambda_lower = fit_copula_from_tau(u, v, copula_type="clayton")
    joint_crash_prob = float(clayton_copula_cdf(tail_quantile, tail_quantile, theta))

    # Independent benchmark: tail_quantile^2 (e.g. 0.05 * 0.05 = 0.0025)
    independent_prob = tail_quantile * tail_quantile
    crash_multiplier = joint_crash_prob / independent_prob if independent_prob > 0 else 1.0

    # Risk sizing haircut recommendation:
    # If joint crash probability is 2.5x higher than independent expectation,
    # scale sizing down progressively.
    if crash_multiplier > 3.0:
        sizing_haircut = 0.65
        risk_level = "ELEVATED_CRASH_RISK"
    elif crash_multiplier > 2.0:
        sizing_haircut = 0.80
        risk_level = "MODERATE_TAIL_DEPENDENCE"
    else:
        sizing_haircut = 1.00
        risk_level = "NORMAL"

    return {
        "theta": round(theta, 4),
        "lambda_lower_tail": round(lambda_lower, 4),
        "joint_crash_prob": round(joint_crash_prob, 5),
        "independent_prob": round(independent_prob, 5),
        "crash_excess_ratio": round(crash_multiplier, 2),
        "recommended_haircut": sizing_haircut,
        "risk_level": risk_level,
    }
