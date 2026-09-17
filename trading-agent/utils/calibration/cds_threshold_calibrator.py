"""
CDS Threshold Calibrator

Automatically adjusts CDS thresholds based on empirical outcome data.
If high-CDS trades consistently underperform, thresholds are tightened.
If CDS is not predictive, a flag is raised for manual review.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import AssetAnalysis, PaperTradeRecord, SystemConfig

logger = logging.getLogger('TradingAgent.CDSThresholdCalibrator')

MIN_TRADES_FOR_CALIBRATION = 20
CALIBRATION_INTERVAL_HOURS = 24
CALIBRATION_KEY = 'cds_threshold_calibration'

async def run_calibration_if_due(session: AsyncSession, settings: dict) -> dict:
    """
    Run CDS threshold calibration if enough data and time have passed.
    Returns calibration result dict.
    """
    # Check if calibration is due
    cfg = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == CALIBRATION_KEY)
    )).scalar_one_or_none()
    
    if cfg and cfg.value:
        try:
            data = json.loads(cfg.value)
            last_run = datetime.fromisoformat(data.get('last_run', '2020-01-01'))
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
            hours_since = (datetime.now(timezone.utc) - last_run).total_seconds() / 3600
            if hours_since < CALIBRATION_INTERVAL_HOURS:
                return {'status': 'skipped', 'reason': f'Last calibration {hours_since:.1f}h ago'}
        except Exception:
            pass
    
    # Run calibration
    result = await _compute_cds_calibration(session, settings)
    
    # Save result
    save_data = {
        'last_run': datetime.now(timezone.utc).isoformat(),
        'result': result
    }
    if cfg:
        cfg.value = json.dumps(save_data)
    else:
        session.add(SystemConfig(key=CALIBRATION_KEY, value=json.dumps(save_data)))
        
    if result.get('new_thresholds') and result['new_thresholds'] != result.get('current_thresholds'):
        dyn_cfg = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == "dynamic_cds_thresholds")
        )).scalar_one_or_none()
        if dyn_cfg:
            dyn_cfg.value = json.dumps(result['new_thresholds'])
        else:
            session.add(SystemConfig(key="dynamic_cds_thresholds", value=json.dumps(result['new_thresholds'])))
            
    await session.commit()
    
    return result


async def _compute_cds_calibration(session: AsyncSession, settings: dict) -> dict:
    """
    Core calibration logic.
    
    Analyzes relationship between CDS at time of analysis and trade outcomes.
    Adjusts thresholds if CDS is strongly predictive.
    """
    since = datetime.now(timezone.utc) - timedelta(days=60)
    
    records = (await session.execute(
        select(AssetAnalysis, PaperTradeRecord)
        .outerjoin(PaperTradeRecord, AssetAnalysis.id == PaperTradeRecord.analysis_id)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.closed_at >= since)
        .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
        .where(AssetAnalysis.ssvp_cds_score_at_analysis.isnot(None))
    )).all()
    
    if len(records) < MIN_TRADES_FOR_CALIBRATION:
        return {
            'status': 'insufficient_data',
            'count': len(records),
            'min_required': MIN_TRADES_FOR_CALIBRATION
        }
    
    # Bucket trades by CDS level
    buckets = {
        'low': {'min': 0.0, 'max': 0.20, 'wins': 0, 'total': 0},
        'warning': {'min': 0.20, 'max': 0.30, 'wins': 0, 'total': 0},
        'medium': {'min': 0.30, 'max': 0.50, 'wins': 0, 'total': 0},
        'high': {'min': 0.50, 'max': 1.0, 'wins': 0, 'total': 0},
    }
    
    for analysis, trade in records:
        cds = analysis.ssvp_cds_score_at_analysis
        is_win = trade.exit_reason == 'tp_hit'
        
        for bucket_name, bucket in buckets.items():
            if bucket['min'] <= cds < bucket['max']:
                bucket['total'] += 1
                if is_win:
                    bucket['wins'] += 1
                break
    
    # Compute win rates per bucket
    for bucket_name, bucket in buckets.items():
        if bucket['total'] > 0:
            bucket['win_rate'] = round(bucket['wins'] / bucket['total'] * 100, 1)
        else:
            bucket['win_rate'] = None
    
    # Check if CDS is predictive: low CDS should have higher win rate than high CDS
    low_wr = buckets['low']['win_rate']
    high_wr = buckets['high']['win_rate']
    
    is_predictive = (
        low_wr is not None and 
        high_wr is not None and 
        buckets['low']['total'] >= 15 and
        buckets['high']['total'] >= 10 and
        low_wr > high_wr + 12  # Statistically meaningful gap
    )
    
    # Determine threshold adjustment
    current_thresholds = {
        'warning': settings.get('ssvp', {}).get('cds_thresholds', {}).get('warning', 0.20),
        'sync_trigger': settings.get('ssvp', {}).get('cds_thresholds', {}).get('sync_trigger', 0.30),
        'block_buysell': settings.get('ssvp', {}).get('cds_thresholds', {}).get('block_buysell', 0.50),
    }
    
    new_thresholds = current_thresholds.copy()
    recommendations = []
    
    if not is_predictive and (buckets['low']['total'] + buckets['medium']['total'] + buckets['high']['total']) >= 25:
        recommendations.append(
            'CDS not yet predictive (sample N>=25). Consider lowering warning threshold by 0.05 '
            'to capture more divergence early.'
        )
        new_thresholds['warning'] = max(0.10, new_thresholds['warning'] - 0.05)
    
    if is_predictive:
        # If high-CDS trades lose significantly with sufficient sample size, tighten block threshold
        if high_wr is not None and high_wr < 25 and buckets['high']['total'] >= 10:
            recommendations.append(
                f'High-CDS win rate={high_wr:.0f}% < 25% (N={buckets["high"]["total"]}). '
                f'Consider lowering block_buysell threshold from '
                f'{current_thresholds["block_buysell"]:.2f} to 0.40.'
            )
            new_thresholds['block_buysell'] = 0.40
        
        # If warning-zone trades perform like low-CDS, loosen warning
        if (buckets['warning']['win_rate'] is not None and 
            low_wr is not None and
            abs(buckets['warning']['win_rate'] - low_wr) < 5):
            recommendations.append(
                f'Warning-zone win rate ({buckets["warning"]["win_rate"]:.0f}%) '
                f'similar to low-CDS ({low_wr:.0f}%). '
                f'Consider raising warning threshold from '
                f'{current_thresholds["warning"]:.2f} to 0.25.'
            )
            new_thresholds['warning'] = 0.25
    
    # Write recommendations to SystemConfig for monitoring dashboard
    summary = {
        'status': 'calibrated',
        'is_cds_predictive': is_predictive,
        'bucket_win_rates': {
            name: {
                'win_rate': b['win_rate'],
                'total': b['total']
            } for name, b in buckets.items()
        },
        'current_thresholds': current_thresholds,
        'new_thresholds': new_thresholds,
        'recommendations': recommendations,
        'computed_at': datetime.now(timezone.utc).isoformat()
    }
    
    if recommendations:
        logger.warning(
            f'[CDSCalibrator] Threshold adjustment recommended: '
            f'{recommendations[0]}'
        )
    else:
        logger.info(
            f'[CDSCalibrator] Thresholds optimal. '
            f'CDS predictive: {is_predictive}. '
            f'Low CDS WR: {low_wr}%, High CDS WR: {high_wr}%'
        )
    
    return summary
