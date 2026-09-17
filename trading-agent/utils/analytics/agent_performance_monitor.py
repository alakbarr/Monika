"""
Agent Performance Monitor - tracks accuracy metrics per agent type.
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PaperTradeRecord, AssetAnalysis, SystemConfig

logger = logging.getLogger('TradingAgent.AgentPerformanceMonitor')

async def compute_agent_accuracy_report(session: AsyncSession, days_back: int = 30, horizon_start_h: int = 4, horizon_end_h: int = 8) -> dict:
    """Compute accuracy metrics for each agent stage."""
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    
    # Stage 1 accuracy: Did currency bias align with subsequent price movement?
    from database.models import FundamentalBrief, PriceOHLCV
    
    briefs = (await session.execute(
        select(FundamentalBrief)
        .where(FundamentalBrief.generated_at >= since)
        .order_by(FundamentalBrief.generated_at.desc())
        .limit(100)
    )).scalars().all()
    
    import json
    stage1_accuracy = {'total': 0, 'correct': 0, 'by_currency': {}}
    brier_score_sum = 0.0
    
    CURRENCY_PROXY = {
        'USD': {'symbol': 'EURUSD', 'invert': True},   # USD up = EURUSD down
        'EUR': {'symbol': 'EURUSD', 'invert': False},
        'GBP': {'symbol': 'GBPUSD', 'invert': False},
        'JPY': {'symbol': 'USDJPY', 'invert': True},   # JPY up = USDJPY down
        'AUD': {'symbol': 'AUDUSD', 'invert': False},
        'XAU': {'symbol': 'XAUUSD', 'invert': False},
    }
    
    for brief in briefs[:50]:  # Limit to 50 for performance
        if not brief.structured_json:
            continue
        
        try:
            b_data = json.loads(brief.structured_json)
            currency_bias = b_data.get('currency_bias', {})
            confidence = b_data.get('confidence', 0.5)
            brief_time = brief.generated_at
            if brief_time.tzinfo is None:
                brief_time = brief_time.replace(tzinfo=timezone.utc)
            
            check_time_start = brief_time + timedelta(hours=horizon_start_h)
            check_time_end = brief_time + timedelta(hours=horizon_end_h)
            
            for currency, bias in currency_bias.items():
                if currency not in CURRENCY_PROXY or bias == 'neutral':
                    continue
                
                proxy = CURRENCY_PROXY[currency]
                symbol = proxy['symbol']
                invert = proxy['invert']
                
                # Get price at brief generation and 4-8h later
                price_at_brief = (await session.execute(
                    select(PriceOHLCV.close)
                    .where(PriceOHLCV.symbol == symbol)
                    .where(PriceOHLCV.timeframe == 'H4')
                    .where(PriceOHLCV.timestamp <= brief_time + timedelta(hours=1))
                    .where(PriceOHLCV.timestamp >= brief_time - timedelta(hours=1))
                    .order_by(func.abs(
                        func.extract('epoch', PriceOHLCV.timestamp) - 
                        brief_time.timestamp()
                    ))
                    .limit(1)
                )).scalar_one_or_none()
                
                price_after = (await session.execute(
                    select(PriceOHLCV.close)
                    .where(PriceOHLCV.symbol == symbol)
                    .where(PriceOHLCV.timeframe == 'H4')
                    .where(PriceOHLCV.timestamp >= check_time_start)
                    .where(PriceOHLCV.timestamp <= check_time_end)
                    .order_by(PriceOHLCV.timestamp)
                    .limit(1)
                )).scalar_one_or_none()
                
                if not price_at_brief or not price_after:
                    continue
                
                price_moved_up = price_after > price_at_brief
                if invert:
                    price_moved_up = not price_moved_up
                
                from utils.market.bias_utils import normalize_bias
                brief_was_bullish = normalize_bias(bias) == 'bullish'
                is_correct = (brief_was_bullish == price_moved_up)
                
                # Brier Score calculation
                # forecast probability = confidence if bias matches direction, else (1 - confidence)
                # Since we only test directional accuracy, actual outcome is 1 (correct) or 0 (incorrect)
                actual_outcome = 1.0 if is_correct else 0.0
                forecast_prob = confidence  # Because we evaluate from the perspective of the chosen bias
                
                brier_score_sum += (forecast_prob - actual_outcome) ** 2
                
                if currency not in stage1_accuracy['by_currency']:
                    stage1_accuracy['by_currency'][currency] = {'correct': 0, 'total': 0, 'brier_sum': 0.0}
                
                stage1_accuracy['by_currency'][currency]['total'] += 1
                stage1_accuracy['by_currency'][currency]['brier_sum'] += (forecast_prob - actual_outcome) ** 2
                if is_correct:
                    stage1_accuracy['by_currency'][currency]['correct'] += 1
                
                stage1_accuracy['total'] += 1
                if is_correct:
                    stage1_accuracy['correct'] += 1
        except Exception as e:
            logger.debug(f'Stage 1 accuracy check failed for brief {brief.id}: {e}')
    
    # Compute overall accuracy
    overall_stage1 = (
        stage1_accuracy['correct'] / stage1_accuracy['total'] * 100 
        if stage1_accuracy['total'] > 0 else 0
    )
    
    brier_score = (
        brier_score_sum / stage1_accuracy['total']
        if stage1_accuracy['total'] > 0 else 0
    )
    
    by_currency_rates = {}
    for currency, data in stage1_accuracy['by_currency'].items():
        if data['total'] >= 5:
            by_currency_rates[currency] = {
                'accuracy': round(data['correct'] / data['total'] * 100, 1),
                'brier_score': round(data['brier_sum'] / data['total'], 3),
                'total': data['total']
            }
    
    return {
        'stage1_bias_accuracy': {
            'overall': round(overall_stage1, 1),
            'brier_score': round(brier_score, 3),
            'total_checked': stage1_accuracy['total'],
            'by_currency': by_currency_rates,
            'interpretation': (
                'EXCELLENT' if overall_stage1 >= 60 else
                'GOOD' if overall_stage1 >= 55 else
                'ACCEPTABLE' if overall_stage1 >= 50 else
                'BELOW_RANDOM - review Stage 1 prompts'
            )
        },
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'days_analyzed': days_back
    }

async def compute_dynamic_escalation_threshold(session: AsyncSession, base_limit: int = 1) -> int:
    """
    Compute dynamic Opus escalation budget/limit.
    Increases limit if VIX is high (complex market) or recent accuracy is poor.
    """
    from database.models import VIXData
    
    escalation_limit = base_limit
    
    try:
        # 1. Market Complexity (VIX)
        vix = (await session.execute(
            select(VIXData).order_by(VIXData.date.desc()).limit(1)
        )).scalar_one_or_none()
        
        if vix:
            if vix.close >= 30:
                escalation_limit += 2  # Extreme conditions, need more Opus
            elif vix.close >= 20:
                escalation_limit += 1  # Elevated conditions
                
        # 2. Recent Accuracy Check
        accuracy_report = await compute_agent_accuracy_report(session, days_back=7)
        overall_acc = accuracy_report.get('stage1_bias_accuracy', {}).get('overall', 50)
        
        if overall_acc < 45:
            escalation_limit += 1  # Poor recent performance, allow Opus to override Sonnet more
            
    except Exception as e:
        logger.error(f"Failed to compute dynamic escalation threshold: {e}")
        
    return min(escalation_limit, 5)  # Hard cap at 5 to prevent runaway costs

async def compute_agent_accuracy_report_multi_horizon(session: AsyncSession, days_back: int = 30) -> dict:
    """
    Menggabungkan akurasi horizon pendek (4-8h, sinyal taktis) dan horizon panjang
    (24-32h, sinyal fundamental sesungguhnya). Bias makro sering benar dalam horizon
    multi-hari meski noisy jangka pendek — mengandalkan horizon pendek saja bisa
    menghasilkan kalibrasi yang tidak adil terhadap kualitas bias fundamental Stage1.
    """
    short = await compute_agent_accuracy_report(session, days_back, 4, 8)
    long = await compute_agent_accuracy_report(session, days_back, 24, 32)
    short_acc = short['stage1_bias_accuracy']
    long_acc = long['stage1_bias_accuracy']
    if short_acc['total_checked'] > 0 and long_acc['total_checked'] > 0:
        combined = round(0.3 * short_acc['overall'] + 0.7 * long_acc['overall'], 1)
    elif long_acc['total_checked'] > 0:
        combined = long_acc['overall']
    elif short_acc['total_checked'] > 0:
        combined = short_acc['overall']
    else:
        combined = None
    return {'short_horizon': short_acc, 'long_horizon': long_acc, 'combined_overall_accuracy': combined}

async def get_currency_confidence_ceiling(session: AsyncSession, days_back: int = 30) -> dict:
    """
    Establish hard boundaries on confidence based on historical win rates.
    If historical win rate for a currency is poor, cap the max allowable confidence.
    """
    multi = await compute_agent_accuracy_report_multi_horizon(session, days_back)
    ceilings = {}
    long_by_currency = multi['long_horizon'].get('by_currency', {})
    short_by_currency = multi['short_horizon'].get('by_currency', {})
    for cur in set(long_by_currency) | set(short_by_currency):
        long_data = long_by_currency.get(cur)
        short_data = short_by_currency.get(cur)
        # Prioritaskan horizon panjang (tes sesungguhnya untuk kebenaran fundamental);
        # fallback ke horizon pendek hanya jika data horizon panjang belum cukup.
        data = long_data if (long_data and long_data['total'] >= 5) else short_data
        if not data:
            continue
        win_rate, total = data['accuracy'], data['total']
        if total < 5:
            ceilings[cur] = 0.85
        elif win_rate < 30:
            ceilings[cur] = 0.5
        elif win_rate < 45:
            ceilings[cur] = 0.65
        elif win_rate < 60:
            ceilings[cur] = 0.8
        else:
            ceilings[cur] = 0.95
    return ceilings
