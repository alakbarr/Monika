# ==============================================================================
# File: indicators/alpha_zoo/microstructure_factors.py
# Monika Quantitative Alpha Zoo: Institutional Microstructure & Order Flow Factors
# ==============================================================================

"""
Institutional market microstructure, volume-price interaction, and liquidity factors.

Adapts quantitative formulations from institutional research (Guotai Junan 191 Formulations):
- Volume-Price Rank Divergence Correlation
- Intraday High-Low Range Dispersion
- Volume-Weighted Momentum Surge
- Candlestick Shadow Asymmetry Reversal
- Turnover Acceleration Imbalance
- Breakout Volatility Expansion
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.alpha_zoo.meta import AlphaMeta
from indicators.alpha_zoo.registry import FactorRegistry
from indicators.factor_primitives import (
    delta,
    safe_div,
    signed_power,
    ts_corr,
    ts_mean,
    ts_rank,
    ts_std,
)


# ==============================================================================
# 1. Volume-Price Rank Divergence Correlation
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="microstructure_volume_price_rank_divergence",
        category="microstructure",
        lookback=6,
        columns_required=["close", "open", "volume"],
        min_warmup_bars=6,
        decay_horizon=3,
        direction="positive_bullish",
        formula_latex=r"-\text{corr}(\text{rank}(\Delta \ln(\text{Vol})), \text{rank}(\frac{C-O}{O}), 6)",
        description="Identifies volume-price divergence: Unbacked price advances forecast mean-reverting retracements.",
    )
)
def microstructure_volume_price_rank_divergence(df: pd.DataFrame) -> pd.Series:
    delta_log_vol = np.log(df["volume"] + 1.0) - np.log(df["volume"].shift(1) + 1.0)
    intraday_ret = safe_div(df["close"] - df["open"], df["open"])
    
    # Rolling correlation between volume change and price change
    r_vol = delta_log_vol.rolling(6).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
    r_ret = intraday_ret.rolling(6).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
    
    corr = r_vol.rolling(6).corr(r_ret)
    return - corr


# ==============================================================================
# 2. Intraday High-Low Range Dispersion
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="microstructure_range_dispersion",
        category="volatility",
        lookback=10,
        columns_required=["high", "low", "close"],
        min_warmup_bars=10,
        decay_horizon=4,
        direction="positive_bearish",
        formula_latex=r"\frac{H - L}{\text{SMA}(H - L, 10)} - 1.0",
        description="Relative intraday candle spread normalized against its 10-period moving average.",
    )
)
def microstructure_range_dispersion(df: pd.DataFrame) -> pd.Series:
    candle_range = df["high"] - df["low"]
    avg_range = candle_range.rolling(10, min_periods=3).mean()
    return safe_div(candle_range, avg_range) - 1.0


# ==============================================================================
# 3. Volume-Weighted Momentum Surge
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="microstructure_volume_weighted_momentum",
        category="momentum",
        lookback=14,
        columns_required=["close", "volume"],
        min_warmup_bars=14,
        decay_horizon=5,
        direction="positive_bullish",
        formula_latex=r"\frac{\text{SMA}(C \times \text{Vol}, 5)}{\text{SMA}(\text{Vol}, 5)} - \frac{\text{SMA}(C \times \text{Vol}, 14)}{\text{SMA}(\text{Vol}, 14)}",
        description="VWAP crossover divergence measuring short-term volume-weighted velocity relative to medium-term baseline.",
    )
)
def microstructure_volume_weighted_momentum(df: pd.DataFrame) -> pd.Series:
    pv = df["close"] * df["volume"]
    vwap_fast = safe_div(pv.rolling(5).sum(), df["volume"].rolling(5).sum())
    vwap_slow = safe_div(pv.rolling(14).sum(), df["volume"].rolling(14).sum())
    return safe_div(vwap_fast - vwap_slow, vwap_slow)


# ==============================================================================
# 4. Candlestick Shadow Asymmetry Reversal
# ==============================================================================
@FactorRegistry.register(
    AlphaMeta(
        name="microstructure_shadow_asymmetry",
        category="mean_reversion",
        lookback=5,
        columns_required=["open", "high", "low", "close"],
        min_warmup_bars=5,
        decay_horizon=2,
        direction="positive_bullish",
        formula_latex=r"\frac{\text{LowerShadow} - \text{UpperShadow}}{\text{High} - \text{Low}}",
        description="Calculates rejection shadow asymmetry: Long lower wicks indicate institutional absorption and support.",
    )
)
def microstructure_shadow_asymmetry(df: pd.DataFrame) -> pd.Series:
    candle_range = df["high"] - df["low"]
    body_high = np.maximum(df["open"], df["close"])
    body_low = np.minimum(df["open"], df["close"])
    
    upper_shadow = df["high"] - body_high
    lower_shadow = body_low - df["low"]
    
    asymmetry = safe_div(lower_shadow - upper_shadow, candle_range)
    return asymmetry.rolling(5, min_periods=1).mean()
