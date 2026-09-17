import logging
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PaperTradeRecord, AssetAnalysis, SystemConfig

logger = logging.getLogger('TradingAgent.TradeAutopsy')

async def run_trade_autopsy(session: AsyncSession, trade: PaperTradeRecord) -> dict:
    """
    Analyze why a trade succeeded or failed.
    Returns dict with patterns detected.
    """
    if not trade.analysis_id:
        return {}
    
    analysis = (await session.execute(
        select(AssetAnalysis).where(AssetAnalysis.id == trade.analysis_id)
    )).scalar_one_or_none()
    
    if not analysis:
        return {}
    
    patterns = []
    from utils.analytics.edge_tracker import is_trade_win
    was_loss = not is_trade_win(trade)
    
    # Pattern 1: Was trade entered during high-VIX?
    from database.models import VIXData
    vix_at_entry = (await session.execute(
        select(VIXData)
        .where(VIXData.date <= trade.opened_at)
        .order_by(VIXData.date.desc())
        .limit(1)
    )).scalar_one_or_none()
    
    if vix_at_entry and vix_at_entry.close > 22 and was_loss:
        patterns.append({
            'pattern': 'HIGH_VIX_LOSS',
            'detail': f'VIX was {vix_at_entry.close:.1f} at entry → loss. Consider blocking entries when VIX > 22.',
            'severity': 'high'
        })
    
    # Pattern 2: Was brief close to expiry?
    from database.models import FundamentalBrief
    if analysis.brief_id:
        brief = await session.get(FundamentalBrief, analysis.brief_id)
        if brief and brief.generated_at:
            brief_age_at_entry = (trade.opened_at - brief.generated_at).total_seconds() / 3600
            if brief_age_at_entry > 4.0 and was_loss:
                patterns.append({
                    'pattern': 'STALE_BRIEF_LOSS',
                    'detail': f'Brief was {brief_age_at_entry:.1f}h old at trade entry → loss.',
                    'severity': 'medium'
                })
    
    # Pattern 3: Short holding time on loss (stop hunted?)
    if trade.holding_hours and trade.holding_hours < 2.0 and was_loss:
        patterns.append({
            'pattern': 'QUICK_SL_HIT',
            'detail': f'SL hit in {trade.holding_hours:.1f}h. Possible stop hunt or SL too tight.',
            'severity': 'high'
        })
    
    # Pattern 4: Session at entry
    if trade.opened_at:
        hour = trade.opened_at.hour
        if 21 <= hour <= 23 and was_loss:
            patterns.append({
                'pattern': 'OFF_PEAK_LOSS',
                'detail': f'Trade entered during off-peak hours ({hour}:00 UTC) → loss.',
                'severity': 'medium'
            })
    
    # Pattern 5: Confluence factors present for losses
    if analysis.confluence_factors_json and was_loss:
        factors = json.loads(analysis.confluence_factors_json)
        # Track which factors were present in losing trades
        await _update_factor_failure_stats(session, factors, trade.symbol)
    
    if patterns:
        # Save patterns to SystemConfig for future reference
        key = f'autopsy_{trade.symbol}_{trade.id}'
        await SystemConfig.upsert(
            session,
            key=key,
            value=json.dumps({
                'trade_id': trade.id,
                'patterns': patterns,
                'outcome': trade.exit_reason,
                'pnl_pct': trade.pnl_pct,
                'analyzed_at': datetime.now(timezone.utc).isoformat()
            })
        )
        await session.commit()
        
        logger.info(f'[AUTOPSY] {trade.symbol} {trade.exit_reason}: {len(patterns)} patterns detected')
    
    return {'patterns': patterns, 'trade_id': trade.id}

async def _update_factor_failure_stats(session: AsyncSession, factors: list, symbol: str):
    """Track which confluence factors consistently appear in losing trades."""
    key = 'factor_failure_stats'
    cfg = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == key)
    )).scalar_one_or_none()
    
    stats = {}
    if cfg and cfg.value:
        try:
            stats = json.loads(cfg.value)
        except Exception:
            pass
    
    for factor in factors:
        composite_key = f'{symbol}_{factor}'
        if composite_key not in stats:
            stats[composite_key] = {'failures': 0, 'total': 0}
        stats[composite_key]['total'] += 1
        stats[composite_key]['failures'] += 1  # Dipanggil hanya untuk losses
    
    if cfg:
        cfg.value = json.dumps(stats)
    else:
        session.add(SystemConfig(key=key, value=json.dumps(stats)))

async def summarize_recent_patterns(session: AsyncSession, hours_back: int = 24) -> dict:
    """
    Summarize recent failure patterns from trade autopsy records.
    Returns dict with has_critical_patterns bool and summary string.
    """
    from datetime import datetime, timezone, timedelta
    from database.models import SystemConfig
    from sqlalchemy import select
    
    since = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    has_critical = False
    patterns_found = []
    
    try:
        # Fetch recent autopsy records
        recent_autopsies = (await session.execute(
            select(SystemConfig).where(
                SystemConfig.key.like('autopsy_%')
            ).order_by(SystemConfig.updated_at.desc()).limit(50)
        )).scalars().all()
        
        for cfg in recent_autopsies:
            if not cfg.value:
                continue
            try:
                data = json.loads(cfg.value)
                analyzed_at_str = data.get('analyzed_at', '')
                if not analyzed_at_str:
                    continue
                analyzed_at = datetime.fromisoformat(analyzed_at_str)
                if analyzed_at.tzinfo is None:
                    analyzed_at = analyzed_at.replace(tzinfo=timezone.utc)
                if analyzed_at < since:
                    continue
                
                patterns = data.get('patterns', [])
                for p in patterns:
                    if p.get('severity') == 'high':
                        has_critical = True
                        patterns_found.append(f"{p.get('pattern', 'UNKNOWN')}: {p.get('detail', '')[:100]}")
            except Exception:
                continue
    except Exception as e:
        logger.debug(f'summarize_recent_patterns failed (non-fatal): {e}')
    
    return {
        'has_critical_patterns': has_critical,
        'pattern_count': len(patterns_found),
        'summary': '; '.join(patterns_found[:3]) if patterns_found else 'No critical patterns detected'
    }
