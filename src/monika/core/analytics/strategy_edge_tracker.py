from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from database.models import AssetAnalysis, PaperTradeRecord, SystemConfig
from utils.constants import MARKET_OUTCOME_EXIT_REASONS

async def compute_strategy_pair_stats(session, settings: dict) -> dict:
    """Per (strategy_id, symbol): trades, win_rate, profit_factor, expectancy_R."""
    days_back = int(settings.get('trading', {}).get('edge_strategy', {}).get('stats_tracker', {}).get('review_days_back', 60))
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    rows = (await session.execute(
        select(PaperTradeRecord, AssetAnalysis)
        .join(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(AssetAnalysis.decision_source == 'edge_registry')
        .where(PaperTradeRecord.closed_at >= since)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
    )).all()
    stats: dict[tuple[str, str], dict] = {}
    for trade, analysis in rows:
        key = (analysis.source_strategy_id or 'unknown', analysis.symbol)
        s = stats.setdefault(key, {'n': 0, 'wins': 0, 'gross_win': 0.0, 'gross_loss': 0.0})
        s['n'] += 1
        pnl = trade.pnl_pct or 0.0
        if pnl > 0:
            s['wins'] += 1
            s['gross_win'] += pnl
        else:
            s['gross_loss'] += abs(pnl)
    out = {}
    for (strat, sym), s in stats.items():
        pf = (s['gross_win'] / s['gross_loss']) if s['gross_loss'] > 0 else float('inf') if s['gross_win'] > 0 else 0.0
        out[f'{strat}_{sym}'] = {
            'strategy_id': strat, 'symbol': sym, 'trades': s['n'],
            'win_rate_pct': round(s['wins'] / s['n'] * 100, 1) if s['n'] else 0.0,
            'profit_factor': round(pf, 2),
        }
    return out

async def apply_disable_flags(session, settings: dict) -> list[str]:
    """Writes SystemConfig 'strategy_disabled_{strategy_id}_{symbol}'='true' for underperformers.
    Returns list of 'strategy_symbol' pairs disabled this run. Also re-enables recovered pairs."""
    st_cfg = settings.get('trading', {}).get('edge_strategy', {}).get('stats_tracker', {})
    min_sample = int(st_cfg.get('min_sample_size', 20))
    min_profit_factor = float(st_cfg.get('min_profit_factor', 1.0))
    stats = await compute_strategy_pair_stats(session, settings)
    disabled = []
    for key, s in stats.items():
        cfg_key = f"strategy_disabled_{s['strategy_id']}_{s['symbol']}"
        cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == cfg_key))).scalar_one_or_none()
        should_disable = s['trades'] >= min_sample and s['profit_factor'] < min_profit_factor
        val = 'true' if should_disable else 'false'
        if cfg:
            cfg.value = val
        else:
            session.add(SystemConfig(key=cfg_key, value=val))
        if should_disable:
            disabled.append(f"{s['strategy_id']}_{s['symbol']}")
    await session.commit()
    return disabled
