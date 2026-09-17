"""
Higher-order microstructure indicators beyond DOM OBI / Tick CVD.
Detects flow toxicity (VPIN), institutional price impact (Kyle's Lambda),
and liquidity regime thinning (Amihud Illiquidity).

Asset-class routing:
- VPIN: BTCUSD, XAUUSD (informed toxicity detection)
- Kyle's Lambda: EURUSD, GBPUSD, USDJPY, AUDUSD (FX institutional absorption)
- Amihud Illiquidity: XAUUSD, XTIUSD, XBRUSD (commodity liquidity thinning)
- Roll Spread: Skipped (covered by live MT5 bid/ask spread)

Sources:
- VPIN: Easley, López de Prado, O'Hara (2012)
- Amihud: Amihud (2002)
- Kyle's Lambda: Kyle (1985)
"""
import logging
from typing import Dict, Optional, Sequence
import numpy as np
import pandas as pd

logger = logging.getLogger("TradingAgent.Microstructure")

VPIN_SYMBOLS = {"BTCUSD", "XAUUSD"}
KYLE_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD"}
AMIHUD_SYMBOLS = {"XAUUSD", "XTIUSD", "XBRUSD"}


def compute_vpin(
    trades_df: pd.DataFrame,
    bucket_volume: float,
    n_buckets: int = 50,
) -> float:
    """
    Volume-Synchronized Probability of Informed Trading (VPIN).
    Measures order flow toxicity and adverse selection risk.
    VPIN > 0.70: highly toxic flow -> avoid entry.
    VPIN < 0.35: low toxicity retail flow -> clean entry.
    """
    if trades_df is None or len(trades_df) < 2 or bucket_volume <= 0:
        return 0.5

    prices = np.asarray(trades_df["price"], dtype=np.float64)
    volumes = np.asarray(trades_df["volume"], dtype=np.float64)

    # Bulk volume classification (BVC)
    price_changes = np.diff(prices, prepend=prices[0])
    buy_pct = np.where(price_changes > 0, 1.0, np.where(price_changes < 0, 0.0, 0.5))

    buy_volumes = volumes * buy_pct
    sell_volumes = volumes * (1.0 - buy_pct)

    cum_vol = np.cumsum(volumes)
    bucket_ids = (cum_vol / bucket_volume).astype(int)

    bucket_buy = pd.Series(buy_volumes).groupby(bucket_ids).sum()
    bucket_sell = pd.Series(sell_volumes).groupby(bucket_ids).sum()

    if len(bucket_buy) < min(10, n_buckets):
        return 0.5

    imbalance = (bucket_buy - bucket_sell).abs()
    total = bucket_buy + bucket_sell
    recent_imbalance = imbalance.iloc[-n_buckets:]
    recent_total = total.iloc[-n_buckets:]

    denom = recent_total.sum()
    if denom <= 1e-12:
        return 0.5

    vpin = float(recent_imbalance.sum() / denom)
    return float(np.clip(vpin, 0.0, 1.0))


def compute_amihud_illiquidity(
    returns: pd.Series,
    dollar_volume: pd.Series,
    window: int = 20,
) -> pd.Series:
    """
    Amihud (2002) Illiquidity Ratio: absolute return per dollar of volume.
    Measures price sensitivity to volume. High illiquidity signals thin depth and slippage danger.
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
    Kyle (1985) Lambda: slope of price change on signed trade volume.
    High Lambda indicates that order flow moves prices sharply (strong institutional information).
    """
    if price_changes is None or len(price_changes) < window:
        return pd.Series(dtype=float)

    def _ols_slope(y, x):
        if len(y) < 3:
            return 0.0
        x_dm = x - np.mean(x)
        denom = float(np.sum(x_dm * x_dm))
        if denom < 1e-12:
            return 0.0
        y_dm = y - np.mean(y)
        return float(np.sum(x_dm * y_dm) / denom)

    res = pd.Series(index=price_changes.index, dtype=float)
    y_vals = price_changes.values
    x_vals = signed_volume.values

    for i in range(window, len(price_changes)):
        sl = slice(i - window, i)
        res.iloc[i] = _ols_slope(y_vals[sl], x_vals[sl])

    return res.fillna(0.0)


def get_microstructure_metrics(
    symbol: str,
    trades_df: Optional[pd.DataFrame] = None,
    ohlcv_df: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    """
    Compute asset-class routed microstructure metrics for a symbol.
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

    # 3. Amihud Illiquidity for Commodities
    if sym in AMIHUD_SYMBOLS and ohlcv_df is not None and len(ohlcv_df) >= 20:
        close = ohlcv_df["close"].astype(float)
        vol = ohlcv_df["volume"].astype(float)
        rets = close.pct_change().fillna(0.0)
        dollar_vol = vol * close
        amihud_series = compute_amihud_illiquidity(rets, dollar_vol, window=20)
        val_am = amihud_series.iloc[-1]
        metrics["amihud_illiquidity"] = round(0.0 if pd.isna(val_am) else float(val_am), 8)

    return metrics
