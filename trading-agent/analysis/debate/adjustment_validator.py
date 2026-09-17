import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import TechnicalIndicator, AssetAnalysis

logger = logging.getLogger('TradingAgent.AdjustmentValidator')


async def validate_and_apply_judge_adjustments(
    session: AsyncSession,
    ana: AssetAnalysis,
    verdict: dict,
    settings: dict,
    entry_zone_data: dict,
) -> tuple[bool, str]:
    """Re-validasi SL/TP/entry hasil adjustment Investment Judge terhadap aturan
    struktural yang sama seperti saat submit_asset_analysis (min R:R, min ATR
    multiplier, max entry deviation). Judge TIDAK punya akses tool untuk verifikasi
    ulang ATR — validasi mekanis ini wajib ada di sisi backend sebelum nilai
    di-persist, karena Judge bisa saja mengusulkan SL yang secara matematis
    melanggar risk management meskipun argumennya terdengar masuk akal secara teks.
    """
    adjusted_entry = verdict.get('adjusted_entry')
    adjusted_sl = verdict.get('adjusted_sl')
    adjusted_tp = verdict.get('adjusted_tp')

    if adjusted_entry is None and adjusted_sl is None and adjusted_tp is None:
        return True, ''  # tidak ada adjustment untuk divalidasi

    original_price = entry_zone_data.get('price') or ana.price_at_analysis
    new_entry = float(adjusted_entry) if adjusted_entry is not None else original_price
    new_sl = float(adjusted_sl) if adjusted_sl is not None else ana.stop_loss
    new_tp = float(adjusted_tp) if adjusted_tp is not None else ana.take_profit

    if not new_entry or not new_sl or not new_tp:
        return False, 'Judge adjustment tidak lengkap (entry/sl/tp referensi hilang)'

    sl_dist = abs(new_entry - new_sl)
    tp_dist = abs(new_entry - new_tp)
    if sl_dist <= 0:
        return False, 'Judge SL distance = 0'

    rr = tp_dist / sl_dist
    min_rr = float(settings.get('trading', {}).get('risk', {}).get('min_rr_ratio', 1.3))
    if rr < min_rr:
        return False, f'Judge-adjusted R:R={rr:.2f} di bawah minimum {min_rr}'

    atr_row = (await session.execute(
        select(TechnicalIndicator)
        .where(TechnicalIndicator.symbol == ana.symbol)
        .where(TechnicalIndicator.timeframe == 'H4')
        .where(TechnicalIndicator.indicator_name == 'ATR_14')
        .order_by(TechnicalIndicator.timestamp.desc())
        .limit(1)
    )).scalar_one_or_none()

    if atr_row:
        raw_atr = json.loads(atr_row.value_json)
        atr_val = float(raw_atr.get('atr', raw_atr.get('value', 0))) if isinstance(raw_atr, dict) else float(raw_atr or 0)
        risk_cfg = settings.get('trading', {}).get('risk', {})
        mult_map = risk_cfg.get('min_sl_atr_multiplier_by_symbol', {})
        min_mult = mult_map.get(ana.symbol, mult_map.get('default', 1.0))
        if atr_val > 0 and sl_dist < atr_val * min_mult:
            return False, (
                f'Judge-adjusted SL distance {sl_dist:.5f} < {min_mult}x ATR ({atr_val:.5f}). '
                f'Kemungkinan SL akan kena noise volatilitas normal.'
            )

    try:
        from analysis.calculators.daily_range_calculator import compute_daily_range_context
        adr_ctx = await compute_daily_range_context(session, ana.symbol, settings)
        if 'error' not in adr_ctx:
            tol = adr_ctx.get('band_tolerance_pct', 0.10)
            tp_min = adr_ctx['target_tp_min_distance'] * (1 - tol)
            tp_max = adr_ctx['target_tp_max_distance'] * (1 + tol)
            sl_max = adr_ctx['target_sl_max_distance'] * (1 + tol)
            if tp_dist < tp_min or tp_dist > tp_max:
                return (False, f"Judge-adjusted TP distance {tp_dist:.5f} di luar target band intraday-range [{tp_min:.5f}, {tp_max:.5f}] (ADR={adr_ctx['adr']:.5f}).")
            if sl_dist > sl_max:
                return (False, f"Judge-adjusted SL distance {sl_dist:.5f} melebihi batas maksimum intraday-range {sl_max:.5f} (35% ADR).")
    except Exception as e:
        logger.debug(f"ADR validation in adjustment_validator failed (non-fatal): {e}")

    if original_price and original_price > 0:
        deviation_pct = abs(new_entry - original_price) / original_price * 100
        if deviation_pct > 3.0:
            return False, (
                f'Judge-adjusted entry deviasi {deviation_pct:.1f}% dari harga analisis '
                f'asli (maks 3%). Kemungkinan Judge memakai harga stale/halusinasi.'
            )

    return True, ''
