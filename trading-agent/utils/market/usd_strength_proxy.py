import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import DXYData, PriceOHLCV
logger = logging.getLogger(__name__)

# Bobot ICE DXY asli: EUR 57.6%, JPY 13.6%, GBP 11.9%, CAD 9.1%, SEK 4.2%, CHF 3.6%.
# CAD/SEK/CHF tidak tersedia di asset_universe sistem ini, sehingga bobot
# dinormalisasi ulang hanya atas EUR+JPY+GBP (~83% dari bobot DXY asli).
_DXY_PROXY_WEIGHTS = {'EURUSD': 0.686, 'USDJPY': 0.162, 'GBPUSD': 0.152}
# EURUSD/GBPUSD: USD adalah QUOTE currency -> pair naik = USD LEMAH (invert).
# USDJPY: USD adalah BASE currency -> pair naik = USD KUAT (tidak di-invert).
_DXY_PROXY_INVERT = {'EURUSD': True, 'GBPUSD': True, 'USDJPY': False}


from datetime import datetime
from typing import Optional

async def _get_pct_change(session: AsyncSession, symbol: str, timeframe: str, lookback_bars: int, as_of: Optional[datetime] = None) -> float | None:
    stmt = (
        select(PriceOHLCV.close)
        .where(PriceOHLCV.symbol == symbol)
        .where(PriceOHLCV.timeframe == timeframe)
    )
    if as_of:
        stmt = stmt.where(PriceOHLCV.timestamp <= as_of)
    stmt = stmt.order_by(PriceOHLCV.timestamp.desc()).limit(lookback_bars)
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) < 2:
        return None
    recent = rows[0]
    old = rows[-1]
    if not old:
        return None
    return (recent - old) / old * 100


async def compute_usd_strength_proxy(session: AsyncSession, lookback_bars: int = 20, timeframe: str = 'H4', as_of: Optional[datetime] = None) -> dict:
    """
    Menghitung proxy kekuatan USD dari basket EURUSD/GBPUSD/USDJPY pada
    resolusi H4/H1 (sesuai `timeframe` yang diminta caller), karena tabel
    DXYData di sistem ini hanya diperbarui pada resolusi HARIAN (feed
    yfinance D1) sehingga terlalu basi untuk penilaian priced-in/momentum
    intraday di Stage 1 dan Stage 2.

    FIX (P0): implementasi lama mengabaikan parameter `timeframe` sepenuhnya
    dan hanya membaca DXYData harian, meski dinamai dan dipanggil sebagai
    "weighted proxy" H4. Fungsi ini sekarang benar-benar menghitung basket
    berbobot dari data multi-pair pada timeframe yang diminta, dengan
    fallback ke DXYData harian hanya jika data intraday tidak cukup.
    """
    try:
        weighted_change = 0.0
        total_weight_used = 0.0
        components = {}
        for symbol, weight in _DXY_PROXY_WEIGHTS.items():
            pct = await _get_pct_change(session, symbol, timeframe, lookback_bars, as_of=as_of)
            if pct is None:
                continue
            signed_pct = -pct if _DXY_PROXY_INVERT[symbol] else pct
            weighted_change += signed_pct * weight
            total_weight_used += weight
            components[symbol] = round(pct, 4)
        if total_weight_used >= 0.5:
            normalized_change = weighted_change / total_weight_used
            direction = 'strengthening' if normalized_change > 0 else 'weakening' if normalized_change < 0 else 'flat'
            return {
                'weighted_usd_change_pct': round(normalized_change, 4),
                'direction': direction,
                'method': 'basket_proxy',
                'timeframe': timeframe,
                'lookback_bars': lookback_bars,
                'components_pct_change': components,
                'basket_weight_coverage': round(total_weight_used, 3),
            }
        logger.warning(f'USD strength proxy: cakupan basket intraday tidak cukup (coverage={total_weight_used:.2f}), fallback ke DXYData harian.')
    except Exception as e:
        logger.error(f'Error menghitung basket USD strength proxy: {e}. Fallback ke DXYData harian.')

    try:
        rows = (await session.execute(select(DXYData).order_by(DXYData.date.desc()).limit(lookback_bars))).scalars().all()
        if not rows or len(rows) < 2:
            return {'weighted_usd_change_pct': 0.0, 'direction': 'flat', 'method': 'dxy_daily_fallback_insufficient_data'}
        recent = rows[0].close
        old = rows[-1].close
        change = (recent - old) / old * 100
        return {'weighted_usd_change_pct': round(change, 4), 'direction': 'strengthening' if change > 0 else 'weakening', 'method': 'dxy_daily_fallback'}
    except Exception as e:
        logger.error(f'Error menghitung DXY daily fallback: {e}')
        return {'error': str(e), 'weighted_usd_change_pct': 0.0, 'direction': 'unknown', 'method': 'error'}
