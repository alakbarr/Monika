import json
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import OrderBlock, FVGZone, SRZone, SwingPoint, LiquidityZone, TechnicalIndicator
from analysis.calculators.daily_range_calculator import compute_daily_range_context

logger = logging.getLogger('TradingAgent.IntradayLevelOptimizer')

ZONE_WEIGHTS = {'order_block': 3.0, 'fvg': 2.5, 'sr_zone': 2.0, 'liquidity': 1.5, 'swing': 1.0}


from utils.validation.indicator_sanitizer import safe_float

async def _get_atr(session: AsyncSession, symbol: str) -> float:
    row = (await session.execute(
        select(TechnicalIndicator).where(TechnicalIndicator.symbol == symbol)
        .where(TechnicalIndicator.timeframe == 'H4').where(TechnicalIndicator.indicator_name == 'ATR_14')
        .order_by(TechnicalIndicator.timestamp.desc()).limit(1)
    )).scalar_one_or_none()
    if not row:
        return 0.0
    try:
        raw = json.loads(row.value_json)
        val = raw.get('atr', raw.get('value', 0)) if isinstance(raw, dict) else raw
        res = safe_float(val, 0.0)
        return float(res) if res is not None else 0.0
    except Exception:
        return 0.0


async def _collect_zones(session: AsyncSession, symbol: str) -> list[dict]:
    zones = []
    obs = (await session.execute(select(OrderBlock).where(
        OrderBlock.symbol == symbol, OrderBlock.timeframe == 'H4', OrderBlock.mitigated_at == None))).scalars().all()
    for ob in obs:
        zones.append({'type': 'order_block', 'direction': ob.direction, 'low': ob.price_low,
                       'high': ob.price_high, 'weight': ZONE_WEIGHTS['order_block']})

    fvgs = (await session.execute(select(FVGZone).where(
        FVGZone.symbol == symbol, FVGZone.timeframe == 'H4', FVGZone.filled_at == None))).scalars().all()
    for fvg in fvgs:
        zones.append({'type': 'fvg', 'direction': fvg.direction, 'low': fvg.gap_low,
                       'high': fvg.gap_high, 'weight': ZONE_WEIGHTS['fvg']})

    srs = (await session.execute(select(SRZone).where(
        SRZone.symbol == symbol, SRZone.timeframe.in_(['H4', 'D1'])))).scalars().all()
    for sr in srs:
        w = ZONE_WEIGHTS['sr_zone'] * min(1.5, sr.strength / 2.0)
        zones.append({'type': 'sr_zone', 'direction': None, 'low': sr.price_low, 'high': sr.price_high, 'weight': w})

    liqs = (await session.execute(select(LiquidityZone).where(
        LiquidityZone.symbol == symbol, LiquidityZone.timeframe == 'H4'))).scalars().all()
    for lz in liqs:
        zones.append({'type': 'liquidity', 'direction': lz.type, 'low': lz.zone_low,
                       'high': lz.zone_high, 'weight': ZONE_WEIGHTS['liquidity']})

    swings = (await session.execute(select(SwingPoint).where(
        SwingPoint.symbol == symbol, SwingPoint.timeframe == 'H4')
        .order_by(SwingPoint.timestamp.desc()).limit(12))).scalars().all()
    for sw in swings:
        zones.append({'type': 'swing', 'direction': sw.type, 'low': sw.price, 'high': sw.price,
                       'weight': ZONE_WEIGHTS['swing']})
    return zones


def _score_candidate(distance: float, mid_band: float, band_width: float, weight: float) -> float:
    if band_width <= 0:
        proximity_score = 0.0
    else:
        proximity_score = max(0.0, 1.0 - abs(distance - mid_band) / band_width)
    return round(weight * (0.5 + 0.5 * proximity_score), 3)


async def compute_optimal_levels(
    session: AsyncSession,
    symbol: str,
    direction: str,
    entry_price: float,
    settings: dict,
    existing_sl: Optional[float] = None,
    existing_tp: Optional[float] = None,
) -> dict:
    adr_ctx = await compute_daily_range_context(session, symbol, settings)
    if 'error' in adr_ctx:
        return {'error': adr_ctx['error']}

    atr = await _get_atr(session, symbol)
    zones = await _collect_zones(session, symbol)
    try:
        from analysis.calculators.liquidity_sweep_detector import detect_liquidity_sweep
        sweep = await detect_liquidity_sweep(session, symbol, settings)
        if sweep.get('sweep_detected') and sweep.get('sweep_price'):
            pad = (atr * 0.15) if atr else abs(sweep['sweep_price']) * 0.0005
            zones.append({'type': 'liquidity_sweep', 'direction': sweep.get('valid_for_direction'),
                           'low': sweep['sweep_price'] - pad, 'high': sweep['sweep_price'] + pad,
                           'weight': ZONE_WEIGHTS.get('liquidity', 1.5) * 1.3})
    except Exception:
        pass
    risk_cfg = (settings or {}).get('trading', {}).get('risk', {})
    min_rr = float(risk_cfg.get('min_rr_ratio', 1.3))
    mult_map = risk_cfg.get('min_sl_atr_multiplier_by_symbol', {})
    min_sl_mult = mult_map.get(symbol, mult_map.get('default', 1.0))

    tp_min, tp_max = adr_ctx['target_tp_min_distance'], adr_ctx['target_tp_max_distance']
    sl_max = adr_ctx['target_sl_max_distance']
    tp_mid, tp_width = (tp_min + tp_max) / 2.0, max(tp_max - tp_min, 1e-9)

    # TimesFM 3.0 Reachability Integration
    tfm_forecast = None
    try:
        from indicators.timesfm_engine import TimesFMEngine
        tfm_engine = TimesFMEngine(settings)
        tfm_forecast = await tfm_engine.get_latest_forecast(session, symbol, timeframe='H1', max_age_hours=8.0)
    except Exception as tfm_err:
        logger.debug(f"[{symbol}] TimesFM lookup in level optimizer failed (non-fatal): {tfm_err}")

    q10_target = None
    q90_target = None
    if tfm_forecast and "quantiles" in tfm_forecast:
        q_dict = tfm_forecast["quantiles"]
        if "q10" in q_dict and q_dict["q10"]:
            q10_target = float(q_dict["q10"][-1])
        if "q90" in q_dict and q_dict["q90"]:
            q90_target = float(q_dict["q90"][-1])

    tp_candidates, sl_candidates = [], []

    # Priority candidate if caller provides prescribed SL
    if existing_sl is not None:
        try:
            ex_sl = float(existing_sl)
            dist_sl = (entry_price - ex_sl) if direction == 'buy' else (ex_sl - entry_price)
            if dist_sl > 0:
                sl_candidates.append({
                    'price': round(ex_sl, 5),
                    'distance': round(dist_sl, 5),
                    'basis': 'signal_prescribed_sl',
                    'score': 10.0
                })
        except (ValueError, TypeError):
            pass

    # Priority candidate if caller provides prescribed TP
    if existing_tp is not None:
        try:
            ex_tp = float(existing_tp)
            dist_tp = (ex_tp - entry_price) if direction == 'buy' else (entry_price - ex_tp)
            if dist_tp > 0:
                tp_candidates.append({
                    'price': round(ex_tp, 5),
                    'distance': round(dist_tp, 5),
                    'basis': 'signal_prescribed_tp',
                    'score': 10.0
                })
        except (ValueError, TypeError):
            pass

    for z in zones:
        z_near_edge = z['high'] if direction == 'buy' else z['low']
        z_far_edge = z['low'] if direction == 'buy' else z['high']

        dist_to_far = (z_far_edge - entry_price) if direction == 'buy' else (entry_price - z_far_edge)
        if tp_min * 0.85 <= dist_to_far <= tp_max * 1.05 and dist_to_far > 0:
            score = _score_candidate(dist_to_far, tp_mid, tp_width, z['weight'])
            # TimesFM Reachability multiplier: boost if within Q10-Q90 cone, penalize if beyond
            if direction == 'buy' and q90_target:
                if z_far_edge <= q90_target:
                    score = round(score * 1.25, 3)
                else:
                    score = round(score * 0.50, 3)  # Overextended target penalty
            elif direction == 'sell' and q10_target:
                if z_far_edge >= q10_target:
                    score = round(score * 1.25, 3)
                else:
                    score = round(score * 0.50, 3)  # Overextended target penalty

            tp_candidates.append({'price': round(z_far_edge, 5), 'distance': round(dist_to_far, 5),
                                   'basis': f"{z['type']}({z.get('direction') or 'n/a'})", 'score': score})

        dist_to_near = (entry_price - z_near_edge) if direction == 'buy' else (z_near_edge - entry_price)
        if atr > 0 and atr * min_sl_mult <= dist_to_near <= sl_max * 1.05 and dist_to_near > 0:
            score = _score_candidate(dist_to_near, sl_max * 0.5, sl_max, z['weight'])
            sl_candidates.append({'price': round(z_near_edge, 5), 'distance': round(dist_to_near, 5),
                                   'basis': f"{z['type']}({z.get('direction') or 'n/a'})", 'score': score})

    tp_candidates.sort(key=lambda x: x['score'], reverse=True)
    sl_candidates.sort(key=lambda x: x['score'], reverse=True)

    fallback_tp = entry_price + tp_mid if direction == 'buy' else entry_price - tp_mid
    fallback_sl_dist = min(sl_max, max(atr * min_sl_mult, sl_max * 0.5))
    fallback_sl = entry_price - fallback_sl_dist if direction == 'buy' else entry_price + fallback_sl_dist

    if not tp_candidates:
        tp_candidates.append({'price': round(fallback_tp, 5), 'distance': round(tp_mid, 5),
                              'basis': 'adr_band_midpoint_no_structure_found', 'score': 0.0})
    if not sl_candidates:
        sl_candidates.append({'price': round(fallback_sl, 5), 'distance': round(fallback_sl_dist, 5),
                              'basis': 'adr_band_fallback_no_structure_found', 'score': 0.0})

    # R:R Pairing: Find pairs that satisfy tp_dist / sl_dist >= min_rr
    valid_pairs = []
    for tp in tp_candidates:
        for sl in sl_candidates:
            if sl['distance'] <= 0:
                continue
            rr = tp['distance'] / sl['distance']
            if rr >= min_rr:
                valid_pairs.append({
                    'tp': tp,
                    'sl': sl,
                    'rr': round(rr, 2),
                    'score': round(tp['score'] + sl['score'], 3)
                })

    entry_allowed = adr_ctx.get('entry_allowed', True)
    rejection_reason = None

    if valid_pairs:
        valid_pairs.sort(key=lambda p: (p['score'], p['rr']), reverse=True)
        best_tp = valid_pairs[0]['tp']
        best_sl = valid_pairs[0]['sl']
        tp_candidates = [best_tp] + [t for t in tp_candidates if t['price'] != best_tp['price']]
        sl_candidates = [best_sl] + [s for s in sl_candidates if s['price'] != best_sl['price']]
    else:
        # No structural pair meets min_rr.
        # Fallback A: Synthesize TP based on best SL candidate if ADR room permits
        best_sl = sl_candidates[0]
        sl_dist = best_sl['distance']
        req_tp_dist = round(sl_dist * min_rr, 5)
        max_allowed_tp_dist = adr_ctx.get('target_tp_max_distance', adr_ctx.get('adr', 0.0) * 0.8)
        room_pct = adr_ctx.get('room_remaining_pct', 1.0)

        if req_tp_dist <= max_allowed_tp_dist * 1.15 and room_pct >= 0.20:
            synthetic_tp_price = round(entry_price + req_tp_dist if direction == 'buy' else entry_price - req_tp_dist, 5)
            synthetic_tp = {
                'price': synthetic_tp_price,
                'distance': req_tp_dist,
                'basis': 'synthetic_min_rr_adr_target',
                'score': 0.5
            }
            tp_candidates = [synthetic_tp] + tp_candidates
        else:
            entry_allowed = False
            rejection_reason = 'insufficient_rr_within_adr'

    top_tp = tp_candidates[:3]
    top_sl = sl_candidates[:3]
    selected_rr = round(top_tp[0]['distance'] / max(top_sl[0]['distance'], 1e-9), 2) if top_tp and top_sl else 0.0

    res = {
        'symbol': symbol, 'direction': direction, 'entry_price': entry_price,
        'adr': adr_ctx['adr'], 'volatility_regime': adr_ctx.get('volatility_regime', 'normal'),
        'room_remaining_pct': adr_ctx.get('room_remaining_pct'),
        'entry_allowed': entry_allowed,
        'min_rr_ratio': min_rr,
        'selected_rr': selected_rr,
        'top_tp_candidates': top_tp,
        'top_sl_candidates': top_sl,
        'instruction': ('Prefer the highest-scored candidate for both TP and SL. If no candidate scores '
                         '> 0, no valid structural intraday setup exists right now — prefer WAIT.')
    }
    if not entry_allowed and rejection_reason:
        res['rejection_reason'] = rejection_reason
    return res
