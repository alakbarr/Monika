# ==============================================================================
# File: analysis/economic_surprise.py
# ==============================================================================

"""
Kalkulator Economic Surprise.
Menghitung selisih persentase antara nilai aktual dan ekspektasi (forecast).
"""
import logging
import re
from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import EconomicCalendar

logger = logging.getLogger("TradingAgent.EconomicSurprise")


def _parse_numeric(val: Optional[str]) -> Optional[float]:
    """Mem-parsing string nilai ekonomi ('1.5%', '10K', '2M', dll) menjadi float."""
    if not val or val in ("-", "--", "N/A", ""):
        return None
    try:
        clean = re.sub(r'[%,]', '', str(val).strip())
        multiplier = 1
        if clean.upper().endswith('K'):
            multiplier = 1_000; clean = clean[:-1]
        elif clean.upper().endswith('M'):
            multiplier = 1_000_000; clean = clean[:-1]
        elif clean.upper().endswith('B'):
            multiplier = 1_000_000_000; clean = clean[:-1]
        return float(clean) * multiplier
    except (ValueError, TypeError):
        return None


_INVERTED_METRIC_KEYWORDS = (
    "unemployment", "jobless claims", "initial claims", "continuing claims",
    "claimant count", "unemployment rate"
)

async def compute_surprise_scores(session: AsyncSession) -> int:
    """
    Menghitung dan memperbarui `surprise_score` untuk event kalender ekonomi.
    Hanya memproses event dengan nilai aktual/forecast yang belum diskor.
    Membalikkan tanda (inverted sign) untuk metrik pengangguran/klaim agar skor positif
    konsisten mencerminkan dorongan hawkish/penguatan nilai mata uang.
    """
    events = (await session.execute(
        select(EconomicCalendar)
        .where(EconomicCalendar.actual != None)
        .where(EconomicCalendar.forecast != None)
        .where(EconomicCalendar.surprise_score == None)
    )).scalars().all()
    
    updated = 0
    for event in events:
        actual = _parse_numeric(event.actual)
        forecast = _parse_numeric(event.forecast)
        
        if actual is None or forecast is None:
            continue
        
        # Normalisasi: persentase deviasi dari forecast
        if abs(forecast) > 0.001:
            surprise = round(((actual - forecast) / abs(forecast)) * 100.0, 4)
        else:
            surprise = round(actual - forecast, 4)

        # Inversi arah untuk metrik pengangguran/klaim
        # (kenaikan pengangguran adalah sinyal dovish/pelemah mata uang)
        name_lower = (event.event_name or "").lower()
        if any(kw in name_lower for kw in _INVERTED_METRIC_KEYWORDS):
            surprise = -surprise
        
        event.surprise_score = round(surprise, 4)
        updated += 1
    
    if updated:
        await session.commit()
    
    return updated
