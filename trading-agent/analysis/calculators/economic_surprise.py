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
        
        # Indicator-specific surprise calculation
        name_lower = (event.event_name or "").lower()
        diff = actual - forecast
        
        # 1. Central bank interest rate decisions (Fed Funds, ECB, BOE, BOJ, RBA)
        if any(k in name_lower for k in ("interest rate", "rate decision", "fed funds", "refinancing rate", "cash rate", "policy rate")):
            # 15 bps (0.15%) difference is massive -> normalize so 15 bps = 20.0 surprise score
            surprise = round((diff / 0.15) * 20.0, 4)
        # 2. CPI / PCE inflation
        elif any(k in name_lower for k in ("cpi", "pce", "inflation", "ppi")):
            # 0.20% difference is a major macro surprise -> normalize so 0.20% = 20.0 score
            surprise = round((diff / 0.20) * 20.0, 4)
        # 3. NFP / Employment Change
        elif any(k in name_lower for k in ("nonfarm", "payroll", "employment change", "nfp")):
            # 30,000 difference is major -> normalize so 30K = 20.0 score
            scale = 30_000.0 if (abs(actual) > 1000 or abs(forecast) > 1000) else 30.0
            surprise = round((diff / scale) * 20.0, 4)
        # 4. Unemployment Rate
        elif any(k in name_lower for k in ("unemployment rate", "jobless rate")):
            # Inverted: higher unemployment is dovish (-), 0.20% = 20.0 score
            surprise = round((-diff / 0.20) * 20.0, 4)
        # 5. PMI / ISM / Business & Consumer Sentiment Surveys (Index scale centered around 50 or 100)
        elif any(k in name_lower for k in ("pmi", "ism", "sentiment", "ifo", "zew", "chicago pm", "consumer confidence")):
            # 1.5 index point difference is a major macro surprise -> normalize so 1.5 = 20.0 score
            surprise = round((diff / 1.50) * 20.0, 4)
        # 6. GDP / Retail Sales / Industrial Production (Growth rates)
        elif any(k in name_lower for k in ("gdp", "retail sales", "industrial production", "factory orders")):
            # 0.30% growth rate surprise is major -> normalize so 0.30% = 20.0 score
            surprise = round((diff / 0.30) * 20.0, 4)
        else:
            # Normalisasi persentase deviasi dari forecast untuk metrik umum
            if abs(forecast) > 0.001:
                surprise = ((actual - forecast) / abs(forecast)) * 100.0
            else:
                surprise = actual - forecast

            # Inversi arah untuk metrik pengangguran/klaim lainnya
            if any(kw in name_lower for kw in _INVERTED_METRIC_KEYWORDS):
                surprise = -surprise
        
        # Clamp ke rentang batas wajar [-300.0, +300.0] untuk mencegah anomali angka tak terhingga
        surprise = max(-300.0, min(300.0, surprise))
        event.surprise_score = round(surprise, 4)
        updated += 1
    
    if updated:
        await session.commit()
    
    return updated


async def compute_cesi_index(
    session: AsyncSession,
    currency: str,
    window_days: int = 90,
    half_life_days: float = 30.0
) -> dict:
    """
    Menghitung Citigroup-style Economic Surprise Index (CESI) untuk suatu mata uang
    menggunakan pembobotan peluruhan eksponensial (exponential decay) selama window_days (default: 90 hari).
    """
    from datetime import datetime, timezone, timedelta
    import utils.clock as clock
    import math

    curr = currency.strip().upper()
    now = clock.now()
    cutoff = now - timedelta(days=window_days)

    events = (await session.execute(
        select(EconomicCalendar)
        .where(EconomicCalendar.currency == curr)
        .where(EconomicCalendar.surprise_score != None)
        .where(EconomicCalendar.event_time >= cutoff)
        .order_by(EconomicCalendar.event_time.asc())
    )).scalars().all()

    if not events:
        return {
            "currency": curr,
            "window_days": window_days,
            "cesi_score": 0.0,
            "event_count": 0,
            "trend": "NEUTRAL",
            "description": f"No scored economic events in the last {window_days} days."
        }

    decay_lambda = math.log(2) / max(1.0, half_life_days)
    weighted_sum = 0.0
    total_weights = 0.0

    for ev in events:
        ev_time = ev.event_time.replace(tzinfo=timezone.utc) if ev.event_time.tzinfo is None else ev.event_time
        age_days = (now - ev_time).total_seconds() / 86400.0
        weight = math.exp(-decay_lambda * max(0.0, age_days))

        # Weight higher impact events more heavily
        impact = str(ev.impact or "").upper()
        impact_multiplier = 2.0 if impact == "HIGH" else (1.0 if impact == "MEDIUM" else 0.5)
        effective_weight = weight * impact_multiplier

        score = float(ev.surprise_score or 0.0)
        weighted_sum += score * effective_weight
        total_weights += effective_weight

    cesi = round(weighted_sum / max(1e-6, total_weights), 2) if total_weights > 0 else 0.0

    if cesi >= 15.0:
        trend = "STRONG_POSITIVE_MOMENTUM"
    elif cesi >= 5.0:
        trend = "MODERATE_POSITIVE"
    elif cesi <= -15.0:
        trend = "STRONG_NEGATIVE_MOMENTUM"
    elif cesi <= -5.0:
        trend = "MODERATE_NEGATIVE"
    else:
        trend = "NEUTRAL"

    return {
        "currency": curr,
        "window_days": window_days,
        "cesi_score": cesi,
        "event_count": len(events),
        "trend": trend,
        "description": f"CESI for {curr} over {window_days}d is {cesi:+.2f} ({trend}, {len(events)} events)."
    }

