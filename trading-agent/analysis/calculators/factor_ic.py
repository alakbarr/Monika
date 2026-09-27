# ==============================================================================
# File: analysis/calculators/factor_ic.py
# Monika Information Coefficient (IC) & Predictive Factor Analytics Engine
# ==============================================================================

"""
Information Coefficient (IC) Analysis Engine.

Measures the statistical correlation between factor predictions at bar t and
subsequent forward returns at t + horizon.

Provides:
- Rolling Spearman Rank IC & Pearson Linear IC
- IC Mean, IC Standard Deviation, and IC Information Ratio (IC IR = Mean / Std)
- Student-t significance tests (t-statistic and p-value)
- Adaptive weight multipliers for confluence integration.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple
import numpy as np
import pandas as pd

try:
    from scipy import stats
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False
    stats = None


def _calc_corr(a: pd.Series, b: pd.Series, method: str = "spearman") -> float:
    """Computes correlation using pandas/scipy with automatic fallback."""
    if _HAS_SCIPY and stats is not None:
        fn = stats.spearmanr if method == "spearman" else stats.pearsonr
        c, _ = fn(a, b)
        return float(c) if not np.isnan(c) else 0.0
    
    if method == "spearman":
        c = a.rank().corr(b.rank())
    else:
        c = a.corr(b)
    return float(c) if (c is not None and not np.isnan(c)) else 0.0


def compute_forward_returns(prices: pd.Series, horizon: int = 1) -> pd.Series:
    """
    Computes lookahead forward returns: (P_{t+h} - P_t) / P_t.
    Note: Must be lagged appropriately when evaluated in live inference.
    """
    return (prices.shift(-horizon) - prices) / prices


def compute_factor_ic(
    factor: pd.Series,
    forward_returns: pd.Series,
    method: str = "spearman",
) -> float:
    """
    Computes point-in-time cross-sectional or longitudinal IC.
    """
    valid = factor.notna() & forward_returns.notna()
    if valid.sum() < 5:
        return 0.0

    return _calc_corr(factor[valid], forward_returns[valid], method=method)


def compute_rolling_factor_ic(
    factor: pd.Series,
    forward_returns: pd.Series,
    window: int = 30,
    method: str = "spearman",
) -> pd.Series:
    """
    Computes rolling Information Coefficient over a lookback window.
    """
    valid = factor.notna() & forward_returns.notna()
    res = pd.Series(np.nan, index=factor.index)

    for i in range(window, len(factor)):
        sl = slice(i - window, i)
        f_sub = factor.iloc[sl]
        r_sub = forward_returns.iloc[sl]
        sub_valid = f_sub.notna() & r_sub.notna()
        if sub_valid.sum() >= 10:
            c = _calc_corr(f_sub[sub_valid], r_sub[sub_valid], method=method)
            res.iloc[i] = c

    return res


def summarize_factor_ic(ic_series: pd.Series) -> Dict[str, float]:
    """
    Aggregates a rolling IC series into institutional performance metrics:
    - ic_mean: Average predictive strength
    - ic_std: Predictive volatility
    - ic_ir: Information Ratio (Mean / Std)
    - t_stat: Significance against null hypothesis of zero correlation
    - p_value: Two-tailed significance
    - positive_ratio: Proportion of periods with positive correlation
    """
    clean_ic = ic_series.dropna()
    n = len(clean_ic)
    if n < 5:
        return {
            "ic_mean": 0.0,
            "mean_ic": 0.0,
            "ic_std": 0.0,
            "ic_ir": 0.0,
            "information_ratio": 0.0,
            "t_stat": 0.0,
            "p_value": 1.0,
            "positive_ratio": 0.5,
        }

    mean = float(clean_ic.mean())
    std = float(clean_ic.std(ddof=1))
    std = max(1e-9, std)
    ir = mean / std
    t_stat = mean / (std / np.sqrt(n))
    if _HAS_SCIPY and stats is not None:
        p_val = float(2.0 * stats.t.sf(np.abs(t_stat), df=n - 1))
    else:
        # Standard normal approximation via complementary error function
        p_val = float(math.erfc(abs(t_stat) / math.sqrt(2.0)))
    pos_ratio = float((clean_ic > 0).mean())

    return {
        "ic_mean": round(mean, 4),
        "mean_ic": round(mean, 4),
        "ic_std": round(std, 4),
        "ic_ir": round(ir, 4),
        "information_ratio": round(ir, 4),
        "t_stat": round(t_stat, 3),
        "p_value": round(p_val, 5),
        "positive_ratio": round(pos_ratio, 3),
    }


def calculate_spearman_rank_ic(factor: pd.Series, forward_returns: pd.Series) -> float:
    """Public helper for Spearman Rank IC."""
    return compute_factor_ic(factor, forward_returns, method="spearman")


def evaluate_factor_predictive_power(
    factor: pd.Series,
    prices: pd.Series,
    forward_bars: int = 1,
) -> Dict[str, float]:
    """Evaluates predictive power of a factor series against prices."""
    fwd = compute_forward_returns(prices, horizon=forward_bars)
    rolling_ic = compute_rolling_factor_ic(factor, fwd, window=min(30, max(10, len(factor) // 2)))
    return summarize_factor_ic(rolling_ic)


def get_adaptive_confluence_multiplier(ic_ir: float) -> float:
    """
    Translates an empirical Factor IC IR into an adaptive weighting multiplier.
    - IR > 0.5: Excellent alpha (+30% weight) -> 1.30
    - IR in [0.2, 0.5]: Moderate alpha (+10% weight) -> 1.10
    - IR in [-0.1, 0.2]: Neutral alpha -> 1.00
    - IR < -0.1: Alpha decay/inverted (-30% weight) -> 0.70
    """
    if ic_ir >= 0.5:
        return 1.30
    elif ic_ir >= 0.2:
        return 1.10
    elif ic_ir >= -0.1:
        return 1.00
    elif ic_ir >= -0.3:
        return 0.85
    else:
        return 0.70
