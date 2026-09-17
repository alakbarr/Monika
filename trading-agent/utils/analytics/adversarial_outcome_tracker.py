import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger('TradingAgent.AdversarialOutcomeTracker')


async def compute_adversarial_check_correlation(session: AsyncSession, days_back: int = 60) -> dict:
    """Mengecek apakah verdict adversarial_check (approve/hard_block/recommend_block)
    benar-benar berkorelasi dengan outcome trade — untuk kalibrasi alert_on_extreme_only."""
    from database.models import SystemConfig, PaperTradeRecord
    from utils.analytics.edge_tracker import is_trade_win
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    rows = (
        await session.execute(
            select(SystemConfig)
            .where(SystemConfig.key.like('adversarial_outcome_%'))
            .order_by(SystemConfig.key.desc())
        )
    ).scalars().all()
    flagged_wins, flagged_total, clean_wins, clean_total = 0, 0, 0, 0
    for cfg in rows:
        try:
            if not cfg.value:
                continue
            data = json.loads(cfg.value)
            trade = (
                await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.analysis_id == data['analysis_id'])
                    .where(PaperTradeRecord.status == 'closed')
                    .where(PaperTradeRecord.closed_at >= since)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not trade:
                continue
            is_win = is_trade_win(trade)
            if data.get('recommend_block') or data.get('hard_block'):
                flagged_total += 1
                flagged_wins += int(is_win)
            else:
                clean_total += 1
                clean_wins += int(is_win)
        except Exception:
            continue
    if flagged_total < 5 or clean_total < 5:
        return {'status': 'insufficient_data'}
    flagged_wr = flagged_wins / flagged_total * 100
    clean_wr = clean_wins / clean_total * 100
    return {
        'status': 'analyzed', 'flagged_win_rate': round(flagged_wr, 1), 'flagged_total': flagged_total,
        'clean_win_rate': round(clean_wr, 1), 'clean_total': clean_total,
        'is_predictive': clean_wr > flagged_wr + 5,
        'recommendation': (
            'Adversarial check PREDICTIVE — pertahankan alert_on_extreme_only=True atau perketat.'
            if clean_wr > flagged_wr + 5 else
            'Adversarial check belum terbukti predictive — tinjau ulang system prompt / deterministic flags.'
        ),
    }
