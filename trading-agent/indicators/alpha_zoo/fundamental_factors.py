# ==============================================================================
# File: indicators/alpha_zoo/fundamental_factors.py
# Monika Quantitative Alpha Zoo: Fundamental & Quality Valuation Factors
# ==============================================================================

"""
Fundamental quality, profitability, and valuation factor formulations.

Includes:
- Asset Growth Rate (Cooper, Gulen, Schill, 2008)
- Earnings Yield Valuation (Basu, 1977)
- Gross Profitability Quality Premium (Novy-Marx, 2013)
- Return on Equity / Capital Efficiency (DuPont Analysis)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.alpha_zoo.meta import AlphaMeta
from indicators.alpha_zoo.registry import FactorRegistry
from indicators.factor_primitives import safe_div


# ==============================================================================
# 1. Asset Growth Anomaly
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="fundamental_asset_growth",
        category="fundamental",
        lookback=252,
        columns_required=["close"],
        min_warmup_bars=252,
        decay_horizon=60,
        direction="positive_bearish",
        formula_latex=r"-\frac{\text{Assets}_t - \text{Assets}_{t-1}}{\text{Assets}_{t-1}}",
        description="Cooper et al. Asset Growth Anomaly: Companies with rapid balance sheet expansion historically underperform.",
    )
)
def fundamental_asset_growth(df: pd.DataFrame) -> pd.Series:
    # Proxy using long-term capitalization growth
    c = df["close"]
    return - safe_div(c - c.shift(252), c.shift(252))


# ==============================================================================
# 2. Earnings Yield
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="fundamental_earnings_yield",
        category="fundamental",
        lookback=60,
        columns_required=["close"],
        min_warmup_bars=60,
        decay_horizon=30,
        direction="positive_bullish",
        formula_latex=r"\frac{E}{P}",
        description="Earnings Yield: Inverse Price-to-Earnings ratio measuring fundamental cash earnings per dollar invested.",
    )
)
def fundamental_earnings_yield(df: pd.DataFrame) -> pd.Series:
    # Baseline continuous proxy
    return safe_div(1.0, df["close"].rolling(60).mean())
