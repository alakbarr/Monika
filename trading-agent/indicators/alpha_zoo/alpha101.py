# ==============================================================================
# File: indicators/alpha_zoo/alpha101.py
# Monika Quantitative Alpha Zoo: WorldQuant Alpha 101 Formulations for MT5
# ==============================================================================

"""
WorldQuant Alpha 101 Adaptations for Continuous Financial Time Series (Forex, Metals, Crypto).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.alpha_zoo.meta import AlphaMeta
from indicators.alpha_zoo.registry import FactorRegistry
from indicators.factor_primitives import (
    decay_linear,
    delta,
    safe_div,
    signed_power,
    ts_argmax,
    ts_corr,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std,
)


@FactorRegistry.register(
    AlphaMeta(
        name="wq_alpha_001",
        category="momentum",
        lookback=5,
        columns_required=["close"],
        min_warmup_bars=6,
        decay_horizon=5,
        direction="positive_bullish",
        formula_latex=r"\text{rank}(\text{ts\_argmax}(\text{signed\_power}(\Delta C / C_{-1}, 2), 5)) - 0.5",
        description="Volatility surge momentum: Normalized argmax position of squared returns over 5 bars.",
    )
)
def wq_alpha_001(df: pd.DataFrame) -> pd.Series:
    ret = delta(df["close"], 1) / df["close"].shift(1)
    sq = np.sign(ret) * (ret ** 2)
    am = sq.rolling(5, min_periods=5).apply(lambda x: np.argmax(x) if not np.isnan(x).any() else np.nan, raw=True)
    return am / 4.0 - 0.5


@FactorRegistry.register(
    AlphaMeta(
        name="wq_alpha_006",
        category="mean_reversion",
        lookback=10,
        columns_required=["open", "volume"],
        min_warmup_bars=10,
        decay_horizon=3,
        direction="positive_bearish",
        formula_latex=r"-\text{ts\_corr}(O, V, 10)",
        description="Inverse correlation between Open price and Volume over 10 bars.",
    )
)
def wq_alpha_006(df: pd.DataFrame) -> pd.Series:
    corr = df["open"].rolling(10, min_periods=10).corr(df["volume"].astype(float))
    return -1.0 * corr


@FactorRegistry.register(
    AlphaMeta(
        name="wq_alpha_012",
        category="momentum",
        lookback=2,
        columns_required=["close", "volume"],
        min_warmup_bars=2,
        decay_horizon=2,
        direction="positive_bullish",
        formula_latex=r"\text{sign}(\Delta V) \cdot (-\Delta C)",
        description="Volume divergence contrarian flow: price change scaled by volume sign.",
    )
)
def wq_alpha_012(df: pd.DataFrame) -> pd.Series:
    d_vol = delta(df["volume"].astype(float), 1)
    d_close = delta(df["close"], 1)
    return np.sign(d_vol) * (-1.0 * d_close)


@FactorRegistry.register(
    AlphaMeta(
        name="wq_alpha_041",
        category="mean_reversion",
        lookback=1,
        columns_required=["high", "low", "close", "volume"],
        min_warmup_bars=1,
        decay_horizon=2,
        direction="positive_bullish",
        formula_latex=r"\sqrt{H \cdot L} - \text{VWAP}",
        description="Geometric mean of candle extreme vs Volume-Weighted Average Price.",
    )
)
def wq_alpha_041(df: pd.DataFrame) -> pd.Series:
    geo_mean = np.sqrt(df["high"] * df["low"])
    vol = df["volume"].astype(float)
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_tp_vol = (typical_price * vol).cumsum()
    cum_vol = vol.cumsum().replace(0, np.nan)
    vwap = cum_tp_vol / cum_vol
    return geo_mean - vwap


@FactorRegistry.register(
    AlphaMeta(
        name="wq_alpha_053",
        category="momentum",
        lookback=10,
        columns_required=["high", "low", "close"],
        min_warmup_bars=10,
        decay_horizon=3,
        direction="positive_bearish",
        formula_latex=r"-\Delta\left(\frac{(C - L) - (H - C)}{H - L}, 9\right)",
        description="Change in internal candle close balance over 9 bars.",
    )
)
def wq_alpha_053(df: pd.DataFrame) -> pd.Series:
    num = (df["close"] - df["low"]) - (df["high"] - df["close"])
    den = (df["high"] - df["low"]).replace(0, np.nan)
    balance = safe_div(num, den)
    return -1.0 * delta(balance, 9)


@FactorRegistry.register(
    AlphaMeta(
        name="wq_alpha_101",
        category="momentum",
        lookback=1,
        columns_required=["open", "high", "low", "close"],
        min_warmup_bars=1,
        decay_horizon=2,
        direction="positive_bullish",
        formula_latex=r"\frac{C - O}{(H - L) + \epsilon}",
        description="Intraday normalized trend velocity: body size over candle span.",
    )
)
def wq_alpha_101(df: pd.DataFrame) -> pd.Series:
    return safe_div(df["close"] - df["open"], (df["high"] - df["low"]))
