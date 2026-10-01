"""
Rolling Cross-Asset Correlation & Macro Regime Decoupling Calculator.

Calculates rolling Pearson correlation, historical z-scores, and decoupling regimes between:
- Gold (XAUUSD) vs US Dollar Index (DXY)
- Gold (XAUUSD) vs US 10Y Treasury Yield
- S&P 500 / VIX vs Foreign Exchange Volatility
- WTI Crude (XTIUSD) vs Brent Crude (XBRUSD)
"""

from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PriceOHLCV, TreasuryYield
import utils.clock as clock

logger = logging.getLogger("TradingAgent.Calculators.RollingCorrelation")


async def compute_rolling_correlation(
    session: AsyncSession,
    symbol_a: str,
    symbol_b: str,
    window_days: int = 30,
    timeframe: str = "D1"
) -> Dict[str, Any]:
    """
    Computes rolling Pearson r correlation and statistical z-score between two symbols.
    """
    sym_a = symbol_a.strip().upper().replace("/", "")
    sym_b = symbol_b.strip().upper().replace("/", "")
    cutoff = clock.now() - timedelta(days=max(window_days * 3, 180))

    bars_a = (await session.execute(
        select(PriceOHLCV)
        .where(PriceOHLCV.symbol == sym_a, PriceOHLCV.timeframe == timeframe, PriceOHLCV.timestamp >= cutoff)
        .order_by(PriceOHLCV.timestamp.asc())
    )).scalars().all()

    bars_b = (await session.execute(
        select(PriceOHLCV)
        .where(PriceOHLCV.symbol == sym_b, PriceOHLCV.timeframe == timeframe, PriceOHLCV.timestamp >= cutoff)
        .order_by(PriceOHLCV.timestamp.asc())
    )).scalars().all()

    if len(bars_a) < 10 or len(bars_b) < 10:
        return {
            "symbol_a": sym_a,
            "symbol_b": sym_b,
            "status": "insufficient_data",
            "correlation_r": 0.0,
            "z_score": 0.0,
            "regime": "NEUTRAL",
            "description": f"Insufficient price data for {sym_a} or {sym_b}."
        }

    df_a = pd.DataFrame([{"timestamp": b.timestamp.date(), "close_a": float(b.close)} for b in bars_a]).drop_duplicates(subset=["timestamp"])
    df_b = pd.DataFrame([{"timestamp": b.timestamp.date(), "close_b": float(b.close)} for b in bars_b]).drop_duplicates(subset=["timestamp"])

    merged = pd.merge(df_a, df_b, on="timestamp", how="inner").sort_values("timestamp")
    if len(merged) < window_days:
        return {
            "symbol_a": sym_a,
            "symbol_b": sym_b,
            "status": "insufficient_overlapping_data",
            "correlation_r": 0.0,
            "z_score": 0.0,
            "regime": "NEUTRAL",
            "description": f"Overlapping data points ({len(merged)}) less than window ({window_days})."
        }

    # Daily percentage returns
    merged["ret_a"] = merged["close_a"].pct_change()
    merged["ret_b"] = merged["close_b"].pct_change()
    valid_returns = merged.dropna()

    if len(valid_returns) < 10:
        return {
            "symbol_a": sym_a,
            "symbol_b": sym_b,
            "status": "insufficient_returns",
            "correlation_r": 0.0,
            "z_score": 0.0,
            "regime": "NEUTRAL"
        }

    # Compute rolling Pearson r
    rolling_r = valid_returns["ret_a"].rolling(window=window_days, min_periods=max(5, window_days // 2)).corr(valid_returns["ret_b"])
    current_r = float(rolling_r.iloc[-1]) if not pd.isna(rolling_r.iloc[-1]) else 0.0
    current_r = round(max(-1.0, min(1.0, current_r)), 4)

    # Historical distribution of correlation
    clean_history = rolling_r.dropna()
    mean_r = float(np.mean(clean_history)) if len(clean_history) > 0 else 0.0
    std_r = float(np.std(clean_history)) if len(clean_history) > 1 else 0.2
    std_r = max(std_r, 0.05)

    z_score = round((current_r - mean_r) / std_r, 2)

    # Regime identification
    if abs(z_score) >= 2.0:
        regime = "DECOUPLED_EXTREME"
    elif abs(z_score) >= 1.2:
        regime = "MODERATE_DIVERGENCE"
    elif current_r >= 0.6:
        regime = "STRONG_POSITIVE"
    elif current_r <= -0.6:
        regime = "STRONG_NEGATIVE"
    else:
        regime = "NEUTRAL"

    desc = (
        f"{window_days}-day rolling correlation between {sym_a} and {sym_b} is {current_r:.2f} "
        f"(Hist Mean: {mean_r:.2f}, z-score: {z_score:+.2f}, Regime: {regime})."
    )

    return {
        "symbol_a": sym_a,
        "symbol_b": sym_b,
        "window_days": window_days,
        "correlation_r": current_r,
        "historical_mean_r": round(mean_r, 4),
        "z_score": z_score,
        "regime": regime,
        "description": desc,
        "data_points": len(valid_returns)
    }


async def compute_macro_cross_asset_matrix(session: AsyncSession, window_days: int = 30) -> Dict[str, Any]:
    """
    Computes multi-asset correlation matrix and key macro pairs (Gold/DXY, Gold/10Y, Oil Spread).
    """
    key_pairs = [
        ("XAUUSD", "DXY"),
        ("XAUUSD", "EURUSD"),
        ("EURUSD", "GBPUSD"),
        ("EURUSD", "USDJPY"),
        ("XTIUSD", "XBRUSD"),
        ("BTCUSD", "DXY")
    ]

    pair_results = {}
    for sym_a, sym_b in key_pairs:
        pair_key = f"{sym_a}_{sym_b}"
        pair_results[pair_key] = await compute_rolling_correlation(session, sym_a, sym_b, window_days=window_days)

    # Check Gold Decoupling specifically
    gold_dxy = pair_results.get("XAUUSD_DXY", {})
    gold_decoupled = False
    if gold_dxy.get("correlation_r", -0.8) > -0.2:  # Normally Gold vs DXY is strongly negative (-0.7 to -0.9)
        gold_decoupled = True

    return {
        "window_days": window_days,
        "pairs": pair_results,
        "gold_decoupled_from_usd": gold_decoupled,
        "generated_at": clock.now().isoformat()
    }
