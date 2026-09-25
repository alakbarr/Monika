import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PriceOHLCV
logger = logging.getLogger('TradingAgent.VolumeProfile')
_ANCHORS_UTC = [(0, 'asian'), (8, 'london'), (13, 'ny')]

def _recent_anchor(now: datetime) -> tuple[int, str]:
    c = [(h, n) for h, n in _ANCHORS_UTC if h <= now.hour]
    return c[-1] if c else _ANCHORS_UTC[-1]
from utils.validation.indicator_sanitizer import safe_float

from typing import Optional
import utils.clock as clock

async def compute_anchored_vwap(session: AsyncSession, symbol: str, as_of: Optional[datetime] = None) -> dict:
    now = as_of or clock.now()
    hour, name = _recent_anchor(now)
    anchor = now.replace(hour=hour, minute=0, second=0, microsecond=0)

    # FIX 6.7: Try M15 bars or previous session anchor when < 60 min elapsed to prevent starvation
    elapsed_minutes = (now - anchor).total_seconds() / 60.0
    bars = []
    tf_used = 'H1'
    if elapsed_minutes < 60.0:
        m15_bars = (await session.execute(select(PriceOHLCV).where(
            PriceOHLCV.symbol == symbol,
            PriceOHLCV.timeframe == 'M15',
            PriceOHLCV.timestamp >= anchor,
            PriceOHLCV.timestamp <= now
        ).order_by(PriceOHLCV.timestamp.asc()))).scalars().all()
        if m15_bars:
            bars = m15_bars
            tf_used = 'M15'

    if not bars:
        h1_bars = (await session.execute(select(PriceOHLCV).where(
            PriceOHLCV.symbol == symbol,
            PriceOHLCV.timeframe == 'H1',
            PriceOHLCV.timestamp >= anchor,
            PriceOHLCV.timestamp <= now
        ).order_by(PriceOHLCV.timestamp.asc()))).scalars().all()
        if h1_bars:
            bars = h1_bars
            tf_used = 'H1'

    # If still empty within the first session hour, fall back to previous session anchor
    if not bars:
        from datetime import timedelta
        anchors_hours = [h for h, _ in _ANCHORS_UTC]
        idx = anchors_hours.index(hour)
        prev_h = anchors_hours[idx - 1]
        prev_anchor = (now if prev_h < hour else now - timedelta(days=1)).replace(hour=prev_h, minute=0, second=0, microsecond=0)
        fallback_bars = (await session.execute(select(PriceOHLCV).where(
            PriceOHLCV.symbol == symbol,
            PriceOHLCV.timeframe == 'H1',
            PriceOHLCV.timestamp >= prev_anchor,
            PriceOHLCV.timestamp <= now
        ).order_by(PriceOHLCV.timestamp.asc()))).scalars().all()
        if fallback_bars:
            bars = fallback_bars
            tf_used = 'H1_prev_session'
            name = f"{name}_prev_session"

    if not bars:
        return {'error': 'insufficient_data', 'anchor': name}
    total_vol = sum(float(safe_float(b.volume, 0.0) or 0.0) for b in bars)
    if total_vol <= 0:
        vwap = sum((b.high + b.low + b.close) / 3 for b in bars) / len(bars)
        method = 'unweighted_fallback_no_volume'
    else:
        vwap = sum((b.high + b.low + b.close) / 3 * float(safe_float(b.volume, 0.0) or 0.0) for b in bars) / total_vol
        method = 'tick_volume_weighted'
    last = bars[-1].close
    return {'anchor': name, 'vwap': round(vwap, 5), 'last_close': last,
            'deviation_pct': round((last - vwap) / vwap * 100, 4) if vwap else 0.0, 'method': method}

async def compute_volume_profile(session: AsyncSession, symbol: str, settings: Optional[dict] = None, as_of: Optional[datetime] = None) -> dict:
    """NOTE: MT5 FX/CFD 'volume' is broker TICK volume (no consolidated OTC
    tape exists). Treated as a relative activity proxy, not literal size."""
    settings = settings or {}
    cfg = settings.get('trading', {}).get('edge_strategy', {}).get('volume_profile', {})
    if not cfg.get('enabled', True):
        return {'error': 'disabled_in_settings'}
    lookback = int(cfg.get('profile_lookback_bars', 30))
    va_pct = float(cfg.get('value_area_pct', 0.70))
    as_of_time = as_of or clock.now()
    bars = (await session.execute(select(PriceOHLCV).where(
        PriceOHLCV.symbol == symbol,
        PriceOHLCV.timeframe == 'H1',
        PriceOHLCV.timestamp <= as_of_time
    ).order_by(PriceOHLCV.timestamp.desc()).limit(lookback * 24))).scalars().all()
    if len(bars) < 40:
        return {'error': 'insufficient_data', 'bars_found': len(bars)}
    bars = list(reversed(bars))
    hi, lo = max(b.high for b in bars), min(b.low for b in bars)
    if hi <= lo:
        return {'error': 'degenerate_range'}
    range_pct = (hi - lo) / lo if lo > 0 else 0.01
    n_bins = max(16, min(48, int(range_pct * 1000))) if range_pct > 0 else 24
    bin_size = (hi - lo) / n_bins
    vol_by_bin = [0.0] * n_bins
    for b in bars:
        idx = min(n_bins - 1, max(0, int(((b.high + b.low) / 2 - lo) / bin_size)))
        vol_by_bin[idx] += float(safe_float(b.volume, 1.0) or 1.0)
    poc_idx = max(range(n_bins), key=lambda i: vol_by_bin[i])
    total = sum(vol_by_bin) or 1.0
    target, acc, lo_i, hi_i = total * va_pct, vol_by_bin[poc_idx], poc_idx, poc_idx
    while acc < target and (lo_i > 0 or hi_i < n_bins - 1):
        left = vol_by_bin[lo_i - 1] if lo_i > 0 else -1
        right = vol_by_bin[hi_i + 1] if hi_i < n_bins - 1 else -1
        if right >= left and hi_i < n_bins - 1:
            hi_i += 1; acc += vol_by_bin[hi_i]
        elif lo_i > 0:
            lo_i -= 1; acc += vol_by_bin[lo_i]
        else:
            break
    poc = lo + (poc_idx + 0.5) * bin_size
    vah, val = lo + (hi_i + 1) * bin_size, lo + lo_i * bin_size
    last = bars[-1].close
    regime = 'balanced' if val <= last <= vah else 'imbalanced'
    return {'poc': round(poc, 5), 'vah': round(vah, 5), 'val': round(val, 5),
            'last_close': last, 'regime': regime, 'lookback_bars': len(bars)}
