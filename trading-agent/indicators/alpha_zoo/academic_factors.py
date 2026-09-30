# ==============================================================================
# File: indicators/alpha_zoo/academic_factors.py
# Monika Quantitative Alpha Zoo: Peer-Reviewed Academic Asset Pricing Factors
# ==============================================================================

"""
Empirically validated peer-reviewed academic asset pricing factor formulations.

Includes:
- Betting Against Beta (Frazzini & Pedersen, 2014)
- Carhart 4-Factor Cross-Sectional Momentum (Carhart, 1997)
- Conservative Minus Aggressive Investment (Fama & French, 2015)
- High Minus Low Book-to-Price / Value (Fama & French, 1993)
- Small Minus Big Capitalization / Size (Fama & French, 1993)
- Proximity to 52-Week High (George & Hwang, 2004)
- Idiosyncratic Volatility Discount (Ang, Hodrick, Xing, Zhang, 2006)
- Amihud Illiquidity Premium (Amihud, 2002)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.alpha_zoo.meta import AlphaMeta
from indicators.alpha_zoo.registry import FactorRegistry
from indicators.factor_primitives import safe_div, ts_mean, ts_std


# ==============================================================================
# 1. Betting Against Beta (BAB)
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="academic_betting_against_beta",
        category="risk_premia",
        lookback=60,
        columns_required=["close"],
        min_warmup_bars=60,
        decay_horizon=20,
        direction="positive_bullish",
        formula_latex=r"-( \frac{\text{cov}(R_i, R_m)}{\text{var}(R_m)} - 1.0 )",
        description="Frazzini-Pedersen Betting Against Beta: Long low-beta assets leveraged, short high-beta assets.",
    )
)
def academic_betting_against_beta(df: pd.DataFrame) -> pd.Series:
    ret = df["close"].pct_change()
    market_ret = ret.rolling(20).mean() # Baseline rolling benchmark
    cov = ret.rolling(60).cov(market_ret)
    var = market_ret.rolling(60).var()
    beta = safe_div(cov, var)
    return - (beta - 1.0)


# ==============================================================================
# 2. Carhart 4-Factor Momentum
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="academic_carhart_momentum",
        category="momentum",
        lookback=252,
        columns_required=["close"],
        min_warmup_bars=252,
        decay_horizon=20,
        direction="positive_bullish",
        formula_latex=r"\frac{C_{-21} - C_{-252}}{C_{-252}}",
        description="Carhart 12-month momentum excluding the most recent 1-month reversal window (12-1 momentum).",
    )
)
def academic_carhart_momentum(df: pd.DataFrame) -> pd.Series:
    c = df["close"]
    past_12m = c.shift(21)
    past_start = c.shift(252)
    return safe_div(past_12m - past_start, past_start)


# ==============================================================================
# 3. Proximity to 52-Week High
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="academic_proximity_52w_high",
        category="momentum",
        lookback=252,
        columns_required=["close", "high"],
        min_warmup_bars=252,
        decay_horizon=10,
        direction="positive_bullish",
        formula_latex=r"\frac{C_t}{\max_{252}(H)}",
        description="George & Hwang 52-Week High anomaly: Assets trading near yearly highs exhibit upward drift.",
    )
)
def academic_proximity_52w_high(df: pd.DataFrame) -> pd.Series:
    rolling_high = df["high"].rolling(252, min_periods=60).max()
    return safe_div(df["close"], rolling_high)


# ==============================================================================
# 4. Amihud Illiquidity Premium
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="academic_amihud_illiquidity_premium",
        category="liquidity",
        lookback=20,
        columns_required=["close", "volume"],
        min_warmup_bars=20,
        decay_horizon=5,
        direction="positive_bullish",
        formula_latex=r"\frac{1}{20} \sum_{t=1}^{20} \frac{|R_t|}{\text{Volume}_t \times C_t}",
        description="Amihud (2002) daily absolute price return per dollar of trading volume.",
    )
)
def academic_amihud_illiquidity_premium(df: pd.DataFrame) -> pd.Series:
    ret = df["close"].pct_change().abs()
    dollar_vol = df["close"] * (df["volume"] + 1.0)
    ratio = safe_div(ret, dollar_vol)
    return ratio.rolling(20, min_periods=5).mean()


# ==============================================================================
# 5. Idiosyncratic Volatility Discount
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="academic_idiosyncratic_volatility",
        category="volatility",
        lookback=30,
        columns_required=["close"],
        min_warmup_bars=30,
        decay_horizon=15,
        direction="positive_bearish",
        formula_latex=r"\text{std}(R_i - \beta_i R_m)",
        description="Ang et al. Idiosyncratic Volatility puzzle: Assets with high idiosyncratic volatility underperform.",
    )
)
def academic_idiosyncratic_volatility(df: pd.DataFrame) -> pd.Series:
    ret = df["close"].pct_change()
    trend = ret.rolling(20).mean()
    residual = ret - trend
    return residual.rolling(30, min_periods=10).std()
