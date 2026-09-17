import logging
from datetime import datetime, timezone
import utils.clock as clock
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PriceOHLCV
logger = logging.getLogger('TradingAgent.DailyRangeCalculator')

DEFAULT_LOOKBACK_FX = 5
DEFAULT_LOOKBACK_247 = 7
DEFAULT_LOOKBACK_BASELINE = 20


def _resolve_lookback_days(symbol: str, settings: dict) -> int:
    risk_cfg = (settings or {}).get('trading', {}).get('risk', {})
    always_open = set((settings or {}).get('trading', {}).get('24_7_assets', ['BTCUSD']))
    if symbol in always_open:
        return int(risk_cfg.get('adr_lookback_days_247', DEFAULT_LOOKBACK_247))
    return int(risk_cfg.get('adr_lookback_days_fx', DEFAULT_LOOKBACK_FX))


def _trimmed_average(ranges: list[float]) -> float:
    """Drop the single highest range (news-day outlier) when >=5 samples, so ADR
    reflects a *typical* day rather than one anomalous session."""
    if len(ranges) >= 5:
        trimmed = sorted(ranges)[:-1]
        return sum(trimmed) / len(trimmed)
    return sum(ranges) / len(ranges)


from typing import Optional

async def _compute_baseline_adr(session: AsyncSession, symbol: str, lookback_days: int, as_of: Optional[datetime] = None):
    stmt = select(PriceOHLCV).where(PriceOHLCV.symbol == symbol).where(PriceOHLCV.timeframe == 'D1')
    if as_of:
        stmt = stmt.where(PriceOHLCV.timestamp <= as_of)
    stmt = stmt.order_by(PriceOHLCV.timestamp.desc()).limit(lookback_days + 2)
    rows = (await session.execute(stmt)).scalars().all()
    rows = list(rows)
    if len(rows) < 10:
        return None
    history = rows[1:1 + lookback_days] if len(rows) > lookback_days else rows[1:]
    ranges = [r.high - r.low for r in history if r.high and r.low and r.high > r.low]
    if len(ranges) < 8:
        return None
    return _trimmed_average(ranges)


def _classify_volatility_regime(adr_short: float, adr_baseline):
    if not adr_baseline or adr_baseline <= 0:
        return ('normal', 1.0)
    ratio = round(adr_short / adr_baseline, 3)
    if ratio >= 1.35:
        return ('expanding_fast', ratio)
    elif ratio >= 1.15:
        return ('expanding', ratio)
    elif ratio <= 0.65:
        return ('contracting_fast', ratio)
    elif ratio <= 0.85:
        return ('contracting', ratio)
    return ('normal', ratio)


def _band_scale_factor(vol_regime: str) -> dict:
    table = {
        'expanding_fast':   {'tp_min': 1.00, 'tp_max': 1.05, 'sl_max': 1.20},
        'expanding':        {'tp_min': 1.00, 'tp_max': 1.03, 'sl_max': 1.10},
        'normal':           {'tp_min': 1.00, 'tp_max': 1.00, 'sl_max': 1.00},
        'contracting':      {'tp_min': 0.92, 'tp_max': 0.92, 'sl_max': 0.88},
        'contracting_fast': {'tp_min': 0.85, 'tp_max': 0.85, 'sl_max': 0.75},
    }
    return table.get(vol_regime, table['normal'])


async def compute_daily_range_context(session: AsyncSession, symbol: str, settings: Optional[dict] = None, as_of: Optional[datetime] = None) -> dict:
    settings = settings or {}
    risk_cfg = settings.get('trading', {}).get('risk', {})
    lookback_days = _resolve_lookback_days(symbol, settings)
    stmt = select(PriceOHLCV).where(PriceOHLCV.symbol == symbol).where(PriceOHLCV.timeframe == 'D1')
    if as_of:
        stmt = stmt.where(PriceOHLCV.timestamp <= as_of)
    stmt = stmt.order_by(PriceOHLCV.timestamp.desc()).limit(lookback_days + 2)
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) < 3:
        return {'error': f'Insufficient D1 history for {symbol} ({len(rows)} bars, need >= 3)'}

    rows = list(rows)
    now = as_of or clock.now()
    today_bar = rows[0]
    today_ts = today_bar.timestamp.replace(tzinfo=timezone.utc) if today_bar.timestamp.tzinfo is None else today_bar.timestamp
    is_today_forming = today_ts.date() == now.date()

    if is_today_forming:
        today_open, today_high, today_low = today_bar.open, today_bar.high, today_bar.low
        history_rows = rows[1:1 + lookback_days]
    else:
        today_open = today_high = today_low = today_bar.close
        history_rows = rows[0:lookback_days]

    if len(history_rows) < 3:
        return {'error': f'Insufficient completed D1 history for {symbol} ADR calc ({len(history_rows)} bars)'}

    ranges_raw = [r.high - r.low for r in history_rows if r.high and r.low and r.high > r.low]
    if not ranges_raw:
        return {'error': f'No valid D1 ranges for {symbol}'}

    adr_raw_avg = sum(ranges_raw) / len(ranges_raw)
    adr = _trimmed_average(ranges_raw)
    if adr <= 0:
        return {'error': f'Computed ADR <= 0 for {symbol}'}

    baseline_days = int(risk_cfg.get('adr_baseline_lookback_days', DEFAULT_LOOKBACK_BASELINE))
    adr_baseline = await _compute_baseline_adr(session, symbol, baseline_days, as_of=as_of)
    vol_regime, expansion_ratio = _classify_volatility_regime(adr, adr_baseline)
    scale = _band_scale_factor(vol_regime)

    today_range_so_far = max(0.0, today_high - today_low)
    today_range_pct_of_adr = min(1.5, today_range_so_far / adr) if adr > 0 else 0.0
    move_from_open_up = max(0.0, today_high - today_open)
    move_from_open_down = max(0.0, today_open - today_low)

    tp_min_pct = float(risk_cfg.get('intraday_tp_min_adr_pct', 0.5)) * scale['tp_min']
    tp_max_pct = float(risk_cfg.get('intraday_tp_max_adr_pct', 0.8)) * scale['tp_max']
    sl_max_pct = float(risk_cfg.get('intraday_max_sl_adr_pct', 0.35)) * scale['sl_max']
    tolerance = float(risk_cfg.get('intraday_adr_band_tolerance_pct', 0.1))

    room_remaining_pct = max(0.0, 1.0 - today_range_pct_of_adr)

    # Time-decay: shrink the upper TP bound as the day's typical range gets used up
    if room_remaining_pct < 0.5:
        decay_factor = max(0.55, room_remaining_pct / 0.5)
        tp_max_pct = tp_min_pct + (tp_max_pct - tp_min_pct) * decay_factor

    # SOTA TimesFM 3.0 Predictive Volatility & Range Integration
    timesfm_data = None
    try:
        from indicators.timesfm_engine import TimesFMEngine
        engine = TimesFMEngine(settings)
        timesfm_data = await engine.get_latest_forecast(session, symbol, timeframe="H1", max_age_hours=8.0)
    except Exception as tfm_err:
        logger.debug(f"[{symbol}] TimesFM forecast lookup failed (non-fatal): {tfm_err}")

    if timesfm_data and timesfm_data.get("expected_range", 0) > 0:
        tfm_range = float(timesfm_data["expected_range"])
        tfm_ratio = float(timesfm_data.get("volatility_expansion_ratio", 1.0))
        # Blend empirical ADR with forward-looking TimesFM expected range (60% ADR, 40% TimesFM)
        effective_range = (adr * 0.60) + (tfm_range * 0.40)
        # Re-tune scale if TimesFM detects impending volatility breakout or squeeze
        if tfm_ratio >= 1.25 and vol_regime in ("normal", "contracting"):
            vol_regime = "expanding"
            scale = _band_scale_factor("expanding")
        elif tfm_ratio <= 0.75 and vol_regime in ("normal", "expanding"):
            vol_regime = "contracting"
            scale = _band_scale_factor("contracting")
    else:
        effective_range = adr
        tfm_range = None
        tfm_ratio = None

    target_tp_min = effective_range * tp_min_pct
    target_tp_max = max(target_tp_min * 1.05, effective_range * tp_max_pct)
    target_sl_max = effective_range * sl_max_pct

    if room_remaining_pct < 0.15:
        session_recommendation, entry_allowed = 'avoid_new_entry_low_room', False
    elif room_remaining_pct < 0.30:
        session_recommendation, entry_allowed = 'reduced_target', True
    else:
        session_recommendation, entry_allowed = 'full_target', True

    return {
        'symbol': symbol, 'lookback_days': lookback_days,
        'adr': round(adr, 6), 'adr_raw_avg': round(adr_raw_avg, 6), 'outlier_trimmed': len(ranges_raw) >= 5,
        'volatility_regime': vol_regime, 'volatility_expansion_ratio': expansion_ratio, 'band_scale_factor': scale,
        'today_open': round(today_open, 6), 'today_high_so_far': round(today_high, 6),
        'today_low_so_far': round(today_low, 6), 'today_range_so_far': round(today_range_so_far, 6),
        'today_range_pct_of_adr': round(today_range_pct_of_adr, 4),
        'room_remaining_pct': round(room_remaining_pct, 4),
        'move_from_open_up': round(move_from_open_up, 6), 'move_from_open_down': round(move_from_open_down, 6),
        'target_tp_min_distance': round(target_tp_min, 6), 'target_tp_max_distance': round(target_tp_max, 6),
        'target_sl_max_distance': round(target_sl_max, 6), 'band_tolerance_pct': tolerance,
        'session_recommendation': session_recommendation, 'entry_allowed': entry_allowed,
        'timesfm_range': round(tfm_range, 6) if tfm_range is not None else None,
        'timesfm_vol_ratio': round(tfm_ratio, 3) if tfm_ratio is not None else None,
        'effective_range': round(effective_range, 6),
        'computed_at': now.isoformat(),
    }
