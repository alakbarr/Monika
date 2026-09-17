import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import NewsItem, NewsClassificationOutcome, PriceOHLCV

logger = logging.getLogger('TradingAgent.NewsClassificationTracker')

IMPACT_CURRENCY_SYMBOL_MAP = {
    'USD': 'EURUSD', 'EUR': 'EURUSD', 'GBP': 'GBPUSD', 'JPY': 'USDJPY',
    'AUD': 'AUDUSD', 'XAU': 'XAUUSD', 'XTI': 'XTIUSD', 'BTC': 'BTCUSD',
}
# Ambang gerakan (% harga dalam 2 jam) yang dianggap "pasar benar-benar bergerak"
IMPACT_MOVE_THRESHOLDS_PCT = {'BREAKING': 0.20, 'HIGH': 0.12, 'MEDIUM': 0.06}


async def snapshot_classification_for_tracking(session: AsyncSession, news_item: NewsItem) -> None:
    if news_item.impact not in ('BREAKING', 'HIGH', 'MEDIUM'):
        return
    tags = (news_item.currency_tags or '').split(',')
    symbol = None
    for tag in tags:
        symbol = IMPACT_CURRENCY_SYMBOL_MAP.get(tag.strip().upper())
        if symbol:
            break
    if not symbol:
        return
    last_bar = (await session.execute(
        select(PriceOHLCV).where(PriceOHLCV.symbol == symbol)
        .order_by(PriceOHLCV.timestamp.desc()).limit(1)
    )).scalar_one_or_none()
    if not last_bar:
        return
    try:
        session.add(NewsClassificationOutcome(
            news_item_id=news_item.id, symbol_checked=symbol,
            classified_impact=news_item.impact,
            classified_at=datetime.now(timezone.utc),
            price_at_classification=last_bar.close,
        ))
        await session.commit()
    except Exception as e:
        logger.debug(f'Outcome snapshot failed (non-fatal): {e}')


async def _get_dynamic_move_threshold_pct(session: AsyncSession, symbol: str, impact_tier: str) -> float:
    # Mengambil ATR H4 terakhir untuk symbol
    from database.models import PriceOHLCV, TechnicalIndicator
    from sqlalchemy import select
    bar = (await session.execute(
        select(PriceOHLCV).where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == 'H4')
        .order_by(PriceOHLCV.timestamp.desc()).limit(1)
    )).scalar_one_or_none()
    
    atr_row = (await session.execute(
        select(TechnicalIndicator.value_json)
        .where(TechnicalIndicator.symbol == symbol, TechnicalIndicator.timeframe == 'H4', TechnicalIndicator.indicator_name == 'ATR_14')
        .order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    )).scalar_one_or_none()
    
    atr_val = None
    if atr_row:
        import json
        try:
            data = json.loads(atr_row)
            atr_val = data.get('atr', data.get('value', 0)) if isinstance(data, dict) else float(data)
        except Exception:
            pass
    
    # Fallback to static if no ATR available or close=0
    static_thresholds = {'BREAKING': 0.20, 'HIGH': 0.12, 'MEDIUM': 0.06}
    if not bar or not atr_val or not bar.close:
        return static_thresholds.get(impact_tier, 0.10)
        
    atr_pct = (atr_val / bar.close) * 100
    
    # BREAKING news expected to move at least 1.5x H4 ATR
    # HIGH news expected to move at least 0.8x H4 ATR
    # MEDIUM news expected to move at least 0.4x H4 ATR
    multipliers = {'BREAKING': 1.5, 'HIGH': 0.8, 'MEDIUM': 0.4}
    
    return atr_pct * multipliers.get(impact_tier, 0.5)

async def resolve_pending_news_outcomes(session: AsyncSession, min_age_hours: float = 2.0) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    pending = (await session.execute(
        select(NewsClassificationOutcome)
        .where(NewsClassificationOutcome.price_2h_after.is_(None))
        .where(NewsClassificationOutcome.classified_at <= cutoff)
        .limit(200)
    )).scalars().all()
    resolved = 0
    for rec in pending:
        bar = (await session.execute(
            select(PriceOHLCV).where(PriceOHLCV.symbol == rec.symbol_checked)
            .where(PriceOHLCV.timeframe.in_(['H1', 'H4']))
            .where(PriceOHLCV.timestamp >= rec.classified_at + timedelta(hours=1, minutes=30))
            .where(PriceOHLCV.timestamp <= rec.classified_at + timedelta(hours=2, minutes=30))
            .order_by(PriceOHLCV.timestamp.asc()).limit(1)
        )).scalar_one_or_none()
        if not bar or not rec.price_at_classification:
            continue
        move_pct = abs(bar.close - rec.price_at_classification) / rec.price_at_classification * 100
        rec.price_2h_after = bar.close
        rec.move_pct_2h = round(move_pct, 4)
        threshold = await _get_dynamic_move_threshold_pct(session, rec.symbol_checked, rec.classified_impact)
        rec.outcome_matched_classification = move_pct >= threshold
        rec.checked_at = datetime.now(timezone.utc)
        resolved += 1
    if resolved:
        await session.commit()
    return resolved


async def compute_and_apply_tier_calibration(session: AsyncSession, days_back: int = 21) -> dict:
    """
    Memperluas auto-correction news classification ke tier HIGH dan MEDIUM, bukan hanya
    BREAKING. Jika match-rate outcome (pergerakan harga riil) suatu tier secara persisten
    buruk, simpan directive korektif yang akan disuntikkan ke prompt klasifikasi berikutnya.
    """
    from sqlalchemy import select
    since = datetime.now(timezone.utc) - timedelta(days=days_back)
    rows = (await session.execute(
        select(NewsClassificationOutcome)
        .where(NewsClassificationOutcome.checked_at.is_not(None))
        .where(NewsClassificationOutcome.classified_at >= since)
    )).scalars().all()
    if len(rows) < 15:
        return {'status': 'insufficient_data', 'count': len(rows)}
    by_impact = {}
    for r in rows:
        b = by_impact.setdefault(r.classified_impact, {'matched': 0, 'total': 0, 'avg_move': 0.0})
        b['total'] += 1
        b['avg_move'] += r.move_pct_2h or 0
        if r.outcome_matched_classification:
            b['matched'] += 1
    for impact, b in by_impact.items():
        b['match_rate_pct'] = round(b['matched'] / b['total'] * 100, 1) if b['total'] else 0
        b['avg_move'] = round(b['avg_move'] / b['total'], 4) if b['total'] else 0
    breaking_match = by_impact.get('BREAKING', {}).get('match_rate_pct', 100)
    over_classification_suspected = breaking_match < 40 and by_impact.get('BREAKING', {}).get('total', 0) >= 8
    
    calibration = {
        'status': 'analyzed', 'days_back': days_back, 'by_impact': by_impact,
        'over_classification_suspected': over_classification_suspected,
        'recommendation': 'Tinjau kriteria BREAKING' if over_classification_suspected else 'OK',
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }

    directives = []
    # BREAKING sudah ditangani oleh news_auto_tighten (existing). Fokus di sini: HIGH & MEDIUM.
    for tier, min_samples, threshold_pct in (('HIGH', 12, 35), ('MEDIUM', 15, 30)):
        data = by_impact.get(tier, {})
        total = data.get('total', 0)
        if total >= min_samples:
            match_rate = data.get('match_rate_pct', 100)
            if match_rate < threshold_pct:
                directives.append(
                    f"{tier} classification hanya {match_rate:.0f}% terkonfirmasi pergerakan "
                    f"harga riil dari {total} sampel — cenderung OVER-classified. Naikkan bar "
                    f"untuk {tier}, lebih sering gunakan tier di bawahnya bila ragu."
                )

    from database.models import SystemConfig
    from sqlalchemy import select
    import json
    key = 'news_tier_calibration_directives'
    payload = json.dumps({'directives': directives, 'computed_at': datetime.now(timezone.utc).isoformat()})
    cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
    if cfg:
        cfg.value = payload
    else:
        session.add(SystemConfig(key=key, value=payload))
    await session.commit()
    return {'directives': directives, **calibration}

async def compute_news_classification_calibration(session: AsyncSession, days_back: int = 21) -> dict:
    """
    Alias resmi — ini nama fungsi yang benar-benar dipanggil oleh
    cycle_scheduler.py._run_daily_calibrations(). Sebelumnya import ini
    mengarah ke nama fungsi yang tidak ada (compute_and_apply_tier_calibration
    adalah nama fungsi asli), sehingga kalibrasi tier berita berbasis outcome
    TIDAK PERNAH berjalan sejak awal (gagal silent, ditangkap try/except).
    """
    return await compute_and_apply_tier_calibration(session, days_back=days_back)
