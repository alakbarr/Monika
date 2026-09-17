import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from database.models import PrescreenLog, PriceOHLCV

logger = logging.getLogger('TradingAgent.PrescreenCalibrator')


async def resolve_pending_prescreen_logs(session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
    pending = (await session.execute(
        select(PrescreenLog).where(PrescreenLog.resolved == False)
        .where(PrescreenLog.checked_at <= cutoff).limit(200)
    )).scalars().all()
    resolved = 0
    for log in pending:
        target_time = log.checked_at + timedelta(hours=4)
        bar = (await session.execute(
            select(PriceOHLCV).where(PriceOHLCV.symbol == log.symbol).where(PriceOHLCV.timeframe == 'H4')
            .where(PriceOHLCV.timestamp >= target_time - timedelta(hours=2))
            .where(PriceOHLCV.timestamp <= target_time + timedelta(hours=2))
            .order_by(PriceOHLCV.timestamp.asc()).limit(1)
        )).scalar_one_or_none()
        if bar:
            log.price_4h_after = bar.close
        log.resolved = True
        resolved += 1
    if resolved:
        await session.commit()
    return resolved


async def compute_prescreen_skip_quality(session) -> dict:
    skips = (await session.execute(select(PrescreenLog).where(PrescreenLog.decision == 'skip')
             .where(PrescreenLog.resolved == True).where(PrescreenLog.price_4h_after.isnot(None))
             .order_by(PrescreenLog.checked_at.desc()).limit(300))).scalars().all()
    if len(skips) < 20:
        return {'status': 'insufficient_data', 'count': len(skips)}

    def _source(reason: str) -> str:
        return 'local_heuristic' if (reason or '').startswith('Quick local check') else 'llm_prescreen'

    buckets = {'local_heuristic': [], 'llm_prescreen': []}
    for log in skips:
        buckets[_source(log.reason)].append(log)

    out = {'status': 'analyzed', 'total_skips_checked': len(skips)}
    async def _get_atr_pct(symbol: str) -> float:
        from database.models import TechnicalIndicator, PriceOHLCV
        import json as _j
        try:
            atr_row = (await session.execute(
                select(TechnicalIndicator).where(TechnicalIndicator.symbol == symbol)
                .where(TechnicalIndicator.timeframe == 'H4')
                .where(TechnicalIndicator.indicator_name == 'ATR_14')
                .order_by(TechnicalIndicator.timestamp.desc()).limit(1)
            )).scalar_one_or_none()
            if atr_row and atr_row.value_json:
                data = _j.loads(atr_row.value_json)
                atr_val = data.get('atr', data.get('value', 0)) if isinstance(data, dict) else float(data)
                price_row = (await session.execute(
                    select(PriceOHLCV.close).where(PriceOHLCV.symbol == symbol)
                    .order_by(PriceOHLCV.timestamp.desc()).limit(1)
                )).scalar_one_or_none()
                if price_row and price_row > 0:
                    return (atr_val / price_row) * 100
        except Exception:
            pass
        return 1.5 if symbol == 'BTCUSD' else 0.5

    # Cache ATR per symbol to avoid repeated DB hits
    atr_cache = {}

    for source, logs in buckets.items():
        if len(logs) < 10:
            out[source] = {'insufficient_data': True, 'count': len(logs)}
            continue
        big_moves = 0
        for log in logs:
            if not log.price_at_check or log.price_at_check <= 0:
                continue
            move_pct = abs(log.price_4h_after - log.price_at_check) / log.price_at_check * 100
            
            if log.symbol not in atr_cache:
                atr_cache[log.symbol] = await _get_atr_pct(log.symbol)
            
            threshold = atr_cache[log.symbol] * 0.75  # 75% of H4 ATR is considered a big move
            
            if move_pct > threshold:
                big_moves += 1
        false_skip_rate = round(big_moves / len(logs) * 100, 1)
        out[source] = {
            'count': len(logs), 'false_skip_rate_pct': false_skip_rate,
            'recommendation': (f'{source} false-skip rate {false_skip_rate}% is high — consider disabling/loosening.'
                                if false_skip_rate > 35 else f'{source} skip quality acceptable.')
        }
    all_false = [v['false_skip_rate_pct'] for v in out.values() if isinstance(v, dict) and 'false_skip_rate_pct' in v]
    out['false_skip_rate'] = round(sum(all_false) / len(all_false), 1) if all_false else 0.0
    return out
