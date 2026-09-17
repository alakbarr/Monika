import logging
import math
import json
from typing import Optional, Tuple, List, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import PaperTradeRecord, AssetAnalysis, SystemConfig

logger = logging.getLogger('TradingAgent.ConfidenceCalibrator')


def fit_platt_scaling(confidences: List[float], outcomes: List[int], max_iter: int = 100) -> Tuple[float, float]:
    """
    Fits logistic sigmoid parameters A and B using Newton-Raphson method with Platt's bayesian prior.
    Formula: P(Y=1 | z) = 1 / (1 + exp(-(A*z + B)))
    """
    n = len(confidences)
    if n == 0:
        return 1.0, 0.0
    n_pos = sum(outcomes)
    n_neg = n - n_pos

    # Bayes Laplace Platt target probabilities prior
    t_pos = (n_pos + 1.0) / (n_pos + 2.0)
    t_neg = 1.0 / (n_neg + 2.0)
    targets = [t_pos if y == 1 else t_neg for y in outcomes]

    # Initialize A and B
    a = 0.0
    b = math.log((n_neg + 1.0) / (n_pos + 1.0)) if (n_pos + 1.0) > 0 else 0.0

    for _ in range(max_iter):
        g1 = 0.0
        g2 = 0.0
        h11 = 1e-12
        h22 = 1e-12
        h12 = 0.0

        for z, t in zip(confidences, targets):
            # Clamped sigmoid input to avoid overflow
            val = max(-30.0, min(30.0, a * z + b))
            p = 1.0 / (1.0 + math.exp(-val))
            d1 = p - t
            d2 = max(1e-15, p * (1.0 - p))
            g1 += z * d1
            g2 += d1
            h11 += z * z * d2
            h22 += d2
            h12 += z * d2

        det = h11 * h22 - h12 * h12
        if abs(det) < 1e-15:
            break
        delta_a = -(g1 * h22 - g2 * h12) / det
        delta_b = -(g2 * h11 - g1 * h12) / det

        a += delta_a
        b += delta_b
        if abs(delta_a) < 1e-5 and abs(delta_b) < 1e-5:
            break

    return round(a, 4), round(b, 4)


def fit_isotonic_pav(confidences: List[float], outcomes: List[int]) -> List[Dict[str, float]]:
    """
    Pool-Adjacent-Violators (PAV) algorithm for non-parametric isotonic regression.
    Produces piecewise constant, monotonically non-decreasing calibrated probability mapping.
    """
    if not confidences:
        return []
    # Sort pairs by confidence ascending
    pairs = sorted(zip(confidences, outcomes), key=lambda x: x[0])
    
    # Initialize blocks: (weight, sum_y, min_x, max_x)
    blocks = []
    for x, y in pairs:
        blocks.append({'w': 1.0, 'sum_y': float(y), 'min_x': float(x), 'max_x': float(x), 'mean_y': float(y)})

    # Pool adjacent violators
    i = 0
    while i < len(blocks) - 1:
        if blocks[i]['mean_y'] > blocks[i + 1]['mean_y']:
            # Pool blocks i and i+1
            b1 = blocks[i]
            b2 = blocks[i + 1]
            new_w = b1['w'] + b2['w']
            new_sum = b1['sum_y'] + b2['sum_y']
            pooled = {
                'w': new_w,
                'sum_y': new_sum,
                'min_x': min(b1['min_x'], b2['min_x']),
                'max_x': max(b1['max_x'], b2['max_x']),
                'mean_y': new_sum / new_w
            }
            blocks[i] = pooled
            blocks.pop(i + 1)
            # Step back to check previous violator
            if i > 0:
                i -= 1
        else:
            i += 1

    return [{'min_x': round(b['min_x'], 4), 'max_x': round(b['max_x'], 4), 'calibrated_prob': round(b['mean_y'], 4)} for b in blocks]


def calibrate_probability(raw_conf: float, platt_params: Optional[Tuple[float, float]] = None, pav_bins: Optional[List[Dict[str, float]]] = None) -> float:
    """
    Evaluates calibrated probability from raw model confidence using Platt Scaling or Isotonic PAV.
    """
    raw_conf = max(0.0, min(1.0, float(raw_conf)))
    if platt_params:
        a, b = platt_params
        val = max(-30.0, min(30.0, a * raw_conf + b))
        return round(1.0 / (1.0 + math.exp(-val)), 4)

    if pav_bins:
        for b in pav_bins:
            if b['min_x'] <= raw_conf <= b['max_x']:
                return b['calibrated_prob']
        if raw_conf < pav_bins[0]['min_x']:
            return pav_bins[0]['calibrated_prob']
        if raw_conf > pav_bins[-1]['max_x']:
            return pav_bins[-1]['calibrated_prob']

    return raw_conf


async def compute_confidence_calibration(session: AsyncSession) -> dict:
    records = (await session.execute(
        select(PaperTradeRecord, AssetAnalysis)
        .outerjoin(AssetAnalysis, PaperTradeRecord.analysis_id == AssetAnalysis.id)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
        .where(AssetAnalysis.confidence.isnot(None))
    )).all()

    if len(records) < 20:
        return {'status': 'insufficient_data', 'count': len(records), 'total_analyzed': len(records)}

    confidences = []
    outcomes = []
    bands = {
        '0.60-0.65': {'wins': 0, 'total': 0},
        '0.65-0.70': {'wins': 0, 'total': 0},
        '0.70-0.75': {'wins': 0, 'total': 0},
        '0.75-0.80': {'wins': 0, 'total': 0},
        '0.80+': {'wins': 0, 'total': 0}
    }

    for record, analysis in records:
        if not analysis or analysis.confidence is None:
            continue
        conf = float(analysis.confidence)
        is_win = 1 if record.exit_reason == 'tp_hit' else 0
        confidences.append(conf)
        outcomes.append(is_win)

        if conf < 0.65:
            key = '0.60-0.65'
        elif conf < 0.7:
            key = '0.65-0.70'
        elif conf < 0.75:
            key = '0.70-0.75'
        elif conf < 0.8:
            key = '0.75-0.80'
        else:
            key = '0.80+'
        bands[key]['total'] += 1
        if is_win:
            bands[key]['wins'] += 1

    # Fit formal statistical models
    platt_a, platt_b = fit_platt_scaling(confidences, outcomes)
    pav_bins = fit_isotonic_pav(confidences, outcomes)

    # Multi-regime partitioned calibration (Trending vs Ranging)
    trending_confs, trending_outcomes = [], []
    ranging_confs, ranging_outcomes = [], []
    for record, analysis in records:
        if not analysis or analysis.confidence is None:
            continue
        c = float(analysis.confidence)
        y = 1 if record.exit_reason == 'tp_hit' else 0
        regime_str = str(getattr(analysis, 'market_regime', '') or '').lower()
        if any(k in regime_str for k in ['trend', 'donchian', 'momentum', 'expansion']):
            trending_confs.append(c)
            trending_outcomes.append(y)
        elif any(k in regime_str for k in ['range', 'reversion', 'chop', 'ranging']):
            ranging_confs.append(c)
            ranging_outcomes.append(y)

    regime_models = {}
    if len(trending_confs) >= 25:
        t_a, t_b = fit_platt_scaling(trending_confs, trending_outcomes)
        regime_models["trending"] = {"platt_scaling": {"a": t_a, "b": t_b}, "sample_size": len(trending_confs)}
    if len(ranging_confs) >= 25:
        r_a, r_b = fit_platt_scaling(ranging_confs, ranging_outcomes)
        regime_models["ranging"] = {"platt_scaling": {"a": r_a, "b": r_b}, "sample_size": len(ranging_confs)}

    # Hitung Expected Calibration Error (ECE) dan Brier Score
    brier_scores = []
    ece_weighted_diff = 0.0
    total_valid = len(confidences)

    band_midpoints = {
        '0.60-0.65': 0.625,
        '0.65-0.70': 0.675,
        '0.70-0.75': 0.725,
        '0.75-0.80': 0.775,
        '0.80+': 0.850,
    }

    for c, o in zip(confidences, outcomes):
        brier_scores.append((c - float(o)) ** 2)

    brier_score = round(sum(brier_scores) / total_valid, 4) if total_valid > 0 else 0.0

    result = {}
    for band, data in bands.items():
        if data['total'] > 0:
            wr = data['wins'] / data['total'] * 100
            acc = data['wins'] / data['total']
            conf_mid = band_midpoints.get(band, 0.7)
            ece_weighted_diff += (data['total'] / total_valid) * abs(acc - conf_mid)
            result[band] = {'win_rate': round(wr, 1), 'total': data['total'], 'calibrated': wr >= 40.0 and data['total'] >= 5}

    ece_score = round(ece_weighted_diff, 4) if total_valid > 0 else 0.0
    bands_with_data = [(k, v) for k, v in result.items() if v['total'] >= 3]
    is_monotonic = all((bands_with_data[i][1]['win_rate'] <= bands_with_data[i + 1][1]['win_rate'] for i in range(len(bands_with_data) - 1))) if len(bands_with_data) > 1 else False

    if not bands_with_data or len(bands_with_data) < 2:
        status = 'insufficient_data'
        recommendation = 'MAINTAIN'
    elif is_monotonic:
        status = 'calibrated'
        recommendation = 'MAINTAIN'
    else:
        status = 'calibrated'
        highest_band = bands_with_data[-1]
        lowest_band = bands_with_data[0]
        if highest_band[1]['win_rate'] < lowest_band[1]['win_rate']:
            recommendation = 'RAISE_THRESHOLD'
        else:
            recommendation = 'REVIEW_ONLY'

    return {
        'status': status,
        'bands': result,
        'ece': ece_score,
        'brier_score': brier_score,
        'platt_scaling': {'a': platt_a, 'b': platt_b},
        'isotonic_pav_bins': pav_bins,
        'regime_models': regime_models,
        'confidence_is_calibrated': is_monotonic,
        'recommendation': recommendation,
        'total_analyzed': total_valid,
    }


async def get_calibrated_confidence(session: AsyncSession, raw_conf: float, regime: Optional[str] = None) -> float:
    """Reads saved Platt parameters from SystemConfig and returns calibrated probability."""
    if not session:
        return round(min(raw_conf - 0.05, 0.65), 4) if raw_conf >= 0.50 else round(max(raw_conf - 0.05, 0.0), 4)
    try:
        res = await session.execute(select(SystemConfig).where(SystemConfig.key == 'calibration_model_params'))
        cfg = res.scalar_one_or_none() if hasattr(res, 'scalar_one_or_none') else None
        if cfg and hasattr(cfg, 'value') and isinstance(cfg.value, str):
            params = json.loads(cfg.value)
            # Check regime-specific model first if available
            if regime:
                reg_key = "trending" if any(k in regime.lower() for k in ["trend", "momentum", "expansion"]) else "ranging"
                reg_model = params.get("regime_models", {}).get(reg_key, {}).get("platt_scaling")
                if reg_model and "a" in reg_model and "b" in reg_model:
                    return calibrate_probability(raw_conf, platt_params=(float(reg_model["a"]), float(reg_model["b"])))
            
            platt = params.get('platt_scaling')
            if platt and 'a' in platt and 'b' in platt:
                return calibrate_probability(raw_conf, platt_params=(float(platt['a']), float(platt['b'])))
    except Exception:
        pass
    # Fallback saat N < 60 atau calibration params belum ada:
    # Terapkan conservative discount agar overconfidence LLM tidak langsung meloloskan live trade
    if raw_conf >= 0.50:
        return round(min(raw_conf - 0.05, 0.65), 4)
    return round(max(raw_conf - 0.05, 0.0), 4)


async def apply_calibration_correction(session: AsyncSession, settings: dict) -> None:
    res = await compute_confidence_calibration(session)
    if res.get('total_analyzed', 0) < 60:
        logger.info(f"[ConfidenceCalibrator] Sample size ({res.get('total_analyzed', 0)}/60) insufficient for auto-correction.")
        return

    # Persist calibration parameters for runtime inference
    calib_cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == 'calibration_model_params'))).scalar_one_or_none()
    params_payload = json.dumps({
        'platt_scaling': res.get('platt_scaling'),
        'isotonic_pav_bins': res.get('isotonic_pav_bins'),
        'regime_models': res.get('regime_models', {}),
        'ece': res.get('ece'),
        'brier_score': res.get('brier_score'),
        'total_analyzed': res.get('total_analyzed')
    })
    if calib_cfg:
        calib_cfg.value = params_payload
    else:
        session.add(SystemConfig(key='calibration_model_params', value=params_payload))
    await session.commit()

    if res.get('status') == 'calibrated' and res.get('recommendation') == 'RAISE_THRESHOLD':
        key = 'auto_execute_min_confidence_override'
        cfg = (await session.execute(select(SystemConfig).where(SystemConfig.key == key))).scalar_one_or_none()
        current = float(cfg.value) if cfg and cfg.value else settings.get('trading', {}).get('auto_execute_min_confidence', 0.6)
        new_val = min(0.8, current + 0.05)
        if cfg:
            cfg.value = str(new_val)
        else:
            session.add(SystemConfig(key=key, value=str(new_val)))
        await session.commit()
        logger.warning(f'[ConfidenceCalibrator] Confidence tidak terkalibrasi (ECE={res.get("ece")}, Brier={res.get("brier_score")}). '
                        f'auto_execute_min_confidence dinaikkan: {current} -> {new_val}')
