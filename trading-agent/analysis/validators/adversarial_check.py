import json
import logging
from typing import Any
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import AssetAnalysis, SystemConfig
from analysis.providers.llm_factory import get_client_for_task

logger = logging.getLogger('TradingAgent.AdversarialCheck')

ADVERSARIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "approve": {"type": "boolean"},
        "overall_quality": {"type": "string", "enum": ["high", "medium", "low"]},
        "strongest_counter_argument": {"type": "string"},
        "hard_block": {"type": "boolean",
            "description": "true only for objective, verifiable flaws (e.g. rationale contradicts its own stated data, R:R math doesn't match stated levels, ignores an explicitly stated invalidation condition)"},
        "hard_block_reason": {"type": "string"},
        "recommend_block": {"type": "boolean",
            "description": "true if quality is low/risk is high but not objectively disqualifying"},
        "block_reason": {"type": "string"},
    },
    "required": ["approve", "overall_quality", "strongest_counter_argument", "hard_block", "recommend_block"]
}


def _safe_parse(val: Any) -> dict:
    if isinstance(val, dict):
        return val
    if not isinstance(val, str):
        return {}
    c = val.strip()
    if "```json" in c:
        c = c.split("```json")[1].split("```")[0].strip()
    elif "```" in c:
        c = c.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(c)
    except Exception:
        return {}


async def run_adversarial_check(session: AsyncSession, analysis: AssetAnalysis, settings: dict) -> dict:
    default_result = {'approve': True, 'overall_quality': 'medium', 'strongest_counter_argument': '',
                       'hard_block': False, 'hard_block_reason': '', 'recommend_block': False, 'block_reason': ''}
    prompt = ""
    try:
        client = get_client_for_task('adversarial_check', settings)
        deterministic_flags = []

        # Existing checks
        min_rr = float(settings.get('trading', {}).get('risk', {}).get('min_rr_ratio', 1.3))
        effective_entry = getattr(analysis, "entry_price", None) or analysis.price_at_analysis
        if analysis.stop_loss and analysis.take_profit and effective_entry:
            sl_dist = abs(effective_entry - analysis.stop_loss)
            tp_dist = abs(effective_entry - analysis.take_profit)
            if sl_dist > 0 and (tp_dist / sl_dist) < (min_rr - 0.05):
                deterministic_flags.append(f'R:R only {tp_dist / sl_dist:.2f} based on entry zone (min {min_rr:.1f} expected)')
        if analysis.confluence_score is not None and analysis.confluence_score < 6:
            deterministic_flags.append(f'confluence_score={analysis.confluence_score} is unusually low')

        # NEW checks — reuse data yang SUDAH terstruktur di DB, bukan re-derive dari teks
        if analysis.priced_in_score is not None and analysis.priced_in_score >= 9:
            deterministic_flags.append(
                f'priced_in_score={analysis.priced_in_score}/10 — event heavily priced in, sell-the-news risk extreme'
            )
        if not analysis.invalidation_price or not analysis.invalidation_direction:
            deterministic_flags.append(
                'invalidation_price/invalidation_direction NOT SET — thesis tidak bisa dimonitor otomatis'
            )

        # Consecutive loss check (reuse existing pattern dari risk_gate)
        try:
            from database.models import PaperTradeRecord
            recent = (
                await session.execute(
                    select(PaperTradeRecord).where(PaperTradeRecord.symbol == analysis.symbol)
                    .where(PaperTradeRecord.status == 'closed')
                    .where(PaperTradeRecord.exit_reason.in_(['sl_hit', 'tp_hit']))
                    .order_by(PaperTradeRecord.closed_at.desc()).limit(3)
                )
            ).scalars().all()
            if len(recent) == 3 and all(r.exit_reason == 'sl_hit' for r in recent):
                deterministic_flags.append(f'{analysis.symbol}: 3 consecutive SL hits historically — re-entry risk')
        except Exception:
            pass

        # --- NEW: Fix truncation logic to preserve STRESS TEST block ---
        full_rationale = analysis.rationale or ''
        import re
        stress_match = re.search(r'\[STRESS TEST:.*?\]', full_rationale, re.DOTALL)
        stress_block = stress_match.group(0) if stress_match else ''
        remaining_budget = 4000 - len(stress_block)
        body = full_rationale[:remaining_budget]
        rationale_for_prompt = (body + ('\n' + stress_block if stress_block and stress_block not in body else ''))
        # --- END NEW ---

        # Inject fact sheet for ground truth verification
        fact_sheet_str = ''
        try:
            from analysis.debate.fact_sheet import build_fact_sheet
            fact_sheet = await build_fact_sheet(session, analysis.id if hasattr(analysis, 'id') and analysis.id else analysis)
            fact_sheet_str = json.dumps(fact_sheet, indent=2, default=str)
        except Exception as fs_err:
            logger.debug(f'[AdversarialCheck] Could not build fact sheet: {fs_err}')

        prompt = f"""
Symbol: {analysis.symbol}
Direction: {analysis.decision.upper()}
Confluence Score: {analysis.confluence_score}/14
Priced-In Score: {analysis.priced_in_score}/10
Invalidation (structured): {analysis.invalidation_price} / {analysis.invalidation_direction}
Invalidation (text): {analysis.invalidation}
Entry context: {analysis.entry_zone}
SL: {analysis.stop_loss}  TP: {analysis.take_profit}

Deterministic red flags already detected by the system:
{chr(10).join(deterministic_flags) if deterministic_flags else 'none'}

QUALITY SEVERITY ANCHORS (mandatory reference for overall_quality):
- high: Zero unresolved deterministic red flags; rationale cites concrete price/structure levels; bull/bear stress tests are specific and verifiable.
- medium: Exactly 1 minor concern exists (e.g. marginal R:R just above minimum threshold, or 1 mild red flag sufficiently justified in rationale).
- low: 2+ deterministic red flags lack adequate justification, OR rationale is generic/non-specific to current market structure, OR contains unaddressed contradictions with priced-in score or macro brief.

Full Rationale (verbatim, do not paraphrase):
{rationale_for_prompt}

RAW FACT SHEET (ground truth from database — use to verify rationale claims):
{fact_sheet_str if fact_sheet_str else 'unavailable'}

Find the STRONGEST argument against this specific trade. Prioritize addressing the deterministic red flags above before seeking other arguments. 
hard_block=true ONLY for objective disqualifications (mathematical errors, direct self-contradiction, missing/unclear invalidation conditions, or priced_in_score >= 9 without override justification). 
recommend_block=true for significant, non-fatal risk factors.
"""
        import hashlib
        cache_key = f"adv_cache_{hashlib.md5(f'{analysis.symbol}_{analysis.decision}_{analysis.confluence_score}_{analysis.stop_loss}_{analysis.take_profit}_{analysis.rationale}'.encode()).hexdigest()}"
        
        cached_result = (await session.execute(
            select(SystemConfig).where(SystemConfig.key == cache_key)
        )).scalar_one_or_none()
        
        if cached_result and cached_result.value:
            logger.info(f"[AdversarialCheck] {analysis.symbol}: Using cached result")
            return {**default_result, **json.loads(cached_result.value)}

        from utils.typesafe.jev_primitives import build_adversarial_check_questions
        adv_jev_q = build_adversarial_check_questions(analysis.symbol)

        result_str = await client.generate_content(
            system_prompt='You are a skeptical risk-desk reviewer performing a final pre-trade challenge.',
            user_message=prompt, response_schema=ADVERSARIAL_SCHEMA,
            jev_questions=adv_jev_q,
            temperature=0.0
        )
        if not result_str:
            return default_result

        result = _safe_parse(result_str)
        # Synthesize meaningful explanations from Jev category if free-text is empty or YES/NO
        primary_risk = result.get("primary_risk_category")
        if primary_risk and primary_risk != "none":
            if not result.get("strongest_counter_argument") or result.get("strongest_counter_argument") in ("YES", "NO"):
                result["strongest_counter_argument"] = f"Adversarial risk flagged: {primary_risk}"
            if result.get("hard_block") and (not result.get("hard_block_reason") or result.get("hard_block_reason") in ("YES", "NO")):
                result["hard_block_reason"] = f"Fatal flaw: {primary_risk}"
            if result.get("recommend_block") and (not result.get("block_reason") or result.get("block_reason") in ("YES", "NO")):
                result["block_reason"] = f"Recommended block: {primary_risk}"

        merged = {**default_result, **result}
        
        # Save to cache
        await SystemConfig.upsert(session, key=cache_key, value=json.dumps(merged))
        
        # persist for later calibration
        key = f"adversarial_outcome_{analysis.id}"
        await SystemConfig.upsert(session, key=key, value=json.dumps({
            "analysis_id": analysis.id, "symbol": analysis.symbol,
            "hard_block": merged.get("hard_block", False), "recommend_block": merged.get("recommend_block", False),
            "quality": merged.get("overall_quality", "medium"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }))
        await session.commit()
        return merged
    except Exception as e:
        logger.error(f'[AdversarialCheck] {analysis.symbol}: check failed (attempt 1), retrying: {e}')
        # Retry once before failing closed
        try:
            import asyncio
            await asyncio.sleep(3)
            retry_prompt = prompt or f"Symbol: {analysis.symbol}\nDirection: {analysis.decision}\nRationale: {analysis.rationale or ''}"
            client = get_client_for_task('adversarial_check', settings)
            from utils.typesafe.jev_primitives import build_adversarial_check_questions
            retry_jev_q = build_adversarial_check_questions(analysis.symbol)
            result_str = await client.generate_content(
                system_prompt='You are a skeptical risk-desk reviewer performing a final pre-trade challenge.',
                user_message=retry_prompt, response_schema=ADVERSARIAL_SCHEMA,
                jev_questions=retry_jev_q,
                temperature=0.0
            )
            if result_str:
                result = _safe_parse(result_str)
                primary_risk = result.get("primary_risk_category")
                if primary_risk and primary_risk != "none":
                    if not result.get("strongest_counter_argument") or result.get("strongest_counter_argument") in ("YES", "NO"):
                        result["strongest_counter_argument"] = f"Adversarial risk flagged: {primary_risk}"
                    if result.get("hard_block") and (not result.get("hard_block_reason") or result.get("hard_block_reason") in ("YES", "NO")):
                        result["hard_block_reason"] = f"Fatal flaw: {primary_risk}"
                    if result.get("recommend_block") and (not result.get("block_reason") or result.get("block_reason") in ("YES", "NO")):
                        result["block_reason"] = f"Recommended block: {primary_risk}"
                return {**default_result, **result}
        except Exception as retry_err:
            logger.error(f'[AdversarialCheck] {analysis.symbol}: retry also failed: {retry_err}')

        # Alert admin that adversarial check had an error (fail-open)
        try:
            from utils.infra.notifier import AgentNotifier
            import asyncio
            asyncio.create_task(AgentNotifier().send_warning(
                f"⚠️ <b>Adversarial Check Unavailable (Fail-Open)</b>\n\n"
                f"Symbol: {analysis.symbol}\n"
                f"Decision: {analysis.decision}\n"
                f"Error: {e}\n\n"
                f"Trade is allowed through because preceding validation gates passed."
            ))
        except Exception:
            pass

        return {'approve': True, 'overall_quality': 'medium', 'strongest_counter_argument': f"Adversarial check unavailable: {e}",
                'hard_block': False, 'hard_block_reason': '',
                'recommend_block': False, 'block_reason': ''}
