"""
Higher-order microstructure indicators beyond DOM OBI / Tick CVD.
Detects flow toxicity (VPIN), institutional price impact (Kyle's Lambda),
effective spread (Roll), and liquidity regime thinning (Amihud Illiquidity).

Asset-class routing:
- VPIN: BTCUSD, XAUUSD (informed toxicity detection with exact fractional volume slicing)
- Kyle's Lambda: EURUSD, GBPUSD, USDJPY, AUDUSD (FX institutional absorption with intercept OLS)
- Amihud Illiquidity: XAUUSD, XTIUSD, XBRUSD (commodity liquidity thinning with contract size normalization)
- Roll Spread: All instruments (serial covariance effective spread proxy)

Sources:
- VPIN: Easley, López de Prado, O'Hara (2012)
- Amihud: Amihud (2002)
- Kyle's Lambda: Kyle (1985)
- Roll: Roll (1984)
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Sequence
import numpy as np
import pandas as pd

logger = logging.getLogger("TradingAgent.Microstructure")

VPIN_SYMBOLS = {"BTCUSD", "XAUUSD"}
KYLE_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD"}
AMIHUD_SYMBOLS = {"XAUUSD", "XTIUSD", "XBRUSD"}

MT5_CONTRACT_SIZES: Dict[str, float] = {
    "XAUUSD": 100.0,
    "XAGUSD": 5000.0,
    "XTIUSD": 1000.0,
    "XBRUSD": 1000.0,
    "BTCUSD": 1.0,
    "ETHUSD": 1.0,
}


def compute_vpin(
    trades_df: pd.DataFrame,
    bucket_volume: float,
    n_buckets: int = 50,
) -> float:
    """
    Volume-Synchronized Probability of Informed Trading (VPIN) with exact
    fractional volume slicing across bucket boundaries.

    Measures order flow toxicity and adverse selection risk.
    VPIN > 0.70: highly toxic flow -> avoid entry.
    VPIN < 0.35: low toxicity retail flow -> clean entry.
    """
    if trades_df is None or len(trades_df) < 2 or bucket_volume <= 0:
        return 0.5

    price_col = "price" if "price" in trades_df.columns else "close"
    prices = np.asarray(trades_df[price_col], dtype=np.float64)
    volumes = np.asarray(trades_df["volume"], dtype=np.float64)

    # Bulk volume classification (BVC)
    price_changes = np.diff(prices, prepend=prices[0])
    buy_pct = np.where(price_changes > 0, 1.0, np.where(price_changes < 0, 0.0, 0.5))

    buy_vols = volumes * buy_pct
    sell_vols = volumes * (1.0 - buy_pct)

    # Exact fractional volume bucket slicing
    bucket_buys = []
    bucket_sells = []

    curr_b = 0.0
    curr_s = 0.0
    rem_space = bucket_volume

    for b_vol, s_vol, tot_v in zip(buy_vols, sell_vols, volumes):
        if tot_v <= 0:
            continue
        v_left = tot_v
        b_left = b_vol
        s_left = s_vol

        while v_left >= rem_space:
            # Slice fractionally
            frac = rem_space / v_left
            curr_b += b_left * frac
            curr_s += s_left * frac
            bucket_buys.append(curr_b)
            bucket_sells.append(curr_s)

            b_left -= b_left * frac
            s_left -= s_left * frac
            v_left -= rem_space

            curr_b = 0.0
            curr_s = 0.0
            rem_space = bucket_volume

        if v_left > 0:
            curr_b += b_left
            curr_s += s_left
            rem_space -= v_left

    if len(bucket_buys) < min(10, n_buckets):
        return 0.5

    buys_arr = np.array(bucket_buys[-n_buckets:])
    sells_arr = np.array(bucket_sells[-n_buckets:])
    imbalance = np.abs(buys_arr - sells_arr)
    denom = np.sum(buys_arr + sells_arr)

    if denom <= 1e-12:
        return 0.5

    vpin = float(np.sum(imbalance) / denom)
    return float(np.clip(vpin, 0.0, 1.0))


def compute_roll_effective_spread(
    close: pd.Series,
    window: int = 20,
) -> pd.Series:
    """
    Roll (1984) Effective Bid-Ask Spread estimator based on serial covariance:
    s = 2 * sqrt(-min(0, cov(dP_t, dP_{t-1})))
    """
    if close is None or len(close) < window:
        return pd.Series(0.0, index=close.index if close is not None else None)

    dp = close.diff().fillna(0.0)
    dp_lag = dp.shift(1).fillna(0.0)

    # Rolling covariance
    cov = dp.rolling(window).cov(dp_lag)
    # Roll spread is 2 * sqrt(-cov) when cov < 0, else 0.0
    roll_spread = 2.0 * np.sqrt(np.maximum(0.0, -cov))
    return roll_spread.fillna(0.0)


def compute_amihud_illiquidity(
    returns: pd.Series,
    dollar_volume: pd.Series,
    window: int = 20,
) -> pd.Series:
    """
    Amihud (2002) Illiquidity Ratio: absolute return per dollar of volume.
    Measures price sensitivity to volume. High illiquidity signals thin depth.
    """
    if returns is None or len(returns) < 2:
        return pd.Series(dtype=float)

    safe_vol = dollar_volume.replace(0, np.nan).fillna(1.0)
    ratio = returns.abs() / safe_vol
    return ratio.rolling(window).mean().fillna(0.0)


def compute_kyle_lambda(
    price_changes: pd.Series,
    signed_volume: pd.Series,
    window: int = 20,
) -> pd.Series:
    """
    Kyle (1985) Lambda: slope of price change on signed trade volume with OLS intercept:
    dP_t = alpha + lambda * Flow_t + e_t
    """
    if price_changes is None or len(price_changes) < window:
        return pd.Series(dtype=float)

    def _ols_slope_intercept(y: np.ndarray, x: np.ndarray) -> float:
        if len(y) < 3:
            return 0.0
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        x_dm = x - x_mean
        denom = float(np.sum(x_dm * x_dm))
        if denom < 1e-12:
            return 0.0
        y_dm = y - y_mean
        return float(np.sum(x_dm * y_dm) / denom)

    res = pd.Series(index=price_changes.index, dtype=float)
    y_vals = price_changes.values
    x_vals = signed_volume.values

    for i in range(window, len(price_changes)):
        sl = slice(i - window, i)
        res.iloc[i] = _ols_slope_intercept(y_vals[sl], x_vals[sl])

    return res.fillna(0.0)


def get_microstructure_metrics(
    symbol: str,
    trades_df: Optional[pd.DataFrame] = None,
    ohlcv_df: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """
    Compute asset-class routed microstructure metrics for a symbol on MT5.
    """
    sym = symbol.upper()
    metrics: Dict[str, float] = {}

    # 1. VPIN for Crypto & Precious Metals
    if sym in VPIN_SYMBOLS and trades_df is not None and len(trades_df) >= 10:
        bucket_vol = float(trades_df["volume"].sum() / 50.0)
        metrics["vpin"] = round(compute_vpin(trades_df, bucket_volume=bucket_vol), 3)

    # 2. Kyle's Lambda for Forex pairs
    if sym in KYLE_SYMBOLS and ohlcv_df is not None and len(ohlcv_df) >= 20:
        close = ohlcv_df["close"].astype(float)
        vol = ohlcv_df["volume"].astype(float)
        price_chg = close.diff().fillna(0.0)
        signed_vol = vol * np.sign(price_chg)
        k_series = compute_kyle_lambda(price_chg, signed_vol, window=20)
        val_k = k_series.iloc[-1] if not k_series.empty else 0.0
        metrics["kyle_lambda"] = round(0.0 if pd.isna(val_k) else float(val_k), 6)

    # 3. Amihud Illiquidity for Commodities (with MT5 contract size)
    if sym in AMIHUD_SYMBOLS and ohlcv_df is not None and len(ohlcv_df) >= 20:
        close = ohlcv_df["close"].astype(float)
        vol = ohlcv_df["volume"].astype(float)
        contract_size = MT5_CONTRACT_SIZES.get(sym, 1.0)
        rets = close.pct_change().fillna(0.0)
        dollar_vol = vol * contract_size * close
        amihud_series = compute_amihud_illiquidity(rets, dollar_vol, window=20)
        val_am = amihud_series.iloc[-1]
        metrics["amihud_illiquidity"] = round(0.0 if pd.isna(val_am) else float(val_am), 8)

    # 4. Roll Effective Spread for all instruments
    if ohlcv_df is not None and len(ohlcv_df) >= 20:
        roll_s = compute_roll_effective_spread(ohlcv_df["close"].astype(float), window=20)
        val_roll = roll_s.iloc[-1]
        metrics["roll_spread"] = round(0.0 if pd.isna(val_roll) else float(val_roll), 5)

    return metrics


def calculate_vpin_fractional(
    df: pd.DataFrame,
    bucket_volume: float = 500.0,
    num_buckets: int = 10,
) -> Dict[str, float]:
    """
    Computes VPIN with fractional bucket slicing on OHLCV or trade data.
    """
    vpin_val = compute_vpin(df, bucket_volume=bucket_volume, n_buckets=num_buckets)
    return {"vpin": float(vpin_val)}


def calculate_roll_effective_spread(
    close: pd.Series,
    window: int = 20,
) -> Dict[str, float]:
    """
    Computes Roll effective spread on close prices.
    """
    spread_series = compute_roll_effective_spread(close, window=window)
    val = float(spread_series.iloc[-1]) if not spread_series.empty else 0.0
    return {"effective_spread": max(0.0, val)}


def calculate_kyles_lambda_ols(
    df: pd.DataFrame,
    window: int = 20,
) -> Dict[str, float]:
    """
    Computes Kyle's Lambda via OLS regression of price changes on signed volume.
    """
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    price_chg = close.diff().fillna(0.0)
    signed_vol = vol * np.sign(price_chg)
    k_series = compute_kyle_lambda(price_chg, signed_vol, window=window)
    val = float(k_series.iloc[-1]) if not k_series.empty else 0.0
    return {"kyles_lambda": 0.0 if np.isnan(val) else val}


def calculate_amihud_illiquidity_mt5(
    df: pd.DataFrame,
    contract_size: float = 1.0,
    window: int = 20,
) -> Dict[str, float]:
    """
    Computes Amihud illiquidity normalized by MT5 contract size.
    """
    close = df["close"].astype(float)
    vol = df["volume"].astype(float)
    rets = close.pct_change().fillna(0.0)
    dollar_vol = vol * contract_size * close
    amihud_series = compute_amihud_illiquidity(rets, dollar_vol, window=window)
    val = float(amihud_series.iloc[-1]) if not amihud_series.empty else 0.0
    return {"amihud_illiquidity": max(0.0, 0.0 if np.isnan(val) else val)}

