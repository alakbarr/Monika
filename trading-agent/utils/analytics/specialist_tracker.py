import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import AssetAnalysis, PaperTradeRecord
from utils.constants import MARKET_OUTCOME_EXIT_REASONS

logger = logging.getLogger('TradingAgent.SpecialistTracker')

async def compute_specialist_reliability(session: AsyncSession, days_back: int = 45) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    rows = (await session.execute(
        select(AssetAnalysis, PaperTradeRecord)
        .join(PaperTradeRecord, AssetAnalysis.id == PaperTradeRecord.analysis_id)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.closed_at >= since)
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
        .where(AssetAnalysis.specialist_biases_json.isnot(None))
    )).all()

    stats = {'technical': {'correct': 0, 'total': 0}, 'sentiment': {'correct': 0, 'total': 0}, 'macro': {'correct': 0, 'total': 0}}
    for analysis, trade in rows:
        try:
            data = json.loads(analysis.specialist_biases_json)
            biases = data.get('biases', {})
        except Exception:
            continue
        from utils.analytics.edge_tracker import is_trade_win
        was_win = is_trade_win(trade)
        final_direction = analysis.decision
        for spec_name, bias in biases.items():
            if spec_name not in stats or bias not in ('bullish', 'bearish'):
                continue
            agreed = (bias == 'bullish' and final_direction == 'buy') or (bias == 'bearish' and final_direction == 'sell')
            stats[spec_name]['total'] += 1
            if (agreed and was_win) or (not agreed and not was_win):
                stats[spec_name]['correct'] += 1

    out = {}
    for spec_name, d in stats.items():
        if d['total'] >= 8:
            acc = d['correct'] / d['total']
            weight_base = acc * 1.4
            
            chronically_unreliable = d['total'] >= 20 and acc < 0.40
            
            if d['total'] >= 15 and acc < 0.45:
                weight_base *= 0.5
            
            if chronically_unreliable:
                weight_base = min(weight_base, 0.15)  # hard-floor pengaruh
                
            ceiling = 1.3 if (d['total'] >= 15 and acc >= 0.65) else 1.0
            out[spec_name] = {
                'accuracy_pct': round(acc * 100, 1),
                'total': d['total'],
                'trust_weight': max(0.05 if chronically_unreliable else 0.1, min(ceiling, weight_base)),
                'chronically_unreliable': chronically_unreliable,
            }
    return {'days_analyzed': days_back, 'specialists': out, 'generated_at': datetime.now(timezone.utc).isoformat()}

async def check_specialist_model_quality(session: AsyncSession, settings: dict) -> dict:
    """Rekomendasi human-in-the-loop (bukan auto-switch) untuk upgrade model specialist
    jika akurasinya konsisten rendah dalam jangka panjang."""
    reliability = await compute_specialist_reliability(session, days_back=60)
    specialists = reliability.get('specialists', {})
    alerts = []
    for name, data in specialists.items():
        if data['total'] >= 20 and data['accuracy_pct'] < 45.0:
            role = f'specialist_{name}'
            model_name = settings.get('llm', {}).get('task_roles', {}).get(role, {}).get('primary', 'unknown')
            alerts.append(
                f"Specialist '{name}' (model={model_name}) akurasi={data['accuracy_pct']}% "
                f"dari {data['total']} trades  di bawah ambang 45%. Pertimbangkan upgrade "
                f"llm.task_roles.{role}.primary ke model lebih kuat."
            )
    return {'alerts': alerts, 'specialists': specialists}
