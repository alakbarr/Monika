"""Shared rolling-correlation calculator dipakai baik oleh RiskGate
(per-trade heat check) maupun portfolio_correlation_gate (multi-trade
proposal filter), agar keduanya tidak pernah menilai korelasi dua simbol
secara berbeda. Fallback ke tabel statis hanya bila histori harga < 30
bar D1."""
import logging
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PriceOHLCV

logger = logging.getLogger('TradingAgent.DynamicCorrelation')

STATIC_CORRELATION_FALLBACK = {
    ('EURUSD', 'GBPUSD'): 0.85, ('EURUSD', 'AUDUSD'): 0.70, ('EURUSD', 'USDJPY'): -0.80,
    ('GBPUSD', 'AUDUSD'): 0.65, ('GBPUSD', 'USDJPY'): -0.75, ('AUDUSD', 'USDJPY'): -0.65,
    ('XAUUSD', 'USDJPY'): -0.60, ('XAUUSD', 'EURUSD'): 0.65, ('XAUUSD', 'GBPUSD'): 0.55,
    ('XAUUSD', 'AUDUSD'): 0.60, ('XAUUSD', 'XTIUSD'): 0.45, ('XAUUSD', 'BTCUSD'): 0.35,
    ('EURUSD', 'XTIUSD'): 0.45, ('GBPUSD', 'XTIUSD'): 0.40, ('AUDUSD', 'XTIUSD'): 0.55,
    ('BTCUSD', 'EURUSD'): 0.30, ('BTCUSD', 'USDJPY'): -0.25, ('BTCUSD', 'GBPUSD'): 0.25,
    ('BTCUSD', 'AUDUSD'): 0.35, ('BTCUSD', 'XTIUSD'): 0.20, ('USDJPY', 'XTIUSD'): -0.40,
    ('XTIUSD', 'XBRUSD'): 0.95, ('XBRUSD', 'EURUSD'): 0.45, ('XBRUSD', 'USDJPY'): -0.40, ('XAUUSD', 'XBRUSD'): 0.45,
}

def is_crypto_or_commodity_symbol(sym: str) -> bool:
    s = (sym or "").upper()
    return any(k in s for k in ('BTC', 'ETH', 'SOL', 'XRP', 'BNB', 'DOGE', 'ADA', 'XTI', 'XBR', 'XAU'))

def get_correlation_uncertainty_multiplier(sym1: str, sym2: str, source: str) -> float:
    """
    Mengembalikan sizing multiplier penalti jika fallback statis digunakan untuk aset non-stasioner.
    Default: 0.8x jika crypto/komoditas pada static fallback, 1.0x jika dynamic.
    """
    if "static_fallback" in source and (is_crypto_or_commodity_symbol(sym1) or is_crypto_or_commodity_symbol(sym2)):
        return 0.80
    return 1.00

def _static_fallback(sym1: str, sym2: str) -> float:
    val = STATIC_CORRELATION_FALLBACK.get((sym1, sym2)) or STATIC_CORRELATION_FALLBACK.get((sym2, sym1))
    if val is not None:
        res = val
    else:
        s1, s2 = (sym1 or "").upper(), (sym2 or "").upper()
        if (s1.endswith("USD") and s2.endswith("USD")) or (s1.startswith("USD") and s2.startswith("USD")):
            res = 0.65
        elif (s1.endswith("USD") and s2.startswith("USD")) or (s1.startswith("USD") and s2.endswith("USD")):
            res = -0.65
        else:
            res = 0.40
    if is_crypto_or_commodity_symbol(sym1) or is_crypto_or_commodity_symbol(sym2):
        logger.warning(f"[DynamicCorrelation] Using static correlation fallback for {sym1}-{sym2}: {res:.2f} (D1 history < 20 bars). Exercise caution.")
    return res

from datetime import datetime
from typing import Optional

async def get_rolling_correlation(
    session: AsyncSession,
    symbol1: str,
    symbol2: str,
    lookback_bars: int = 60,
    as_of: Optional[datetime] = None,
    method: str = "ewma",
    span: int = 30,
) -> tuple[float, str]:
    """
    Menghitung korelasi dinamis antara 2 instrumen dengan metode EWMA (default) atau rolling Pearson.
    EWMA (span=30, lambda ~0.94) memberikan bobot lebih tinggi pada data terkini untuk merespons regime shift.
    """
    if symbol1 == symbol2:
        return (1.0, 'identity')
    try:
        q1 = select(PriceOHLCV.timestamp, PriceOHLCV.close).where(PriceOHLCV.symbol == symbol1, PriceOHLCV.timeframe == 'D1')
        q2 = select(PriceOHLCV.timestamp, PriceOHLCV.close).where(PriceOHLCV.symbol == symbol2, PriceOHLCV.timeframe == 'D1')
        if as_of is not None:
            q1 = q1.where(PriceOHLCV.timestamp <= as_of)
            q2 = q2.where(PriceOHLCV.timestamp <= as_of)

        s1_rows = (await session.execute(q1.order_by(PriceOHLCV.timestamp.desc()).limit(lookback_bars))).all()
        s2_rows = (await session.execute(q2.order_by(PriceOHLCV.timestamp.desc()).limit(lookback_bars))).all()
        if len(s1_rows) < 20 or len(s2_rows) < 20:
            return (_static_fallback(symbol1, symbol2), 'static_fallback_insufficient_history')
        df1 = pd.DataFrame(s1_rows, columns=['timestamp', 'close1'])
        df2 = pd.DataFrame(s2_rows, columns=['timestamp', 'close2'])
        df1['date'] = pd.to_datetime(df1['timestamp']).dt.date
        df2['date'] = pd.to_datetime(df2['timestamp']).dt.date
        df = df1.set_index('date')[['close1']].join(df2.set_index('date')[['close2']], how='inner').sort_index()
        if len(df) < 20:
            return (_static_fallback(symbol1, symbol2), 'static_fallback_insufficient_overlap')
        df['ret1'] = df['close1'].pct_change()
        df['ret2'] = df['close2'].pct_change()
        
        valid_df = df.dropna(subset=['ret1', 'ret2'])
        if len(valid_df) < 15:
            return (_static_fallback(symbol1, symbol2), 'static_fallback_insufficient_returns')

        if method == "ewma":
            # Exponentially Weighted Moving Average Correlation (RiskMetrics lambda ~ 0.94)
            ewm_corr_series = valid_df['ret1'].ewm(span=span, min_periods=15).corr(valid_df['ret2'])
            corr = ewm_corr_series.iloc[-1] if not ewm_corr_series.empty else float('nan')
            source = 'dynamic_ewma'
            if pd.isna(corr):
                corr = valid_df['ret1'].corr(valid_df['ret2'])
                source = 'dynamic_rolling'
        else:
            corr = valid_df['ret1'].corr(valid_df['ret2'])
            source = 'dynamic_rolling'

        if pd.isna(corr):
            return (_static_fallback(symbol1, symbol2), 'static_fallback_nan')
        return (float(corr), source)
    except Exception as e:
        logger.warning(f'Dynamic correlation failed ({symbol1}/{symbol2}): {e}. Using static fallback.')
        return (_static_fallback(symbol1, symbol2), 'static_fallback_error')
