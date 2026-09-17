# ==============================================================================
# File: analysis/stages/per_asset/verifiers.py
# ==============================================================================

import asyncio
import logging
import json
import sys
from datetime import datetime, timezone
from typing import Optional, Any, Callable, Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import utils.clock as clock

logger = logging.getLogger("TradingAgent.PerAsset.Verifiers")

def _get_clock():
    pas = sys.modules.get("analysis.stages.per_asset_stage")
    if pas and hasattr(pas, "clock"):
        return pas.clock
    return clock


async def _get_symbol_sl_streak(session, symbol: str) -> int:
    from database.models import PaperTradeRecord
    from sqlalchemy import select
    recent = (await session.execute(
        select(PaperTradeRecord).where(PaperTradeRecord.symbol == symbol)
        .where(PaperTradeRecord.status == 'closed')
        .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
        .order_by(PaperTradeRecord.closed_at.desc()).limit(3)
    )).scalars().all()
    streak = 0
    for r in recent:
        if r.exit_reason == 'sl_hit':
            streak += 1
        else:
            break
    return streak


class VerifiersMixin:
    """Mixin untuk verifikasi kualitas data, currency, dan koherensi SSVP."""

    settings: Dict[str, Any]

    async def _get_symbol_sl_streak(self, session: AsyncSession, symbol: str) -> int:
        return await _get_symbol_sl_streak(session, symbol)

    async def _check_brief_freshness_and_quality(
        self, session: AsyncSession, symbol: str, start_time: datetime
    ) -> tuple[Optional[dict], Optional[Any], list[tuple[str, str]]]:
        """Memeriksa keberadaan, kesegaran, dan kualitas FundamentalBrief."""
        from database.models import FundamentalBrief
        from sqlalchemy import select

        context_blocks: list[tuple[str, str]] = []
        brief_check = (await session.execute(
            select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
        )).scalar_one_or_none()

        if brief_check and brief_check.structured_json:
            try:
                _bd = json.loads(brief_check.structured_json)
                if _bd.get('_data_quality_degraded'):
                    logger.warning(f'[{symbol}] Fundamental brief flagged degraded quality. Forcing conservative posture.')
                    context_blocks.append((
                        'BRIEF QUALITY WARNING',
                        'The current fundamental brief FAILED structural validation twice and was '
                        'force-accepted with a hard confidence cap (<=0.35). Treat currency_bias and '
                        'macro_narrative as LOW-TRUST context. Weight technical/price-action evidence '
                        f"more heavily than macro bias this cycle. Known issues: "
                        f"{'; '.join(_bd.get('_degradation_reasons', [])[:3])}"
                    ))
            except Exception:
                pass

        MAX_BRIEF_AGE_FOR_STAGE2 = float(
            self.settings.get('data_quality', {}).get('max_stage2_brief_age_hours')
            or self.settings.get('data_quality', {}).get('max_brief_age_analysis_hours', 12.0)
        )
        if brief_check:
            brief_age_h = (start_time - brief_check.generated_at.replace(tzinfo=timezone.utc) if brief_check.generated_at.tzinfo is None else start_time - brief_check.generated_at).total_seconds() / 3600
            
            if brief_age_h > MAX_BRIEF_AGE_FOR_STAGE2 * 0.7:
                logger.warning(
                    f'[{symbol}] Brief aging ({brief_age_h:.1f}h of {MAX_BRIEF_AGE_FOR_STAGE2}h limit). '
                    f'Consider prioritizing this analysis.'
                )

            if brief_age_h > MAX_BRIEF_AGE_FOR_STAGE2:
                logger.warning(
                    f'[{symbol}] Fundamental brief is {brief_age_h:.1f}h old '
                    f'(limit: {MAX_BRIEF_AGE_FOR_STAGE2}h). '
                    f'Submitting WAIT to preserve decision quality.'
                )
                return {
                    'success': True,
                    'symbol': symbol,
                    'decision': 'wait',
                    'confidence': 0.0,
                    'rationale': f'Fundamental brief too stale ({brief_age_h:.1f}h). Awaiting next Stage 1 cycle.',
                    'analysis_id': None,
                    'elapsed_seconds': 0,
                    'skipped_by_brief_staleness': True
                }, brief_check, context_blocks
        elif brief_check is None:
            logger.warning(f'[{symbol}] No fundamental brief exists. Skipping Stage 2.')
            return {
                'success': True,
                'symbol': symbol,
                'decision': 'wait',
                'confidence': 0.0,
                'rationale': 'No fundamental brief available. Stage 1 must run first.',
                'analysis_id': None,
                'elapsed_seconds': 0,
                'skipped_no_brief': True
            }, None, context_blocks

        return None, brief_check, context_blocks

    async def _compute_ssvp_coherence(self, session: AsyncSession, symbol: str, brief_check: Optional[Any]) -> str:
        """Memeriksa koherensi konteks SSVP untuk mencegah drift/kontaminasi."""
        coherence_injection = ''
        try:
            from utils.protocol.enhanced_cds import compute_composite_cds, get_cds_thresholds
            from utils.protocol.brief_contamination_guard import _build_warning_context, _build_contextmerge_prompt
            import json as _j
            from database.models import SystemConfig
            from database.db import get_session
            
            if brief_check and brief_check.structured_json:
                b_data = _j.loads(brief_check.structured_json)
                from database.models import AssetAnalysis
                from sqlalchemy import select as _asel
                last_tradeable = (await session.execute(
                    _asel(AssetAnalysis.decision)
                    .where(AssetAnalysis.symbol == symbol)
                    .where(AssetAnalysis.decision.in_(['buy', 'sell']))
                    .order_by(AssetAnalysis.generated_at.desc())
                    .limit(1)
                )).scalar_one_or_none()
                last_tradeable_decision = last_tradeable if last_tradeable else 'wait'
                
                cds_score, breakdown = await compute_composite_cds(
                    session=session,
                    symbol=symbol,
                    brief_data=b_data,
                    current_decision=last_tradeable_decision,
                    settings=self.settings
                )
                
                thresholds = get_cds_thresholds(self.settings)
                
                if cds_score >= thresholds['warning']:
                    if cds_score < thresholds['sync_trigger']:
                        logger.info(
                            f'[{symbol}] SSVP Context Divergence Score={cds_score:.2f} >= '
                            f'warning threshold ({thresholds["warning"]:.2f}). Injecting mild warning context.'
                        )
                        coherence_injection = _build_warning_context(symbol, cds_score, breakdown)
                    else:
                        logger.warning(
                            f'[{symbol}] SSVP Context Divergence Score={cds_score:.2f} >= '
                            f'sync threshold ({thresholds["sync_trigger"]:.2f}). Injecting ContextMerge prompt.'
                        )
                        force_wait = cds_score >= thresholds['block_buysell']
                        coherence_injection = _build_contextmerge_prompt(symbol, cds_score, breakdown, force_wait=force_wait)
                        
                    async with get_session() as _mon_sess:
                        mon_key = f'context_drift_{symbol}_{_get_clock().now().strftime("%Y%m%d_%H")}'
                        mon_val = _j.dumps({
                            'cds_score': cds_score,
                            'breakdown': breakdown,
                            'timestamp': _get_clock().now().isoformat(),
                        })
                        await SystemConfig.upsert(_mon_sess, key=mon_key, value=mon_val)
                        await _mon_sess.commit()
        except Exception as _cdc_err:
            logger.debug(f'[{symbol}] SSVP Context coherence check failed (non-fatal): {_cdc_err}')
        return coherence_injection

    async def _check_minimum_data_quality(self, session: AsyncSession, symbol: str) -> tuple[bool, str]:
        """Check if minimum data quality requirements are met for analysis."""
        from database.models import PriceOHLCV, TechnicalIndicator
        from sqlalchemy import select
        
        # Cek apakah ada data harga
        last_price = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()
        if not last_price:
            return False, f"No price data available for {symbol}"
            
        # Cek apakah indikator D1 ada (karena penting untuk makro)
        last_d1 = (await session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol, TechnicalIndicator.timeframe == "D1")
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()
        if not last_d1:
            return False, f"No D1 technical indicators available for {symbol}"
            
        return True, "ok"

    async def _verify_data_currency(self, session: AsyncSession, symbol: str) -> tuple[bool, str]:
        """Verify data freshness (H4 candle age)."""
        from database.models import PriceOHLCV
        from sqlalchemy import select
        from datetime import datetime, timezone
        last_h4 = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol, PriceOHLCV.timeframe == "H4")
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()
        
        if not last_h4:
            return False, f"No H4 price data available for {symbol}"
            
        dt_stamp = last_h4.timestamp
        if dt_stamp.tzinfo is None:
            dt_stamp = dt_stamp.replace(tzinfo=timezone.utc)
            
        now_dt = _get_clock().now()
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        age_hours = (now_dt - dt_stamp).total_seconds() / 3600
        
        is_crypto = symbol.upper().startswith("BTC") or symbol.upper().startswith("ETH") or symbol.upper().startswith("SOL")
        is_weekend = (now_dt.weekday() == 5) or (now_dt.weekday() == 6 and now_dt.hour < 22) or (now_dt.weekday() == 4 and now_dt.hour >= 22)
        is_reopen = (now_dt.weekday() == 6 and now_dt.hour >= 22) or (now_dt.weekday() == 0 and now_dt.hour < 4)
        
        if not is_crypto and is_weekend:
            return True, "ok"
            
        from utils.constants import H4_DATA_MAX_AGE_HOURS
        effective_max = H4_DATA_MAX_AGE_HOURS + (48.0 if (not is_crypto and is_reopen) else 0.0)
        if age_hours > effective_max:
            return False, f"H4 data is too old ({age_hours:.1f} hours). Latest: {dt_stamp}"
            
        return True, "ok"

    async def _check_data_coherence_for_analysis(self, session: AsyncSession, symbol: str) -> tuple[bool, str]:
        """Verify key data points are internally consistent."""
        from database.models import PriceOHLCV, TechnicalIndicator
        from sqlalchemy import select
        import json
        
        atr_row = (await session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol, TechnicalIndicator.indicator_name == "ATR_14", TechnicalIndicator.timeframe == "H4")
            .order_by(TechnicalIndicator.timestamp.desc()).limit(1)
        )).scalar_one_or_none()
        
        if atr_row:
            try:
                raw_atr = json.loads(atr_row.value_json)
                atr_val = float(raw_atr.get('atr', 0) if isinstance(raw_atr, dict) else raw_atr)
                if atr_val <= 0:
                    return False, f"ATR_14 value ({atr_val}) is non-positive"
            except Exception as e:
                return False, f"Failed to parse ATR_14 value: {e}"
        
        # 1. Check TechnicalIndicator vs OHLCV coherence
        from utils.validation.data_validator import check_data_coherence
        coherence = await check_data_coherence(
            session, 
            symbol,
            max_ohlcv_age_hours=self.settings.get('data_quality', {}).get('max_ohlcv_age_hours'),
            max_indicator_age_hours=self.settings.get('data_quality', {}).get('max_indicator_age_hours'),
        )
        if not coherence['coherent']:
            return False, f"Data coherence issue: {'; '.join(coherence['issues'])}"
            
        # 2. Check ATR indicator exists
        atr_row = (await session.execute(
            select(TechnicalIndicator)
            .where(TechnicalIndicator.symbol == symbol)
            .where(TechnicalIndicator.timeframe == 'H4')
            .where(TechnicalIndicator.indicator_name == 'ATR_14')
            .order_by(TechnicalIndicator.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()
        
        if atr_row is None:
            return False, f'No ATR_14 for {symbol}/H4 (indicators not computed)'

        # Check ATR staleness (must match H4 indicator max age)
        atr_ts = atr_row.timestamp
        if atr_ts.tzinfo is None:
            atr_ts = atr_ts.replace(tzinfo=timezone.utc)
            
        now_dt = _get_clock().now()
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        atr_age_hours = (now_dt - atr_ts).total_seconds() / 3600
        
        is_crypto = symbol.upper().startswith("BTC") or symbol.upper().startswith("ETH") or symbol.upper().startswith("SOL")
        is_weekend = (now_dt.weekday() == 5) or (now_dt.weekday() == 6 and now_dt.hour < 22) or (now_dt.weekday() == 4 and now_dt.hour >= 22)
        is_reopen = (now_dt.weekday() == 6 and now_dt.hour >= 22) or (now_dt.weekday() == 0 and now_dt.hour < 4)
        
        from utils.constants import H4_DATA_MAX_AGE_HOURS
        ATR_MAX_AGE_HOURS = H4_DATA_MAX_AGE_HOURS + (48.0 if (not is_crypto and (is_weekend or is_reopen)) else 0.0)
        if not (not is_crypto and is_weekend) and atr_age_hours > ATR_MAX_AGE_HOURS:
            return (
                False,
                f'ATR_14 for {symbol}/H4 is {atr_age_hours:.1f}h old (limit: {ATR_MAX_AGE_HOURS}h). '
                f'SL validation would use stale volatility reference. Wait for MT5 reconnection.'
            )
        
        # 3. Check VIX data must exist (needed for VIX_OK confluence factor)
        from database.models import VIXData
        vix = await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))
        vix_row = vix.scalar_one_or_none()
        if not vix_row:
            return False, "No VIX data - cannot assess market risk environment"
        
        vix_date = vix_row.date
        if hasattr(vix_date, 'tzinfo') and vix_date.tzinfo is None:
            vix_date = vix_date.replace(tzinfo=timezone.utc)
        elif not hasattr(vix_date, 'tzinfo'):
            # It's a datetime.date object
            vix_date = datetime(vix_date.year, vix_date.month, vix_date.day, tzinfo=timezone.utc)
            
        vix_age_days = (now_dt - vix_date).days
        if vix_age_days > 5:
            return False, f"VIX data is {vix_age_days} days old - risk assessment unreliable"
        
        return True, 'ok'


class VerifierService(VerifiersMixin):
    """Component for stage verifiers and data currency validation via composition (H-1)."""
    def __init__(self, settings: Optional[dict] = None, runner: Optional[Any] = None):
        self.settings = settings or {}
        self.runner = runner
