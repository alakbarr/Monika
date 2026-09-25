import logging
from datetime import datetime, timezone, timedelta
import utils.clock as clock
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PriceOHLCV, StructureBreak, FVGZone, OrderBlock
logger = logging.getLogger('TradingAgent.LiquiditySweep')

from utils.validation.indicator_sanitizer import safe_float

async def _confirm_with_volume(session, symbol: str, sweep_bar) -> bool:
    from database.models import PriceOHLCV
    recent = (await session.execute(select(PriceOHLCV.volume).where(
        PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == 'H1',
        PriceOHLCV.timestamp < sweep_bar.timestamp
    ).order_by(PriceOHLCV.timestamp.desc()).limit(20))).scalars().all()
    sweep_vol = float(safe_float(sweep_bar.volume, 0.0) or 0.0)
    if len(recent) < 10 or sweep_vol == 0.0:
        return True
    
    clean_recent: list[float] = [float(safe_float(v, 0.0) or 0.0) for v in recent]
    avg_vol = sum(clean_recent) / len(clean_recent)
    return sweep_vol >= avg_vol * 1.3

from typing import Optional

async def _get_asian_session_range(session: AsyncSession, symbol: str, settings: dict, as_of: Optional[datetime] = None) -> dict | None:
    cfg = settings.get('trading', {}).get('edge_strategy', {}).get('liquidity_sweep', {})
    start_h = int(cfg.get('asian_session_start_utc', 0))
    end_h = int(cfg.get('asian_session_end_utc', 8))
    now = as_of or clock.now()
    session_end = now.replace(hour=end_h, minute=0, second=0, microsecond=0)
    if now < session_end:
        session_end -= timedelta(days=1)
    session_start = session_end.replace(hour=start_h)
    if start_h > end_h:
        session_start -= timedelta(days=1)
    bars_stmt = (
        select(PriceOHLCV).where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == 'H1')
        .where(PriceOHLCV.timestamp >= session_start, PriceOHLCV.timestamp < session_end)
        .order_by(PriceOHLCV.timestamp.asc())
    )
    if as_of:
        bars_stmt = bars_stmt.where(PriceOHLCV.timestamp <= as_of)
    bars = (await session.execute(bars_stmt)).scalars().all()
    if len(bars) < 4:
        return None
    return {'session_start': session_start, 'session_end': session_end,
            'high': max(b.high for b in bars), 'low': min(b.low for b in bars)}

async def detect_liquidity_sweep(session: AsyncSession, symbol: str, settings: dict, as_of: Optional[datetime] = None) -> dict:
    result = {'symbol': symbol, 'sweep_detected': False, 'sweep_direction': None,
              'structure_confirmed': False, 'valid_for_direction': None, 'reasons': []}
    cfg = settings.get('trading', {}).get('edge_strategy', {}).get('liquidity_sweep', {})
    if not cfg.get('enabled', True):
        result['reasons'].append('disabled_in_settings'); return result

    asian = await _get_asian_session_range(session, symbol, settings, as_of=as_of)
    if not asian:
        result['reasons'].append('insufficient_H1_history_fail_open'); return result

    post_bars_stmt = (
        select(PriceOHLCV).where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == 'H1')
        .where(PriceOHLCV.timestamp >= asian['session_end'])
        .order_by(PriceOHLCV.timestamp.asc())
    )
    if as_of:
        post_bars_stmt = post_bars_stmt.where(PriceOHLCV.timestamp <= as_of)
    post_bars = (await session.execute(post_bars_stmt)).scalars().all()
    if not post_bars:
        result['reasons'].append('no_post_session_bars_yet'); return result

    now_ref = as_of or clock.now()
    if now_ref.tzinfo is None:
        now_ref = now_ref.replace(tzinfo=timezone.utc)

    sweep_bar, sweep_direction = None, None
    for bar in post_bars:
        # Ensure candle is confirmed closed (candle start + 1 hour <= now_ref)
        b_ts = bar.timestamp.replace(tzinfo=timezone.utc) if bar.timestamp.tzinfo is None else bar.timestamp
        if b_ts + timedelta(hours=1) > now_ref:
            continue

        if bar.high > asian['high'] and bar.close < asian['high']:
            sweep_bar, sweep_direction = bar, 'sell_side'   # swept buy-stops -> bearish reversal expected
            break
        if bar.low < asian['low'] and bar.close > asian['low']:
            sweep_bar, sweep_direction = bar, 'buy_side'    # swept sell-stops -> bullish reversal expected
            break

    result['asian_high'], result['asian_low'] = asian['high'], asian['low']
    if sweep_bar is None:
        result['reasons'].append('no_confirmed_sweep_this_session'); return result

    # 6-hour TTL expiry: liquidity sweeps older than 6 hours are stale and no longer actionable
    sweep_ts = sweep_bar.timestamp.replace(tzinfo=timezone.utc) if sweep_bar.timestamp.tzinfo is None else sweep_bar.timestamp
    if (now_ref - sweep_ts) > timedelta(hours=6):
        result['reasons'].append(f'sweep_detected_but_expired ({((now_ref - sweep_ts).total_seconds()/3600):.1f}h old > 6.0h TTL)')
        return result

    sweep_price = sweep_bar.high if sweep_direction == 'sell_side' else sweep_bar.low
    result.update(sweep_detected=True, sweep_direction=sweep_direction,
                   sweep_time=sweep_bar.timestamp.isoformat(), sweep_price=sweep_price)

    expected_bias = 'sell' if sweep_direction == 'sell_side' else 'buy'
    ob_dir = 'bearish' if sweep_direction == 'sell_side' else 'bullish'

    break_stmt = (
        select(StructureBreak).where(StructureBreak.symbol == symbol,
            StructureBreak.timeframe.in_(['H1', 'H4']), StructureBreak.formed_at >= sweep_bar.timestamp,
            StructureBreak.direction == ob_dir)
    )
    if as_of:
        break_stmt = break_stmt.where(StructureBreak.formed_at <= as_of)
    confirming_break = (await session.execute(break_stmt.order_by(StructureBreak.formed_at.asc()).limit(1))).scalar_one_or_none()

    if as_of:
        ob_stmt = (
            select(OrderBlock).where(
                OrderBlock.symbol == symbol,
                OrderBlock.timeframe.in_(['H1', 'H4']),
                OrderBlock.formed_at >= sweep_bar.timestamp,
                OrderBlock.formed_at <= as_of,
                OrderBlock.direction == ob_dir,
                or_(OrderBlock.mitigated_at.is_(None), OrderBlock.mitigated_at > as_of)
            )
        )
    else:
        ob_stmt = (
            select(OrderBlock).where(
                OrderBlock.symbol == symbol,
                OrderBlock.timeframe.in_(['H1', 'H4']),
                OrderBlock.formed_at >= sweep_bar.timestamp,
                OrderBlock.direction == ob_dir,
                OrderBlock.mitigated_at.is_(None)
            )
        )
    confirming_ob = (await session.execute(ob_stmt.order_by(OrderBlock.formed_at.asc()).limit(1))).scalar_one_or_none()

    if as_of:
        fvg_stmt = (
            select(FVGZone).where(
                FVGZone.symbol == symbol,
                FVGZone.timeframe.in_(['H1', 'H4']),
                FVGZone.formed_at >= sweep_bar.timestamp,
                FVGZone.formed_at <= as_of,
                FVGZone.direction == ob_dir,
                or_(FVGZone.filled_at.is_(None), FVGZone.filled_at > as_of)
            )
        )
    else:
        fvg_stmt = (
            select(FVGZone).where(
                FVGZone.symbol == symbol,
                FVGZone.timeframe.in_(['H1', 'H4']),
                FVGZone.formed_at >= sweep_bar.timestamp,
                FVGZone.direction == ob_dir,
                FVGZone.filled_at.is_(None)
            )
        )
    confirming_fvg = (await session.execute(fvg_stmt.order_by(FVGZone.formed_at.asc()).limit(1))).scalar_one_or_none()

    confirming = confirming_break or confirming_ob or confirming_fvg
    if confirming:
        basis = 'ChoCH/BOS' if confirming_break else ('Order Block' if confirming_ob else 'FVG')
        volume_confirmed = await _confirm_with_volume(session, symbol, sweep_bar)
        result.update(structure_confirmed=True, valid_for_direction=expected_bias, confirming_structure=basis, volume_confirmed=volume_confirmed)
        result['reasons'].append(f'{sweep_direction} sweep @ {sweep_price:.5f} confirmed by {basis} -> {expected_bias.upper()}')
        if not volume_confirmed:
            result['reasons'].append('Sweep not volume-confirmed (< 1.3x avg H1 volume) — reduced confidence')
    else:
        result['reasons'].append(f'{sweep_direction} sweep detected but NO structural shift yet — not tradeable')
    return result
