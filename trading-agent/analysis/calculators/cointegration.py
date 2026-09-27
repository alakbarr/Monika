# ==============================================================================
# File: analysis/calculators/cointegration.py
# Monika Cointegration & Ornstein-Uhlenbeck Pairs Trading Analytics
# ==============================================================================

"""
Cointegration & Mean-Reversion Analysis for MT5 Commodity and FX Pairs.

Specifically tailored for:
- XTIUSD vs XBRUSD (WTI vs Brent Crude Oil)
- XAUUSD vs XAGUSD (Gold vs Silver)
- EURUSD vs GBPUSD / USDCHF

Provides:
- Augmented Dickey-Fuller (ADF) stationarity testing.
- Engle-Granger two-step cointegration regression and residual testing.
- Ornstein-Uhlenbeck (OU) continuous parameter estimation:
  * Speed of mean reversion (kappa)
  * Long-term equilibrium level (theta)
  * Half-life of mean reversion (t_half = ln(2) / kappa)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple, Any
import numpy as np
import pandas as pd


def _linear_regression(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Pure NumPy OLS regression returning (slope, intercept)."""
    p = np.polyfit(x, y, 1)
    return float(p[0]), float(p[1])


@dataclass(frozen=True)
class CointegrationResult:
    is_cointegrated: bool
    hedge_ratio_beta: float
    intercept_alpha: float
    adf_statistic: float
    p_value: float
    critical_values: dict[str, float]
    ou_kappa: float
    ou_theta: float
    half_life_bars: float
    spread_zscore_latest: float

    @property
    def hedge_ratio(self) -> float:
        return self.hedge_ratio_beta

    @property
    def ou_half_life_bars(self) -> float:
        return self.half_life_bars

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            return getattr(self, item)
        raise KeyError(item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


def adf_test_approx(series: np.ndarray, max_lags: int = 1) -> Tuple[float, float, dict[str, float]]:
    """
    Augmented Dickey-Fuller test with constant drift.
    Returns (adf_stat, p_value_approx, crit_values).
    """
    clean = series[~np.isnan(series)]
    n = len(clean)
    if n < 20:
        return 0.0, 1.0, {"1%": -3.5, "5%": -2.88, "10%": -2.57}

    dy = np.diff(clean)
    y_lag = clean[:-1]

    # Simple OLS: dy_t = alpha + gamma * y_{t-1} + e_t
    x_mat = np.column_stack([np.ones(len(y_lag)), y_lag])
    try:
        beta, _, _, _ = np.linalg.lstsq(x_mat, dy, rcond=None)
        gamma = beta[1]
        residuals = dy - x_mat @ beta
        s2 = np.sum(residuals ** 2) / (len(dy) - 2)
        inv_xx = np.linalg.inv(x_mat.T @ x_mat)
        se_gamma = np.sqrt(s2 * inv_xx[1, 1])
        t_stat = gamma / se_gamma if se_gamma > 1e-12 else 0.0
    except Exception:
        return 0.0, 1.0, {"1%": -3.5, "5%": -2.88, "10%": -2.57}

    crit_values = {"1%": -3.46, "5%": -2.88, "10%": -2.57}

    # MacKinnon approximation for p-value
    if t_stat <= -3.46:
        p_val = 0.01
    elif t_stat <= -2.88:
        p_val = 0.05
    elif t_stat <= -2.57:
        p_val = 0.10
    else:
        p_val = min(1.0, 0.10 + 0.3 * (t_stat - (-2.57)))

    return float(t_stat), float(p_val), crit_values


def fit_ornstein_uhlenbeck(spread: np.ndarray, dt: float = 1.0) -> Tuple[float, float, float]:
    """
    Fits discrete AR(1) specification of continuous Ornstein-Uhlenbeck process:
    spread_{t} = a + b * spread_{t-1} + e_t
    
    where:
    kappa = -ln(b) / dt
    theta = a / (1 - b)
    half_life = ln(2) / kappa
    """
    clean = spread[~np.isnan(spread)]
    if len(clean) < 15:
        return 0.0, 0.0, 999.0

    y = clean[1:]
    x = clean[:-1]

    b, a = _linear_regression(x, y)

    if b <= 0.0 or b >= 1.0:
        # Not mean-reverting (explosive or negative unit root)
        return 0.0, float(np.mean(clean)), 999.0

    kappa = -np.log(b) / dt
    theta = a / (1.0 - b)
    half_life = np.log(2.0) / kappa if kappa > 1e-9 else 999.0

    return float(kappa), float(theta), float(half_life)


def analyze_pairs_cointegration(
    series_y: pd.Series | np.ndarray,
    series_x: pd.Series | np.ndarray,
) -> CointegrationResult:
    """
    Performs Engle-Granger two-step cointegration test between series Y and X:
    Step 1: OLS regression Y = alpha + beta * X
    Step 2: Stationary ADF test on residuals epsilon = Y - (alpha + beta * X)
    Step 3: OU mean-reversion speed and half-life estimation.
    """
    y = np.asarray(series_y, dtype=np.float64)
    x = np.asarray(series_x, dtype=np.float64)

    valid = ~np.isnan(y) & ~np.isnan(x)
    if valid.sum() < 30:
        return CointegrationResult(
            is_cointegrated=False,
            hedge_ratio_beta=1.0,
            intercept_alpha=0.0,
            adf_statistic=0.0,
            p_value=1.0,
            critical_values={"1%": -3.46, "5%": -2.88, "10%": -2.57},
            ou_kappa=0.0,
            ou_theta=0.0,
            half_life_bars=999.0,
            spread_zscore_latest=0.0,
        )

    y_clean = y[valid]
    x_clean = x[valid]

    # Step 1: OLS regression
    beta, alpha = _linear_regression(x_clean, y_clean)

    spread = y_clean - (alpha + beta * x_clean)

    # Step 2: ADF test on residuals
    adf_stat, p_val, crits = adf_test_approx(spread)
    is_coint = bool(p_val <= 0.05)

    # Step 3: OU fit
    kappa, theta, half_life = fit_ornstein_uhlenbeck(spread)

    # Latest z-score
    spread_std = np.std(spread, ddof=1)
    latest_z = float((spread[-1] - theta) / spread_std) if spread_std > 1e-9 else 0.0

    return CointegrationResult(
        is_cointegrated=is_coint,
        hedge_ratio_beta=round(beta, 4),
        intercept_alpha=round(alpha, 4),
        adf_statistic=round(adf_stat, 3),
        p_value=round(p_val, 4),
        critical_values=crits,
        ou_kappa=round(kappa, 4),
        ou_theta=round(theta, 4),
        half_life_bars=round(half_life, 2),
        spread_zscore_latest=round(latest_z, 2),
    )


# Alias for concise testing and strategy discovery
test_cointegration_ou = analyze_pairs_cointegration

