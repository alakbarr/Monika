"""
Brief Contamination Guard
Validates Stage 1 brief integrity before allowing Stage 2 propagation.
Implements anti-contamination measures per SSVP research.
"""

import json
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import DXYData, VIXData

logger = logging.getLogger('TradingAgent.BriefContaminationGuard')

try:
    from sqlalchemy import func as _func
except ImportError:
    _func = None


def func_abs(x):
    if _func is not None:
        return _func.abs(x)
    return x


class BriefContaminationGuard:
    """
    Protects against contamination spreading from Stage 1 to all Stage 2 agents.
    
    Per research: contamination most dangerous when a single erroneous belief
    cascades across multiple semantically linked evaluation dimensions.
    
    In trading: wrong USD bias → all USD pairs contaminated.
    """

    # Pairs that should NOT both be the same directional bias
    # against USD simultaneously (would be internally contradictory)
    INTERNALLY_CONSISTENT_GROUPS = {
        'usd_long_pairs': ['EURUSD', 'GBPUSD', 'AUDUSD'],
        'usd_short_pairs': ['USDJPY'],
        'safe_haven': ['XAUUSD'],
    }

    @staticmethod
    async def validate_brief_integrity(
        session: AsyncSession,
        brief_data: dict,
        settings: Optional[dict] = None
    ) -> tuple[bool, list[str], float]:
        """
        Multi-layer validation of Stage 1 brief.
        
        Returns: (is_safe, issues_list, contamination_risk_score)
        """
        issues = []
        risk_score = 0.0

        currency_bias = brief_data.get('currency_bias', {})
        risk_sentiment = brief_data.get('risk_sentiment', 'mixed')
        confidence = brief_data.get('confidence', 0.5)

        # Check 1: Internal USD consistency (EUR, GBP, AUD)
        from utils.market.bias_utils import normalize_bias
        usd_bias = normalize_bias(currency_bias.get('USD', 'neutral'))
        eur_bias = normalize_bias(currency_bias.get('EUR', 'neutral'))

        if (usd_bias == 'bullish' and eur_bias == 'bullish') or (usd_bias == 'bearish' and eur_bias == 'bearish'):
            issues.append(
                f"CORRELATION CONFLICT: Both USD and EUR labeled '{usd_bias}'. "
                "EURUSD correlation ~0.95 inverse makes this rare without strong idiosyncratic drivers. "
                "Brief may have hallucinated currency biases."
            )
            risk_score += 0.40

        gbp_bias = normalize_bias(currency_bias.get('GBP', 'neutral'))
        aud_bias = normalize_bias(currency_bias.get('AUD', 'neutral'))
        jpy_bias = normalize_bias(currency_bias.get('JPY', 'neutral'))

        # GBP/USD correlation
        if (usd_bias == 'bullish' and gbp_bias == 'bullish') or (usd_bias == 'bearish' and gbp_bias == 'bearish'):
            issues.append(f"CORRELATION CONFLICT: Both USD and GBP labeled '{usd_bias}' (GBPUSD/EURUSD high correlation).")
            risk_score += 0.30

        # AUD/USD correlation
        if (usd_bias == 'bullish' and aud_bias == 'bullish') or (usd_bias == 'bearish' and aud_bias == 'bearish'):
            issues.append(f"CORRELATION CONFLICT: Both USD and AUD labeled '{usd_bias}' — AUDUSD historically moves inverse to USD strength.")
            risk_score += 0.25

        # NEW: JPY sebagai safe-haven, cek serupa dengan XAU yang sudah ada
        if risk_sentiment == 'risk-on' and jpy_bias == 'bullish':
            issues.append("SENTIMENT MISMATCH: risk_sentiment='risk-on' but JPY='bullish'. JPY typically weakens in risk-on regimes (carry-trade unwind logic reverses). Requires idiosyncratic justification (e.g. BOJ policy shift).")
            risk_score += 0.2
        if risk_sentiment == 'risk-off' and jpy_bias == 'bearish':
            issues.append("SENTIMENT MISMATCH: risk_sentiment='risk-off' but JPY='bearish'. JPY typically strengthens as a safe-haven during risk-off flows.")
            risk_score += 0.2

        # Check 2: Safe-haven consistency with risk sentiment
        xau_bias = normalize_bias(currency_bias.get('XAU', 'neutral'))
        if risk_sentiment == 'risk-on' and xau_bias == 'bullish':
            # Not impossible but needs extra scrutiny
            issues.append(
                "SENTIMENT MISMATCH: risk_sentiment='risk-on' but XAU='bullish'. "
                "Gold is a safe-haven — typically bearish in risk-on environments. "
                "Brief needs idiosyncratic driver justification."
            )
            risk_score += 0.20

        # Check 3: Cross-validate with DXY (most reliable real-time signal)
        try:
            dxy_rows = (await session.execute(
                select(DXYData).order_by(DXYData.date.desc()).limit(5)
            )).scalars().all()
            
            if len(dxy_rows) >= 3:
                dxy_trend = 'strengthening' if dxy_rows[0].close > dxy_rows[-1].close else 'weakening'
                # Check if brief contains explicit forward-looking catalyst or macro narrative justifying reversal
                narrative_l = (brief_data.get('macro_narrative') or '').lower()
                has_reversal_catalyst = any(w in narrative_l for w in ('reversal', 'catalyst', 'pivot', 'fed cut', 'hike', 'cpi miss', 'cpi beat', 'nfp', 'yield drop', 'yield spike')) or bool(brief_data.get('macro_catalysts'))
                
                penalty = 0.15 if has_reversal_catalyst else 0.25
                if dxy_trend == 'strengthening' and usd_bias == 'bearish':
                    issues.append(
                        f"DXY CONFLICT: DXY 5-day trend='{dxy_trend}' but brief says USD='{usd_bias}'. "
                        f"DXY is price-based. {'Reversal catalyst noted in brief.' if has_reversal_catalyst else 'Verify USD thesis against fresh macro releases.'}"
                    )
                    risk_score += penalty
                elif dxy_trend == 'weakening' and usd_bias == 'bullish':
                    issues.append(
                        f"DXY CONFLICT: DXY 5-day trend='{dxy_trend}' but brief says USD='{usd_bias}'. "
                        f"DXY is price-based. {'Reversal catalyst noted in brief.' if has_reversal_catalyst else 'Verify USD thesis against fresh macro releases.'}"
                    )
                    risk_score += penalty
        except Exception as e:
            logger.debug(f"BriefContaminationGuard: DXY check failed (non-fatal): {e}")
            try:
                await session.rollback()
            except Exception:
                pass

        # Check 4: VIX consistency
        try:
            vix = (await session.execute(
                select(VIXData).order_by(VIXData.date.desc()).limit(1)
            )).scalar_one_or_none()
            
            if vix:
                if vix.close > 30 and risk_sentiment == 'risk-on':
                    issues.append(
                        f"VIX CONFLICT: VIX={vix.close:.1f} indicates HIGH FEAR "
                        f"but brief says risk_sentiment='{risk_sentiment}'. "
                        f"VIX is real-time market fear gauge — trust VIX over brief."
                    )
                    risk_score += 0.30
                elif vix.close < 13 and risk_sentiment == 'risk-off':
                    issues.append(
                        f"VIX CONFLICT: VIX={vix.close:.1f} indicates COMPLACENCY "
                        f"but brief says risk_sentiment='{risk_sentiment}'."
                    )
                    risk_score += 0.20
        except Exception as e:
            logger.debug(f"BriefContaminationGuard: VIX check failed (non-fatal): {e}")
            try:
                await session.rollback()
            except Exception:
                pass

        # Check 5: Brief confidence sanity
        if confidence < 0.40:
            issues.append(
                f"LOW CONFIDENCE BRIEF: Stage 1 confidence={confidence:.0%}. "
                f"High contamination risk — Stage 2 agents may anchor on low-quality brief."
            )
            risk_score += 0.15

        # Normalize risk score
        risk_score = min(risk_score, 1.0)
        is_safe = risk_score < 0.50

        if issues:
            logger.warning(
                f"BriefContaminationGuard: {len(issues)} issues found "
                f"(risk_score={risk_score:.2f}, is_safe={is_safe})"
            )
            for issue in issues:
                logger.warning(f"  → {issue}")

        return is_safe, issues, risk_score

    @staticmethod
    async def compute_per_symbol_safety(
        session: AsyncSession,
        brief_data: dict,
        symbols: list[str],
        settings: Optional[dict] = None
    ) -> dict[str, dict]:
        """
        Compute per-symbol safety assessment using per-symbol CDS.
        Implements SELECTIVE synchronization (not full-broadcast).
        
        Returns dict: symbol → {safety_level, cds, breakdown, context}
        """
        from utils.protocol.enhanced_cds import compute_composite_cds, get_cds_thresholds_async
        
        thresholds = await get_cds_thresholds_async(session, settings)
        result = {}

        for symbol in symbols:
            try:
                cds, breakdown = await compute_composite_cds(
                    session, symbol, brief_data, settings=settings
                )

                if cds < thresholds['warning']:
                    safety_level = 'safe'
                    context = ''
                elif cds < thresholds['sync_trigger']:
                    safety_level = 'warning'
                    context = _build_warning_context(symbol, cds, breakdown)
                elif cds < thresholds['block_buysell']:
                    safety_level = 'sync_required'
                    context = _build_contextmerge_prompt(symbol, cds, breakdown)
                elif cds < thresholds['abort_all']:
                    safety_level = 'block_buysell'
                    context = _build_contextmerge_prompt(symbol, cds, breakdown, force_wait=True)
                else:
                    safety_level = 'abort'
                    context = f"[SSVP ABORT] CDS={cds:.2f} for {symbol} exceeds abort threshold. Skipping analysis."

                result[symbol] = {
                    'safety_level': safety_level,
                    'cds': cds,
                    'breakdown': breakdown,
                    'context': context,
                }

            except Exception as e:
                logger.error(f"Per-symbol safety check failed for {symbol}: {e}")
                result[symbol] = {
                    'safety_level': 'warning',  # Fail-safe: raise warning context if check fails
                    'cds': 0.35,
                    'breakdown': {'error': str(e)},
                    'context': f'Contamination check failed with exception: {e}',
                }

        return result

    @staticmethod
    async def check_magnitude_based_staleness(
        session: AsyncSession,
        symbol: str,
        brief_generated_at: datetime,
        settings: Optional[dict] = None
    ) -> tuple[bool, str]:
        """
        Check if brief is stale based on PRICE MOVEMENT MAGNITUDE,
        not just time elapsed.
        
        A brief from 2 hours ago may be stale if XAUUSD moved 0.5%.
        """
        from database.models import PriceOHLCV
        from sqlalchemy import select

        # Get thresholds from settings
        default_threshold = 0.35
        if settings:
            thresholds = settings.get('ssvp', {}).get('magnitude_staleness_thresholds', {})
            threshold_pct = thresholds.get(symbol, thresholds.get('default', default_threshold))
        else:
            threshold_pct = default_threshold

        now = datetime.now(timezone.utc)
        brief_time = brief_generated_at.replace(tzinfo=timezone.utc) if brief_generated_at.tzinfo is None else brief_generated_at

        # Get price at brief generation time (approximate: nearest H4 bar)
        price_at_brief = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == 'H4')
            .where(PriceOHLCV.timestamp <= brief_time + timedelta(hours=4))
            .where(PriceOHLCV.timestamp >= brief_time - timedelta(hours=4))
            .order_by(func_abs(
                _func.extract('epoch', PriceOHLCV.timestamp) - 
                brief_time.timestamp()
            ) if _func is not None else PriceOHLCV.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()

        # Get current price
        current_price_bar = (await session.execute(
            select(PriceOHLCV)
            .where(PriceOHLCV.symbol == symbol)
            .where(PriceOHLCV.timeframe == 'H4')
            .order_by(PriceOHLCV.timestamp.desc())
            .limit(1)
        )).scalar_one_or_none()

        if not price_at_brief or not current_price_bar:
            return False, ''

        if price_at_brief.close <= 0:
            return False, ''

        price_change_pct = abs(
            (current_price_bar.close - price_at_brief.close) / price_at_brief.close * 100
        )

        if price_change_pct > threshold_pct:
            age_hours = (now - brief_time).total_seconds() / 3600
            return True, (
                f"PRICE-STALE BRIEF: {symbol} moved {price_change_pct:.2f}% "
                f"since brief generation ({age_hours:.1f}h ago). "
                f"Threshold: {threshold_pct:.2f}%. "
                f"Macro bias in brief may no longer apply to current price levels. "
                f"Weight technical analysis over macro brief for this symbol."
            )

        return False, ''


def _build_warning_context(symbol: str, cds: float, breakdown: dict) -> str:
    """Light warning for CDS in warning range."""
    dominant = breakdown.get('dominant_dimension', 'unknown')
    return (
        f"\\n⚠️ [SSVP WARNING — {symbol}] Context Divergence Score={cds:.2f} "
        f"(dominant: {dominant}). "
        f"Minor inconsistency detected between data sources. "
        f"Apply normal analysis but note in rationale which source you weight more."
    )


def _build_contextmerge_prompt(
    symbol: str,
    cds: float,
    breakdown: dict,
    force_wait: bool = False
) -> str:
    """
    Build explicit ContextMerge adjudication prompt per research protocol.
    """
    spatial = breakdown.get('spatial', 0)
    temporal = breakdown.get('temporal', 0)
    task = breakdown.get('task', 0)

    dominant_issues = []
    if spatial > 0.25:
        dominant_issues.append(f"Stage 1 macro bias conflicts with recent {symbol} price action (spatial CDS={spatial:.2f})")
    if temporal > 0.25:
        dominant_issues.append(f"Data sources are from significantly different time points (temporal CDS={temporal:.2f})")
    if task > 0.25:
        dominant_issues.append(f"Current decision would dramatically contradict recent analysis history (task CDS={task:.2f})")

    force_wait_instruction = (
        "\\n⛔ MANDATORY: Due to HIGH CDS, you MUST submit WAIT unless you can provide "
        "an extremely clear and specific adjudication resolving ALL conflicts above. "
        "Ambiguous rationale = WAIT submission required.\\n"
    ) if force_wait else ""

    return f"""
╔══════════════════════════════════════════════════════════════════╗
║ SSVP CONTEXT MERGE REQUIRED: CONFLICTING DATA DETECTED 
╚══════════════════════════════════════════════════════════════════╝
Context Divergence Score (CDS) = {cds:.2f} (HIGH RISK OF HALLUCINATION)

Conflict Details:
{chr(10).join(f"- {issue}" for issue in dominant_issues)}

{force_wait_instruction}
YOUR INSTRUCTIONS:
1. DO NOT simply blend conflicting signals (e.g., "brief is 
   bullish, but H4 price dropped 0.3% since brief."

2. EVALUATE SOURCE AUTHORITY:
   • Which data source is MORE RECENT?
   • Which is MORE SPECIFIC to current conditions?
   • Which has been MORE ACCURATE recently (per performance notes)?

3. RESOLVE: State your decision explicitly in your rationale:
   "I trust [PRICE ACTION / STAGE 1 BRIEF] because [SPECIFIC REASON]."
   OR: "This contradiction is unresolvable → submitting WAIT."

4. APPLY: Use the resolved belief for ALL remaining analysis steps.

VALIDATION: Your rationale in submit_asset_analysis MUST contain
one of these adjudication markers:
  → "I trust price action because..."
  → "I trust the brief because..."  
  → "Contradiction unresolved → WAIT"
  → "Brief overrides because..."
  → "Price action overrides because..."

Failure to include adjudication = system will require WAIT decision.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
