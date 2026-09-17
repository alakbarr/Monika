"""
CDS-Outcome Correlation Tracker
Validates whether our CDS metric is actually predictive of hallucination/poor outcomes.
Per research: validates SSVP effectiveness empirically.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger('TradingAgent.CDSOutcomeTracker')


async def compute_cds_outcome_correlation(
    session: AsyncSession,
    days_back: int = 60
) -> dict:
    """
    Analyze whether high CDS at analysis time correlates with poor trade outcomes.
    
    This validates our CDS implementation empirically, similar to the paper's
    controlled experiments.
    """
    from database.models import AssetAnalysis, PaperTradeRecord
    from utils.constants import MARKET_OUTCOME_EXIT_REASONS

    since = datetime.now(timezone.utc) - timedelta(days=days_back)

    records = (await session.execute(
        select(AssetAnalysis, PaperTradeRecord)
        .join(PaperTradeRecord, AssetAnalysis.id == PaperTradeRecord.analysis_id)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.closed_at >= since)
        .where(PaperTradeRecord.exit_reason.in_(MARKET_OUTCOME_EXIT_REASONS))
        .where(AssetAnalysis.ssvp_cds_score_at_analysis.isnot(None))
    )).all()

    if len(records) < 10:
        return {
            'status': 'insufficient_data',
            'count': len(records),
            'min_required': 10
        }

    # Split by CDS threshold
    high_cds = []   # CDS >= 0.30
    low_cds = []    # CDS < 0.30

    for analysis, trade in records:
        cds = analysis.ssvp_cds_score_at_analysis
        is_win = (trade.pnl_pct or 0) > 0 or trade.exit_reason in ('tp_hit', 'trailing_sl', 'take_profit')
        pnl = trade.pnl_pct or 0

        entry = {'cds': cds, 'is_win': is_win, 'pnl': pnl, 'symbol': analysis.symbol}

        if cds >= 0.30:
            high_cds.append(entry)
        else:
            low_cds.append(entry)

    # Compute win rates
    high_cds_wr = (
        sum(1 for r in high_cds if r['is_win']) / len(high_cds)
        if high_cds else None
    )
    low_cds_wr = (
        sum(1 for r in low_cds if r['is_win']) / len(low_cds)
        if low_cds else None
    )

    is_predictive = (
        high_cds_wr is not None and
        low_cds_wr is not None and
        low_cds_wr > high_cds_wr + 0.05  # At least 5% WR difference
    )

    result = {
        'status': 'analyzed',
        'days_back': days_back,
        'total_records': len(records),
        'high_cds': {
            'count': len(high_cds),
            'win_rate': round(high_cds_wr * 100, 1) if high_cds_wr is not None else None,
            'avg_pnl': round(sum(r['pnl'] for r in high_cds) / len(high_cds), 3) if high_cds else None,
        },
        'low_cds': {
            'count': len(low_cds),
            'win_rate': round(low_cds_wr * 100, 1) if low_cds_wr is not None else None,
            'avg_pnl': round(sum(r['pnl'] for r in low_cds) / len(low_cds), 3) if low_cds else None,
        },
        'cds_is_predictive': is_predictive,
        'recommendation': (
            "CDS is PREDICTIVE — keep current thresholds" if is_predictive
            else "CDS not yet predictive — needs more data or threshold calibration"
        ),
        'generated_at': datetime.now(timezone.utc).isoformat()
    }

    logger.info(
        f"[CDSOutcomeTracker] high_cds_wr={result['high_cds']['win_rate']}% "
        f"low_cds_wr={result['low_cds']['win_rate']}% "
        f"predictive={is_predictive}"
    )

    return result


async def auto_calibrate_cds_threshold(
    session: AsyncSession,
    current_threshold: float = 0.30,
    min_trades: int = 30
) -> tuple[float, str]:
    """
    Auto-calibrate CDS threshold based on empirical outcome correlation.
    
    Returns: (recommended_threshold, explanation)
    """
    correlation = await compute_cds_outcome_correlation(session)

    if correlation.get('status') == 'insufficient_data':
        return current_threshold, f"Insufficient data ({correlation.get('count', 0)}/{min_trades} trades)"

    if not correlation['cds_is_predictive']:
        return current_threshold, "CDS not yet predictive — maintaining current threshold"

    # Try to find better threshold
    # For now, validate current threshold is reasonable
    high_wr = correlation['high_cds']['win_rate']
    low_wr = correlation['low_cds']['win_rate']

    if high_wr is not None and low_wr is not None:
        wr_gap = low_wr - high_wr
        if wr_gap < 3:
            # Not enough separation — threshold may be too high (catching too few events)
            return max(current_threshold - 0.05, 0.15), f"WR gap only {wr_gap:.1f}% — consider lowering threshold"
        elif wr_gap > 20:
            # Very strong separation — threshold may be too low (too many false positives)
            return min(current_threshold + 0.05, 0.50), f"WR gap {wr_gap:.1f}% is very large — consider raising threshold"
        return current_threshold, f"CDS predictive with WR gap {wr_gap:.1f}% — threshold optimal"

    return current_threshold, "Insufficient data for CDS threshold calibration"
