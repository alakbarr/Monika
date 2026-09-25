import json
import logging
from datetime import datetime, timezone
import utils.clock as clock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import TechnicalIndicator, VIXData, PriceOHLCV

logger = logging.getLogger('TradingAgent.RegimeClassifier')


from typing import Optional

async def _get_latest_adx(session: AsyncSession, symbol: str, timeframe: str = 'D1', as_of: Optional[datetime] = None) -> dict:
    stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol,
        TechnicalIndicator.timeframe == timeframe,
        TechnicalIndicator.indicator_name == 'ADX_14'
    )
    if as_of:
        stmt = stmt.where(TechnicalIndicator.timestamp <= as_of)
    stmt = stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if not row:
        return {}
    try:
        data = json.loads(row.value_json)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


async def _get_atr_series(session: AsyncSession, symbol: str, timeframe: str = 'H4', n: int = 20, as_of: Optional[datetime] = None) -> list[float]:
    stmt = select(TechnicalIndicator.value_json).where(
        TechnicalIndicator.symbol == symbol,
        TechnicalIndicator.timeframe == timeframe,
        TechnicalIndicator.indicator_name == 'ATR_14'
    )
    if as_of:
        stmt = stmt.where(TechnicalIndicator.timestamp <= as_of)
    stmt = stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(n)
    rows = (await session.execute(stmt)).scalars().all()
    out = []
    for raw in rows:
        try:
            data = json.loads(raw)
            val = data.get('atr', data.get('value', 0)) if isinstance(data, dict) else float(data)
            if val and val > 0:
                out.append(float(val))
        except Exception:
            continue
    return out


async def classify_market_regime(session: AsyncSession, symbol: str, settings: Optional[dict] = None, as_of: Optional[datetime] = None) -> dict:
    """Composite regime: D1 trend strength (ADX) + H4 volatility expansion/contraction
    (ATR ratio vs 20-bar baseline) + VIX macro backdrop -> single actionable label with
    a confluence-threshold modifier and a position-size multiplier."""
    settings = settings or {}
    adx_data = await _get_latest_adx(session, symbol, 'D1', as_of=as_of)
    from utils.validation.indicator_sanitizer import safe_float
    adx_val = safe_float(adx_data.get('adx')) if adx_data else None

    atr_series = await _get_atr_series(session, symbol, 'H4', 20, as_of=as_of)
    vol_ratio = None
    if len(atr_series) >= 8:
        recent = sum(atr_series[:5]) / min(5, len(atr_series[:5]))
        baseline = sum(atr_series) / len(atr_series)
        if baseline > 0:
            vol_ratio = round(recent / baseline, 3)

    vix_stmt = select(VIXData)
    if as_of:
        vix_stmt = vix_stmt.where(VIXData.date <= as_of.date())
    vix_stmt = vix_stmt.order_by(VIXData.date.desc()).limit(1)
    vix_row = (await session.execute(vix_stmt)).scalar_one_or_none()
    vix_close = vix_row.close if vix_row else None

    if adx_val is None:
        trend_label, trend_quality = 'UNKNOWN', 0.4
    elif adx_val >= 40:
        trend_label, trend_quality = 'STRONG_TREND', 1.0
    elif adx_val >= 25:
        trend_label, trend_quality = 'TREND', 0.85
    elif adx_val >= 18:
        trend_label, trend_quality = 'WEAK_TREND', 0.6
    else:
        trend_label, trend_quality = 'RANGE', 0.4

    if vol_ratio is None:
        vol_label, vol_quality = 'NORMAL', 0.7
    elif vol_ratio > 1.4:
        vol_label = 'EXPANDING_FAST'
        vol_quality = 0.85 if trend_label in ('STRONG_TREND', 'TREND') else 0.5
    elif vol_ratio > 1.15:
        vol_label, vol_quality = 'EXPANDING', 0.8 if trend_label in ('STRONG_TREND', 'TREND') else 0.75
    elif vol_ratio < 0.65:
        vol_label, vol_quality = 'CONTRACTING_FAST', 0.80
    elif vol_ratio < 0.85:
        vol_label, vol_quality = 'CONTRACTING', 0.75
    else:
        vol_label, vol_quality = 'NORMAL', 1.0

    if vix_close is None:
        vix_quality = 0.8
    elif vix_close >= 28:
        vix_quality = 0.3
    elif vix_close >= 22:
        vix_quality = 0.6
    elif vix_close <= 12:
        vix_quality = 0.75
    else:
        vix_quality = 1.0

    composite_quality = round(trend_quality * 0.45 + vol_quality * 0.35 + vix_quality * 0.20, 3)

    if trend_label in ('STRONG_TREND', 'TREND') and vol_label in ('NORMAL', 'EXPANDING', 'EXPANDING_FAST'):
        final_regime = trend_label
    elif vol_label == 'CONTRACTING_FAST':
        final_regime = 'SQUEEZE_CONSOLIDATION'
    elif vol_label == 'EXPANDING_FAST':
        final_regime = 'VOLATILE_CHOP'
    elif trend_label in ('RANGE', 'WEAK_TREND'):
        final_regime = trend_label
    else:
        final_regime = 'WEAK_TREND'

    if composite_quality >= 0.85:
        threshold_modifier, size_multiplier = -1, 1.1
    elif composite_quality >= 0.65:
        threshold_modifier, size_multiplier = 0, 1.0
    elif composite_quality >= 0.45:
        threshold_modifier, size_multiplier = 1, 0.65
    else:
        threshold_modifier, size_multiplier = 2, 0.4

    volatility_chop = await compute_bollinger_donchian_chop(session, symbol, 'H4', settings or {}, as_of=as_of)

    # Continuous probabilistic distribution across market regimes
    p_trend = 0.5
    if adx_val is not None:
        p_trend = min(1.0, max(0.05, (adx_val - 12.0) / 28.0))
    p_chop = 0.2
    if vol_ratio is not None:
        if vol_ratio > 1.2:
            p_chop = min(0.9, max(0.1, (vol_ratio - 1.0) * 1.5))
        elif vol_ratio < 0.7:
            # Low vol is squeeze / calm consolidation, NOT volatile chop!
            p_chop = max(0.05, 0.15 - (0.7 - vol_ratio) * 0.2)
        else:
            p_chop = 0.15

    if vol_ratio is not None and vol_ratio < 0.85:
        p_range = max(0.2, min(0.85, (0.95 - vol_ratio) * 1.5))
    else:
        p_range = max(0.05, 1.0 - (p_trend * 0.7 + p_chop * 0.3))

    total_p = p_trend + p_chop + p_range
    regime_probs = {
        "trend": round(p_trend / total_p, 3),
        "range": round(p_range / total_p, 3),
        "volatile_chop": round(p_chop / total_p, 3),
    }

    return {
        'regime': final_regime, 'composite_quality': composite_quality,
        'adx': adx_val, 'vol_ratio': vol_ratio, 'vix': vix_close,
        'threshold_modifier': threshold_modifier, 'size_multiplier': size_multiplier,
        'computed_at': (as_of or clock.now()).isoformat(),
        'volatility_chop': volatility_chop,
        'regime_probabilities': regime_probs,
    }

async def compute_bollinger_donchian_chop(session, symbol: str, timeframe: str, settings: dict, as_of: Optional[datetime] = None) -> dict:
    import json
    from utils.validation.indicator_sanitizer import safe_float
    cfg = settings.get('trading', {}).get('edge_strategy', {}).get('volatility_regime', {})
    if not cfg.get('enabled', True):
        return {'chop_block': False, 'reason': 'disabled_in_settings'}
    lookback = int(cfg.get('lookback_bars', 20))
    bb_stmt = select(TechnicalIndicator).where(
        TechnicalIndicator.symbol == symbol, TechnicalIndicator.timeframe == timeframe,
        TechnicalIndicator.indicator_name == 'BBANDS')
    if as_of:
        bb_stmt = bb_stmt.where(TechnicalIndicator.timestamp <= as_of)
    bb_stmt = bb_stmt.order_by(TechnicalIndicator.timestamp.desc()).limit(lookback)
    bb_rows = (await session.execute(bb_stmt)).scalars().all()
    if len(bb_rows) < 10:
        return {'chop_block': False, 'reason': 'insufficient_history_fail_open'}
    widths = []
    for row in bb_rows:
        try:
            w = safe_float(json.loads(row.value_json).get('width'))
            if w is not None:
                widths.append(w)
        except Exception:
            continue
    if len(widths) < 10:
        return {'chop_block': False, 'reason': 'insufficient_valid_samples_fail_open'}
    current = widths[0]
    ranked = sorted(widths)
    percentile = ranked.index(min(ranked, key=lambda x: abs(x - current))) / len(ranked) * 100
    chop_max = float(cfg.get('chop_atr_percentile_max', 25))
    don_stmt = select(PriceOHLCV).where(
        PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == timeframe)
    if as_of:
        don_stmt = don_stmt.where(PriceOHLCV.timestamp <= as_of)
    don_stmt = don_stmt.order_by(PriceOHLCV.timestamp.desc()).limit(20)
    donchian_rows = (await session.execute(don_stmt)).scalars().all()
    is_breakout = False
    if len(donchian_rows) >= 20:
        recent = donchian_rows[0]
        ch_high = max(b.high for b in donchian_rows[1:])
        ch_low = min(b.low for b in donchian_rows[1:])
        is_breakout = recent.close > ch_high or recent.close < ch_low
    chop_block = percentile <= chop_max and not is_breakout
    return {'bb_width_percentile': round(percentile, 1), 'is_breakout': is_breakout,
            'chop_block': chop_block,
            'reason': (f'BB width @ {percentile:.0f}th pct (<={chop_max}) no breakout' if chop_block else 'ok')}
