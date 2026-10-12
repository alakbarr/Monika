import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger('TradingAgent.ContextSnapshot')


async def compute_context_snapshot_id(session: AsyncSession) -> tuple[str, dict]:
    """
    Compute deterministic snapshot ID dari current context state.
    
    ID ini unik per "state of the world" — jika brief berubah atau
    DXY berubah regime, ID akan berbeda.
    
    Returns:
        (snapshot_id: str, snapshot_metadata: dict)
    """
    from database.models import FundamentalBrief, VIXData, DXYData
    
    components = {}
    
    # Brief ID dan timestamp
    brief = (await session.execute(
        select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
    )).scalar_one_or_none()
    
    if brief:
        components['brief_id'] = brief.id
        components['brief_ts'] = brief.generated_at.isoformat() if brief.generated_at else None
        if brief.structured_json:
            try:
                structured = json.loads(brief.structured_json)
                components['currency_bias'] = structured.get('currency_bias', {})
                components['risk_sentiment'] = structured.get('risk_sentiment', 'mixed')
            except Exception:
                pass
    
    # VIX regime (bukan exact value, tapi regime bucket)
    vix = (await session.execute(
        select(VIXData).order_by(VIXData.date.desc()).limit(1)
    )).scalar_one_or_none()
    
    if vix:
        if vix.close < 15:
            vix_regime = 'low'
        elif vix.close < 20:
            vix_regime = 'moderate'
        elif vix.close < 28:
            vix_regime = 'elevated'
        else:
            vix_regime = 'high'
        components['vix_regime'] = vix_regime
        components['vix_date'] = vix.date.strftime('%Y-%m-%d') if vix.date else None
    
    # DXY trend
    dxy_rows = (await session.execute(
        select(DXYData).order_by(DXYData.date.desc()).limit(3)
    )).scalars().all()
    
    if len(dxy_rows) >= 2:
        dxy_trend = 'up' if dxy_rows[0].close > dxy_rows[-1].close else 'down'
        components['dxy_trend'] = dxy_trend
    
    # Compute hash
    snapshot_str = json.dumps(components, sort_keys=True)
    snapshot_id = hashlib.sha256(snapshot_str.encode()).hexdigest()[:16]
    
    return snapshot_id, components


async def detect_context_version_split(session: AsyncSession, cycle_start: datetime) -> Optional[str]:
    """
    Deteksi apakah dalam satu siklus ada agen yang menggunakan context version berbeda.
    
    Ini terjadi ketika Stage 1 re-run di tengah Stage 2 yang sedang berjalan.
    
    Returns:
        Warning message jika ditemukan split, None jika konsisten.
    """
    from database.models import AssetAnalysis
    
    # Ambil semua analisis dari siklus ini
    analyses = (await session.execute(
        select(AssetAnalysis)
        .where(AssetAnalysis.generated_at >= cycle_start)
        .where(AssetAnalysis.context_snapshot_id.is_not(None))
    )).scalars().all()
    
    if len(analyses) < 2:
        return None
    
    snapshot_ids = set(a.context_snapshot_id for a in analyses)
    
    if len(snapshot_ids) > 1:
        return (
            f"CONTEXT VERSION SPLIT DETECTED: {len(analyses)} analyses in this cycle used "
            f"{len(snapshot_ids)} different context versions: {snapshot_ids}. "
            f"This means Stage 1 re-ran mid-cycle. Results from different versions may contradict."
        )
    
    return None
