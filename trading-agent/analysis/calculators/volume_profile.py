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

async def compute_anchored_vwap(
    session: AsyncSession,
    symbol: str,
    as_of: Optional[datetime] = None,
    anchor_mode: str = "session",
    anchor_timestamp: Optional[datetime] = None,
) -> dict:
    """Compute Anchored VWAP with flexible anchor points: session, weekly_low, weekly_high, swing_low, custom."""
    now = as_of or clock.now()
    name = anchor_mode

    if anchor_mode == "custom" and anchor_timestamp:
        anchor = anchor_timestamp
        name = f"custom_{anchor.strftime('%Y%m%d_%H%M')}"
    elif anchor_mode == "daily":
        anchor = now.replace(hour=0, minute=0, second=0, microsecond=0)
        name = "daily_open_00:00"
    elif anchor_mode in ("weekly_low", "weekly_high"):
        from datetime import timedelta
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(PriceOHLCV).where(
            PriceOHLCV.symbol == symbol,
            PriceOHLCV.timeframe == "H1",
            PriceOHLCV.timestamp >= week_start,
            PriceOHLCV.timestamp <= now,
        )
        w_bars = (await session.execute(stmt)).scalars().all()
        if w_bars:
            if anchor_mode == "weekly_low":
                target_bar = min(w_bars, key=lambda b: b.low)
                anchor = target_bar.timestamp
                name = f"weekly_low_{anchor.strftime('%a_%H:%M')}"
            else:
                target_bar = max(w_bars, key=lambda b: b.high)
                anchor = target_bar.timestamp
                name = f"weekly_high_{anchor.strftime('%a_%H:%M')}"
        else:
            anchor = week_start
            name = "week_open"
    elif anchor_mode == "swing_low":
        from database.models import SwingPoint
        stmt = select(SwingPoint).where(
            SwingPoint.symbol == symbol,
            SwingPoint.type.ilike("%low%"),
            SwingPoint.timestamp <= now,
        ).order_by(SwingPoint.timestamp.desc()).limit(1)
        sp = (await session.execute(stmt)).scalar_one_or_none()
        if sp and sp.timestamp:
            anchor = sp.timestamp.replace(tzinfo=timezone.utc) if sp.timestamp.tzinfo is None else sp.timestamp
            try:
                name = f"swing_low_{float(sp.price):.2f}"
            except Exception:
                name = "swing_low"
        else:
            hour, name = _recent_anchor(now)
            anchor = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    else:
        hour, name = _recent_anchor(now)
        anchor = now.replace(hour=hour, minute=0, second=0, microsecond=0)

    # Fetch bars from anchor to now
    stmt = select(PriceOHLCV).where(
        PriceOHLCV.symbol == symbol,
        PriceOHLCV.timeframe == 'H1',
        PriceOHLCV.timestamp >= anchor,
        PriceOHLCV.timestamp <= now
    ).order_by(PriceOHLCV.timestamp.asc())
    bars = (await session.execute(stmt)).scalars().all()

    if not bars:
        stmt_m15 = select(PriceOHLCV).where(
            PriceOHLCV.symbol == symbol,
            PriceOHLCV.timeframe == 'M15',
            PriceOHLCV.timestamp >= anchor,
            PriceOHLCV.timestamp <= now
        ).order_by(PriceOHLCV.timestamp.asc())
        bars = (await session.execute(stmt_m15)).scalars().all()

    if not bars:
        return {'error': 'insufficient_data', 'anchor': name, 'anchor_time': anchor.isoformat() if hasattr(anchor, 'isoformat') else str(anchor)}

    total_vol = sum(float(safe_float(b.volume, 0.0) or 0.0) for b in bars)
    if total_vol <= 0:
        vwap = sum((b.high + b.low + b.close) / 3 for b in bars) / len(bars)
        method = 'unweighted_fallback_no_volume'
    else:
        vwap = sum((b.high + b.low + b.close) / 3 * float(safe_float(b.volume, 0.0) or 0.0) for b in bars) / total_vol
        method = 'tick_volume_weighted'

    last = bars[-1].close
    return {
        'anchor': name,
        'anchor_time': anchor.isoformat() if hasattr(anchor, 'isoformat') else str(anchor),
        'vwap': round(vwap, 5),
        'avwap': round(vwap, 5),
        'last_close': last,
        'deviation_pct': round((last - vwap) / vwap * 100, 4) if vwap else 0.0,
        'method': method,
        'bars_count': len(bars),
    }

async def compute_volume_profile(
    session: AsyncSession,
    symbol: str,
    settings: Optional[dict] = None,
    as_of: Optional[datetime] = None,
    timeframe: str = "H1"
) -> dict:
    """NOTE: MT5 FX/CFD 'volume' is broker TICK volume (no consolidated OTC
    tape exists). Treated as a relative activity proxy, not literal size."""
    settings = settings or {}
    cfg = settings.get('trading', {}).get('edge_strategy', {}).get('volume_profile', {})
    if not cfg.get('enabled', True):
        return {'error': 'disabled_in_settings'}
    lookback = int(cfg.get('profile_lookback_bars', 30))
    va_pct = float(cfg.get('value_area_pct', 0.70))
    as_of_time = as_of or clock.now()
    tf_clean = timeframe.upper() if timeframe else 'H1'

    bars = (await session.execute(select(PriceOHLCV).where(
        PriceOHLCV.symbol == symbol,
        PriceOHLCV.timeframe == tf_clean,
        PriceOHLCV.timestamp <= as_of_time
    ).order_by(PriceOHLCV.timestamp.desc()).limit(lookback * 24))).scalars().all()

    if len(bars) < 20:
        # Fallback to H1 if requested timeframe has insufficient bars
        bars = (await session.execute(select(PriceOHLCV).where(
            PriceOHLCV.symbol == symbol,
            PriceOHLCV.timeframe == 'H1',
            PriceOHLCV.timestamp <= as_of_time
        ).order_by(PriceOHLCV.timestamp.desc()).limit(lookback * 24))).scalars().all()

    if len(bars) < 20:
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
    avg_vol = total / n_bins
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

    # Extract High Volume Nodes (HVN) and Low Volume Nodes (LVN)
    hvn_levels = []
    lvn_levels = []
    for i in range(1, n_bins - 1):
        bin_price = round(lo + (i + 0.5) * bin_size, 5)
        # Local maximum with volume > 1.2x avg
        if vol_by_bin[i] > vol_by_bin[i - 1] and vol_by_bin[i] > vol_by_bin[i + 1] and vol_by_bin[i] >= avg_vol * 1.15:
            hvn_levels.append(bin_price)
        # Local minimum with volume < 0.65x avg
        elif vol_by_bin[i] < vol_by_bin[i - 1] and vol_by_bin[i] < vol_by_bin[i + 1] and vol_by_bin[i] <= avg_vol * 0.70:
            lvn_levels.append(bin_price)

    return {
        'symbol': symbol,
        'timeframe': tf_clean,
        'poc': round(poc, 5),
        'vah': round(vah, 5),
        'val': round(val, 5),
        'hvn_levels': hvn_levels[:5],
        'lvn_levels': lvn_levels[:5],
        'last_close': last,
        'regime': regime,
        'lookback_bars': len(bars)
    }
