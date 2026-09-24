import json
import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import SystemConfig

logger = logging.getLogger('TradingAgent.UnifiedThreshold')

BASE_THRESHOLD = 6
MAX_TOTAL_ADJUSTMENT = 1  # hard cap, cegah threshold jadi tidak achievable


from typing import Optional

async def compute_unified_confluence_threshold(
    session: AsyncSession,
    symbol: str,
    settings: dict,
    stage1_confidence: float | None = None,
    as_of: Optional[datetime] = None,
    is_backtest: bool = False,
) -> tuple[int, str]:
    """
    Satu-satunya sumber kebenaran untuk effective confluence threshold.
    Mengumpulkan SEMUA sinyal adjustment dan mengembalikan SATU angka final.
    """
    from analysis.calculators.adaptive_policy import AdaptiveRiskPolicy
    reasons = []
    penalties = []
    
    # 1. Edge-based base (AdaptiveRiskPolicy)
    policy = AdaptiveRiskPolicy(settings)
    adaptive_base, adaptive_reason = await policy.get_effective_threshold(session, symbol, as_of=as_of)
    reasons.append(f'adaptive_base={adaptive_base}({adaptive_reason})')
    
    # 2. Stage1 confidence
    stage1_conf = stage1_confidence
    if stage1_conf is not None:
        if stage1_conf < 0.25:
            penalties.append((1, f'very_low_macro(brief_confidence={stage1_conf:.0%})'))
            
    # 3. VIX
    try:
        from database.models import VIXData
        vix_stmt = select(VIXData)
        if as_of:
            vix_stmt = vix_stmt.where(VIXData.date <= as_of.date())
        vix_stmt = vix_stmt.order_by(VIXData.date.desc()).limit(1)
        vix_row = (await session.execute(vix_stmt)).scalar_one_or_none()
        if vix_row and vix_row.close > 30:
            penalties.append((1, f'elevated_vix({vix_row.close:.1f})'))
    except Exception:
        pass
        
    # 4. Consecutive SL: check if the last 3 closed trades strictly hit stop-loss
    try:
        from database.models import PaperTradeRecord
        trades_stmt = (
            select(PaperTradeRecord)
            .where(PaperTradeRecord.symbol == symbol)
            .where(PaperTradeRecord.status == 'closed')
        )
        if as_of:
            trades_stmt = trades_stmt.where(PaperTradeRecord.closed_at <= as_of)
        trades_stmt = trades_stmt.order_by(PaperTradeRecord.closed_at.desc()).limit(3)
        recent_trades = (await session.execute(trades_stmt)).scalars().all()
        if len(recent_trades) == 3 and all(t.exit_reason == 'sl_hit' for t in recent_trades):
            penalties.append((1, f'3_consecutive_sl_hits({symbol})'))
    except Exception:
        pass
        
    # 5. Deterministic ADX/Regime penalty
    regime_modifier = 0
    try:
        from analysis.calculators.regime_classifier import classify_market_regime
        regime = await classify_market_regime(session, symbol, settings, as_of=as_of)
        regime_modifier = max(-1, min(2, regime['threshold_modifier']))
        reasons.append(
            f"regime={regime['regime']}(quality={regime['composite_quality']:.2f}, "
            f"adx={regime.get('adx')}, vol_ratio={regime.get('vol_ratio')}, "
            f"vix={regime.get('vix')}) -> modifier={regime_modifier:+d}"
        )
    except Exception as e:
        logger.debug(f'Regime classification failed for threshold adjustment: {e}')
        
    # Total positive penalties (including positive regime modifier) capped at MAX_TOTAL_ADJUSTMENT
    positive_penalties = sum(d for d, r in penalties) + max(0, regime_modifier)
    capped_penalty = min(positive_penalties, MAX_TOTAL_ADJUSTMENT)
    for d, r in penalties:
        reasons.append(f'{r}(+{d})')
    if positive_penalties > MAX_TOTAL_ADJUSTMENT:
        reasons.append(f'penalty_capped(max=+{MAX_TOTAL_ADJUSTMENT})')
        
    final_threshold = adaptive_base + capped_penalty
    if regime_modifier < 0:
        final_threshold += regime_modifier
    
    # 5. Inflation floor
    try:
        cfg = (
            await session.execute(select(SystemConfig).where(SystemConfig.key == 'score_inflation_correction_threshold'))
        ).scalar_one_or_none()
        if cfg and cfg.value:
            data = json.loads(cfg.value)
            set_at = datetime.fromisoformat(data['set_at'])
            if set_at.tzinfo is None:
                set_at = set_at.replace(tzinfo=timezone.utc)
            now = as_of or datetime.now(timezone.utc)
            if (now - set_at).days < data.get('expires_days', 7):
                inflation_floor = data.get('threshold', BASE_THRESHOLD)
                if final_threshold < inflation_floor:
                    final_threshold = inflation_floor
                    reasons.append(f'inflation_floor={inflation_floor}')
    except Exception:
        pass
        
    final_threshold = max(5, min(final_threshold, 7))  # FIX: hard ceiling 7 (was 8)
    
    reasoning = (
        f'Base=6, adjustments=[{", ".join(reasons)}], '
        f'FINAL THRESHOLD={final_threshold}/14'
    )
    if is_backtest or as_of is not None:
        logger.debug(f'[{symbol}] Unified threshold: {reasoning}')
    else:
        logger.info(f'[{symbol}] Unified threshold: {reasoning}')
    return (final_threshold, reasoning)
