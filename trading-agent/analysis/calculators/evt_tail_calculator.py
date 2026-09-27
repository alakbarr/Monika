# ==============================================================================
# File: analysis/calculators/evt_tail_calculator.py
# Monika Extreme Value Theory (EVT) GPD Tail Risk Engine
# ==============================================================================

"""
Extreme Value Theory (EVT) Peaks-Over-Threshold (POT) Tail Risk Engine.

Fits a Generalized Pareto Distribution (GPD) to historical extreme return losses
to assess fat-tail crash risk beyond standard Gaussian/normal assumptions.

Methodology:
- Extracts worst negative returns exceeding threshold u (typically 95th percentile loss).
- Fits GPD parameters: shape xi (tail index) and scale sigma via MLE.
- Calculates asymptotic standard error: stderr = |1 + xi| / sqrt(n_exceedances).
- Classifies tail regime:
  * 'fat' (Frechet-type heavy tail, xi > 0)
  * 'exponential' (Gumbel-type medium tail, xi ~ 0)
  * 'bounded' (Weibull-type light tail, xi < 0)
- Applies sizing penalty if statistically significant heavy tail is detected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any
import numpy as np
import pandas as pd

try:
    from scipy import stats
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False
    stats = None


@dataclass(frozen=True)
class TailRiskProfile:
    shape_xi: float
    scale_sigma: float
    shape_stderr: float
    threshold_u: float
    n_exceedances: int
    tail_class: str  # 'fat', 'exponential', 'bounded'
    is_statistically_significant: bool
    risk_sizing_multiplier: float
    worst_observed_loss: float


def fit_gpd_tail(
    returns: pd.Series | np.ndarray,
    quantile_threshold: float = 0.95,
    significance_sigmas: float = 2.0,
) -> TailRiskProfile:
    """
    Fits GPD to the negative tail (losses) using Peaks-Over-Threshold.
    
    Args:
        returns: Time-series of arithmetic returns.
        quantile_threshold: Threshold percentile for loss exceedances (default 0.95).
        significance_sigmas: Significance threshold in standard deviations (default 2.0).
        
    Returns:
        TailRiskProfile containing tail shape, classification, and recommended sizing multiplier.
    """
    clean_rets = np.asarray(returns[~np.isnan(returns)], dtype=np.float64)
    if len(clean_rets) < 50:
        # Insufficient data to fit EVT tail reliably; default to neutral
        return TailRiskProfile(
            shape_xi=0.0,
            scale_sigma=0.0,
            shape_stderr=0.0,
            threshold_u=0.0,
            n_exceedances=0,
            tail_class="exponential",
            is_statistically_significant=False,
            risk_sizing_multiplier=1.0,
            worst_observed_loss=float(clean_rets.min()) if len(clean_rets) > 0 else 0.0,
        )

    # Focus on positive losses (L = -r for r < 0)
    losses = -clean_rets[clean_rets < 0.0]
    if len(losses) < 20:
        return TailRiskProfile(
            shape_xi=0.0,
            scale_sigma=0.0,
            shape_stderr=0.0,
            threshold_u=0.0,
            n_exceedances=0,
            tail_class="exponential",
            is_statistically_significant=False,
            risk_sizing_multiplier=1.0,
            worst_observed_loss=float(losses.max()) if len(losses) > 0 else 0.0,
        )

    threshold_u = float(np.percentile(losses, quantile_threshold * 100.0))
    exceedances = losses[losses > threshold_u] - threshold_u
    n_exceed = len(exceedances)

    if n_exceed < 8:
        return TailRiskProfile(
            shape_xi=0.0,
            scale_sigma=0.0,
            shape_stderr=0.0,
            threshold_u=threshold_u,
            n_exceedances=n_exceed,
            tail_class="exponential",
            is_statistically_significant=False,
            risk_sizing_multiplier=1.0,
            worst_observed_loss=float(losses.max()),
        )

    xi = 0.0
    sigma = float(np.std(exceedances)) if len(exceedances) > 0 else 1.0
    fitted = False

    # Try scipy.stats.genpareto if installed
    if _HAS_SCIPY and stats is not None:
        try:
            c_fit, loc_fit, scale_fit = stats.genpareto.fit(exceedances, floc=0.0)
            xi = float(c_fit)
            sigma = float(scale_fit)
            fitted = True
        except Exception:
            fitted = False

    # Pure-NumPy Hosking-Wallis (1987) Elementary Method of Moments fallback
    if not fitted:
        mean_y = float(np.mean(exceedances))
        var_y = float(np.var(exceedances, ddof=1)) if n_exceed > 1 else float(np.var(exceedances))
        if var_y > 1e-12 and mean_y > 1e-12:
            hw_xi = 0.5 * (1.0 - (mean_y ** 2) / var_y)
            hw_xi = float(np.clip(hw_xi, -1.0, 1.5))
            hw_sigma = 0.5 * mean_y * (1.0 + (mean_y ** 2) / var_y)
            xi = hw_xi
            sigma = max(hw_sigma, 1e-6)
        else:
            xi = 0.0
            sigma = max(mean_y, 1e-6)

    # Asymptotic standard error for MLE/moments estimator
    shape_stderr = float(np.abs(1.0 + xi) / np.sqrt(n_exceed)) if n_exceed > 1 else 1.0
    t_stat = np.abs(xi) / shape_stderr if shape_stderr > 1e-9 else 0.0
    is_sig = bool(t_stat >= significance_sigmas)

    if is_sig and xi > 0.15:
        tail_class = "fat"
        # Severe fat tail: scale down lot sizing to prevent ruin
        sizing_mult = 0.50 if xi > 0.35 else 0.75
    elif is_sig and xi < -0.15:
        tail_class = "bounded"
        sizing_mult = 1.00
    else:
        tail_class = "exponential"
        sizing_mult = 1.00

    return TailRiskProfile(
        shape_xi=round(xi, 4),
        scale_sigma=round(sigma, 6),
        shape_stderr=round(shape_stderr, 4),
        threshold_u=round(threshold_u, 6),
        n_exceedances=int(n_exceed),
        tail_class=tail_class,
        is_statistically_significant=is_sig,
        risk_sizing_multiplier=sizing_mult,
        worst_observed_loss=round(float(losses.max()), 6),
    )


def fit_evt_peaks_over_threshold(
    returns: pd.Series | np.ndarray,
    quantile: float = 0.95,
    significance_sigmas: float = 2.0,
) -> Dict[str, Any]:
    """
    Convenience wrapper returning a dictionary format for EVT tail analysis.

    Args:
        returns: Series or array of asset returns.
        quantile: Quantile threshold for extreme loss detection (default 0.95).
        significance_sigmas: Statistical significance threshold in standard deviations.

    Returns:
        Dictionary with EVT parameters, regime classification, and sizing penalty.
    """
    profile = fit_gpd_tail(
        returns,
        quantile_threshold=quantile,
        significance_sigmas=significance_sigmas,
    )
    return {
        "shape_xi": profile.shape_xi,
        "scale_sigma": profile.scale_sigma,
        "shape_stderr": profile.shape_stderr,
        "threshold_u": profile.threshold_u,
        "exceedance_count": profile.n_exceedances,
        "tail_risk_regime": profile.tail_class,
        "is_statistically_significant": profile.is_statistically_significant,
        "risk_sizing_multiplier": profile.risk_sizing_multiplier,
        "worst_observed_loss": profile.worst_observed_loss,
    }
