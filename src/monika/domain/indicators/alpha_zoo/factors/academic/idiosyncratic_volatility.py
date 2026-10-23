"""Academic Idiosyncratic Volatility Alpha.

Reference:
    Ang, A., Hodrick, R. J., Xing, Y., & Zhang, X. (2006).
    The cross-section of volatility and expected returns.
    The Journal of Finance, 61(1), 259-299.
"""

from __future__ import annotations

import pandas as pd

from monika.domain.indicators.factor_primitives import safe_div

__alpha_meta__ = {
    "id": "academic_idiosyncratic_volatility",
    "name": "academic_idiosyncratic_volatility",
    "nickname": "Ang et al. Idiosyncratic Volatility",
    "category": "volatility",
    "theme": ["volatility"],
    "formula_latex": r"\text{std}(R_i - \text{trend}(R_i), 30)",
    "columns_required": ["close"],
    "lookback": 30,
    "min_warmup_bars": 30,
    "decay_horizon": 15,
    "direction": "positive_bearish",
    "description": "Ang et al. Idiosyncratic Volatility: Assets with high idiosyncratic volatility underperform.",
}


def compute(panel: dict | pd.DataFrame) -> pd.DataFrame | pd.Series:
    """Compute Idiosyncratic Volatility."""
    cl = panel["close"]
    ret = safe_div(cl - cl.shift(1), cl.shift(1))
    trend = ret.rolling(20, min_periods=5).mean()
    residual = ret - trend
    return residual.rolling(30, min_periods=10).std()
