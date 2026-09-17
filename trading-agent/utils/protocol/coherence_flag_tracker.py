import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PaperTradeRecord, AssetAnalysis
from utils.constants import MARKET_OUTCOME_EXIT_REASONS

logger = logging.getLogger('TradingAgent.CoherenceFlagTracker')

async def compute_coherence_override_impact(session: AsyncSession, days_back: int = 30) -> dict:
    """Bandingkan win rate trade yang RASIONALE-nya mengandung
    '[SYSTEM COHERENCE FLAG' (Stage2 melawan bias Stage1) vs yang tidak."""
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    records = (await session.execute(
        select(PaperTradeRecord, AssetAnalysis)
        .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(PaperTradeRecord.closed_at >= since)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
    )).all()
    if not records:
        return {'insufficient_data': True}

    flagged, clean = [], []
    for record, analysis in records:
        rationale = (analysis.rationale or '') if analysis else ''
        if 'SYSTEM COHERENCE FLAG' in rationale:
            flagged.append(record)
        else:
            clean.append(record)

    def _stats(lst):
        if not lst:
            return {'total': 0, 'win_rate': 0.0}
        wins = sum(1 for r in lst if (r.pnl_pct or 0) > 0)
        return {'total': len(lst), 'win_rate': round(wins / len(lst) * 100, 1)}

    return {
        'days_analyzed': days_back,
        'technical_override_macro': _stats(flagged),
        'macro_aligned': _stats(clean),
        'recommendation': (
            'Technical-override-macro terbukti UNDERPERFORM — pertimbangkan menaikkan bar untuk override.'
            if flagged and clean and _stats(flagged)['win_rate'] < _stats(clean)['win_rate'] - 8
            else 'Belum ada sinyal jelas / override performa sebanding.'
        ),
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
