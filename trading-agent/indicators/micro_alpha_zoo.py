# ==============================================================================
# File: indicators/micro_alpha_zoo.py
# Monika High-Performance Micro-Alpha Factor Zoo (20 MT5 Factor Formulations)
# ==============================================================================

"""
Monika Micro-Alpha Factor Zoo.

Implements 20 vectorized quantitative alpha factor formulas tailored for
Forex, Metals (XAUUSD), Energy (XTIUSD), and Crypto (BTCUSD) on MT5.
Utilizes exact factor primitives (vectorized numpy/bottleneck, strict NaN
propagation, and lookahead-free lagging).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from indicators.factor_primitives import (
    decay_linear,
    delta,
    rank,
    safe_div,
    scale,
    signed_power,
    ts_argmax,
    ts_argmin,
    ts_corr,
    ts_cov,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std,
    zscore,
)


@dataclass(frozen=True)
class FactorMetadata:
    name: str
    category: str  # momentum, mean_reversion, volatility, liquidity
    lookback: int
    inputs: list[str]
    direction: str  # positive_bullish, positive_bearish
    description: str


class MicroAlphaZoo:
    """Registry and calculator for institutional micro-alpha factor formulations."""

    _REGISTRY: dict[str, tuple[Callable[[pd.DataFrame], pd.Series | pd.DataFrame], FactorMetadata]] = {}

    @classmethod
    def register(cls, name: str, category: str, lookback: int, inputs: list[str], direction: str, description: str):
        def decorator(fn: Callable[[pd.DataFrame], pd.Series | pd.DataFrame]):
            meta = FactorMetadata(
                name=name,
                category=category,
                lookback=lookback,
                inputs=inputs,
                direction=direction,
                description=description,
            )
            cls._REGISTRY[name] = (fn, meta)
            return fn
        return decorator

    @classmethod
    def list_factors(cls) -> list[FactorMetadata]:
        return [meta for _, meta in cls._REGISTRY.values()]

    @classmethod
    def compute_factor(cls, name: str, df: pd.DataFrame) -> pd.Series | pd.DataFrame:
        if name not in cls._REGISTRY:
            raise KeyError(f"Alpha factor '{name}' not found in MicroAlphaZoo registry")
        fn, _ = cls._REGISTRY[name]
        return fn(df)

    @classmethod
    def compute_all_factors(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Computes all registered alpha factors and concatenates into a DataFrame."""
        results = {}
        for name, (fn, _) in cls._REGISTRY.items():
            try:
                res = fn(df)
                if isinstance(res, pd.DataFrame):
                    if res.shape[1] == 1:
                        results[name] = res.iloc[:, 0]
                    else:
                        for col in res.columns:
                            results[f"{name}_{col}"] = res[col]
                else:
                    results[name] = res
            except Exception:
                results[name] = pd.Series(np.nan, index=df.index)
        return pd.DataFrame(results, index=df.index)


# ==============================================================================
# 20 QUANTITATIVE ALPHA FORMULATIONS
# ==============================================================================

@MicroAlphaZoo.register(
    name="alpha_001",
    category="momentum",
    lookback=6,
    inputs=["close"],
    direction="positive_bullish",
    description="Short-term return volatility surge: ts_argmax of squared 1-bar returns over 5 bars.",
)
def alpha_001(df: pd.DataFrame) -> pd.Series:
    ret = delta(df["close"], 1) / df["close"].shift(1)
    ret_df = pd.DataFrame({"r": ret})
    sq = signed_power(ret_df, 2.0)
    am = ts_argmax(sq, 5)
    return am["r"] - 2.5


@MicroAlphaZoo.register(
    name="alpha_002",
    category="mean_reversion",
    lookback=6,
    inputs=["open", "close", "volume"],
    direction="positive_bullish",
    description="Volume-price exhaustion reversal: -1 * correlation of volume delta and candle body ratio.",
)
def alpha_002(df: pd.DataFrame) -> pd.Series:
    vol_delta = delta(np.log(df["volume"].replace(0, np.nan)), 2)
    body_ratio = safe_div(df["close"] - df["open"], df["open"])
    df_vol = pd.DataFrame({"v": vol_delta})
    df_body = pd.DataFrame({"v": body_ratio})
    corr = ts_corr(df_vol, df_body, 6)
    return -1.0 * corr["v"]


@MicroAlphaZoo.register(
    name="alpha_003",
    category="mean_reversion",
    lookback=10,
    inputs=["open", "volume"],
    direction="positive_bullish",
    description="Early session open-volume divergence: -1 * rolling correlation of open price and volume.",
)
def alpha_003(df: pd.DataFrame) -> pd.Series:
    df_open = pd.DataFrame({"s": df["open"]})
    df_vol = pd.DataFrame({"s": df["volume"]})
    corr = ts_corr(df_open, df_vol, 10)
    return -1.0 * corr["s"]


@MicroAlphaZoo.register(
    name="alpha_006",
    category="momentum",
    lookback=10,
    inputs=["open", "volume"],
    direction="positive_bearish",
    description="Accumulation flow divergence: rolling correlation of open and volume.",
)
def alpha_006(df: pd.DataFrame) -> pd.Series:
    df_open = pd.DataFrame({"s": df["open"]})
    df_vol = pd.DataFrame({"s": df["volume"]})
    corr = ts_corr(df_open, df_vol, 10)
    return corr["s"]


@MicroAlphaZoo.register(
    name="alpha_009",
    category="momentum",
    lookback=5,
    inputs=["close"],
    direction="positive_bullish",
    description="Velocity ratio: delta(close, 1) over delta(close, 5).",
)
def alpha_009(df: pd.DataFrame) -> pd.Series:
    d1 = delta(df["close"], 1)
    d5 = delta(df["close"], 5)
    return safe_div(d1, d5)


@MicroAlphaZoo.register(
    name="alpha_012",
    category="mean_reversion",
    lookback=2,
    inputs=["close", "volume"],
    direction="positive_bullish",
    description="Contrarian volume-delta impulse: sign(delta(volume, 1)) * (-1 * delta(close, 1)).",
)
def alpha_012(df: pd.DataFrame) -> pd.Series:
    d_vol = delta(df["volume"], 1)
    d_close = delta(df["close"], 1)
    return np.sign(d_vol) * (-1.0 * d_close)


@MicroAlphaZoo.register(
    name="alpha_028",
    category="momentum",
    lookback=6,
    inputs=["close", "volume"],
    direction="positive_bullish",
    description="Volume-price correlation plus trend momentum.",
)
def alpha_028(df: pd.DataFrame) -> pd.Series:
    df_close = pd.DataFrame({"s": df["close"]})
    df_vol = pd.DataFrame({"s": df["volume"]})
    corr = ts_corr(df_close, df_vol, 5)["s"]
    d5 = delta(df["close"], 5)
    return corr + np.sign(d5)


@MicroAlphaZoo.register(
    name="alpha_033",
    category="momentum",
    lookback=5,
    inputs=["open", "close"],
    direction="positive_bullish",
    description="Intraday candle body expansion: safe_div(close - open, close).",
)
def alpha_033(df: pd.DataFrame) -> pd.Series:
    return safe_div(df["close"] - df["open"], df["close"])


@MicroAlphaZoo.register(
    name="alpha_041",
    category="volatility",
    lookback=1,
    inputs=["high", "low", "close"],
    direction="positive_bullish",
    description="Geometric shadow ratio: safe_div(high * low, close**2).",
)
def alpha_041(df: pd.DataFrame) -> pd.Series:
    return safe_div(df["high"] * df["low"], df["close"] ** 2) - 1.0


@MicroAlphaZoo.register(
    name="alpha_053",
    category="mean_reversion",
    lookback=10,
    inputs=["high", "low", "close"],
    direction="positive_bullish",
    description="Wick rejection reversion: -1 * delta of upper vs lower shadow balance over 9 bars.",
)
def alpha_053(df: pd.DataFrame) -> pd.Series:
    lower_wick = df["close"] - df["low"]
    upper_wick = df["high"] - df["close"]
    num = lower_wick - upper_wick
    den = lower_wick + upper_wick
    ratio = safe_div(num, den)
    return -1.0 * delta(ratio, 9)


@MicroAlphaZoo.register(
    name="alpha_054",
    category="mean_reversion",
    lookback=2,
    inputs=["open", "high", "low", "close"],
    direction="positive_bullish",
    description="Extreme tail thrust: -1 * (low - close) * open / ((low - high) * close).",
)
def alpha_054(df: pd.DataFrame) -> pd.Series:
    num = -1.0 * (df["low"] - df["close"]) * df["open"]
    den = (df["low"] - df["high"]) * df["close"]
    return safe_div(num, den)


@MicroAlphaZoo.register(
    name="alpha_060",
    category="momentum",
    lookback=10,
    inputs=["high", "low", "close", "volume"],
    direction="positive_bullish",
    description="Volume-weighted buying pressure vs high reach: (2 * close - low - high) / (high - low) * volume.",
)
def alpha_060(df: pd.DataFrame) -> pd.Series:
    bp = 2.0 * df["close"] - df["low"] - df["high"]
    rng = df["high"] - df["low"]
    flow = safe_div(bp, rng) * df["volume"]
    df_close = pd.DataFrame({"s": df["close"]})
    am = ts_argmax(df_close, 10)["s"]
    return safe_div(flow, df["volume"].rolling(10).mean()) - (am / 5.0)


@MicroAlphaZoo.register(
    name="alpha_amihud_illiquidity",
    category="liquidity",
    lookback=20,
    inputs=["close", "volume"],
    direction="positive_bearish",
    description="Amihud illiquidity ratio: rolling mean of |return| / (volume * close).",
)
def alpha_amihud_illiquidity(df: pd.DataFrame) -> pd.Series:
    ret = abs(delta(df["close"], 1)) / df["close"].shift(1)
    dollar_vol = df["volume"] * df["close"]
    impact = safe_div(ret, dollar_vol)
    return impact.rolling(20, min_periods=20).mean()


@MicroAlphaZoo.register(
    name="alpha_hl_volatility_ratio",
    category="volatility",
    lookback=10,
    inputs=["high", "low"],
    direction="positive_bullish",
    description="High-Low volatility expansion ratio: std(high - low, 10) / mean(high - low, 10).",
)
def alpha_hl_volatility_ratio(df: pd.DataFrame) -> pd.Series:
    rng = pd.DataFrame({"r": df["high"] - df["low"]})
    std = ts_std(rng, 10)["r"]
    mean = ts_mean(rng, 10)["r"]
    return safe_div(std, mean)


@MicroAlphaZoo.register(
    name="alpha_return_skewness",
    category="volatility",
    lookback=20,
    inputs=["close"],
    direction="positive_bullish",
    description="Rolling 20-bar return skewness (3rd standardized moment).",
)
def alpha_return_skewness(df: pd.DataFrame) -> pd.Series:
    ret = delta(df["close"], 1) / df["close"].shift(1)
    return ret.rolling(20, min_periods=20).skew()


@MicroAlphaZoo.register(
    name="alpha_liquidity_sweep_reversion",
    category="mean_reversion",
    lookback=11,
    inputs=["high", "low"],
    direction="positive_bearish",
    description="False breakout penetration: (high - ts_max(high[1], 10)) / (high - low).",
)
def alpha_liquidity_sweep_reversion(df: pd.DataFrame) -> pd.Series:
    df_high_prev = pd.DataFrame({"h": df["high"].shift(1)})
    prior_max = ts_max(df_high_prev, 10)["h"]
    sweep = df["high"] - prior_max
    rng = df["high"] - df["low"]
    return safe_div(sweep.clip(lower=0), rng)


@MicroAlphaZoo.register(
    name="alpha_volume_vwap_deviation",
    category="mean_reversion",
    lookback=20,
    inputs=["close", "volume"],
    direction="positive_bullish",
    description="Rolling 20-bar VWAP stretch z-score: (close - VWAP) / std(close, 20).",
)
def alpha_volume_vwap_deviation(df: pd.DataFrame) -> pd.Series:
    pv = df["close"] * df["volume"]
    vwap = pv.rolling(20, min_periods=20).sum() / df["volume"].rolling(20, min_periods=20).sum()
    std = df["close"].rolling(20, min_periods=20).std()
    return safe_div(df["close"] - vwap, std)


@MicroAlphaZoo.register(
    name="alpha_acceleration_momentum",
    category="momentum",
    lookback=7,
    inputs=["close"],
    direction="positive_bullish",
    description="Momentum acceleration (2nd derivative): delta(delta(close, 3), 3).",
)
def alpha_acceleration_momentum(df: pd.DataFrame) -> pd.Series:
    vel = delta(df["close"], 3)
    return delta(vel, 3)


@MicroAlphaZoo.register(
    name="alpha_range_efficiency",
    category="momentum",
    lookback=1,
    inputs=["open", "high", "low", "close"],
    direction="positive_bullish",
    description="Candle range efficiency: |close - open| / (high - low).",
)
def alpha_range_efficiency(df: pd.DataFrame) -> pd.Series:
    body = abs(df["close"] - df["open"])
    rng = df["high"] - df["low"]
    return safe_div(body, rng)


@MicroAlphaZoo.register(
    name="alpha_decay_trend_strength",
    category="momentum",
    lookback=11,
    inputs=["close"],
    direction="positive_bullish",
    description="Linearly decaying weighted momentum over 10 bars.",
)
def alpha_decay_trend_strength(df: pd.DataFrame) -> pd.Series:
    d1 = pd.DataFrame({"d": delta(df["close"], 1)})
    decay = decay_linear(d1, 10)
    return decay["d"]
