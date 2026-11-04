# ==============================================================================
# File: application/analysis/stages/fundamental_fallback.py
# ==============================================================================

"""
Deterministic Fallback Brief Generator & Brief Patcher for FundamentalStage.
Derives baseline regime and sentiment when LLM is unavailable or tool calls fail.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
import re
import monika.core.primitives.clock as clock
from monika.infrastructure.providers.llm_factory import get_client_for_task
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import FundamentalBrief

logger = logging.getLogger("TradingAgent.FundamentalStage")


async def generate_deterministic_fallback_brief(
    stage_instance, session: AsyncSession, prefetched_data: Any, weekend_btc_only_mode: bool = False
) -> Optional[FundamentalBrief]:
    """
    Generate deterministic baseline brief when LLM fails or fails to call submit tool.
    Derives baseline regime and sentiment from prefetched indicators (VIX, FedWatch, etc.)
    """
    try:
        data_dict = {}
        if isinstance(prefetched_data, dict):
            data_dict = prefetched_data
        elif isinstance(prefetched_data, str):
            try:
                data_dict = json.loads(prefetched_data)
            except Exception:
                data_dict = {}

        vix_val = None
        if "vix" in data_dict and isinstance(data_dict["vix"], dict):
            vix_val = data_dict["vix"].get("current") or data_dict["vix"].get("close")
        elif "vix" in data_dict and isinstance(data_dict["vix"], (int, float)):
            vix_val = float(data_dict["vix"])

        regime = "mixed"
        sentiment = "mixed"
        if vix_val is not None:
            if vix_val < 18.0:
                sentiment = "risk-on"
                regime = "risk_on"
            elif vix_val > 25.0:
                sentiment = "risk-off"
                regime = "risk_off"

        currencies = ["BTC"] if weekend_btc_only_mode else ["USD", "EUR", "GBP", "JPY", "AUD", "XAU", "OIL", "BTC"]
        currency_bias = {c: "neutral" for c in currencies}
        currency_confidence = {c: 0.0 for c in currencies}
        dxy_info = data_dict.get("dxy") or {}
        dxy_trend = str(dxy_info.get("trend_5d", "")).lower() if isinstance(dxy_info, dict) else ""
        baseline_confidence = 0.0

        # FIX 5.11: Generate concrete macro-specific invalidation conditions
        invalidation_conditions = {}
        for c in currencies:
            b = currency_bias.get(c, "neutral")
            if c == "USD":
                invalidation_conditions[c] = (
                    "DXY daily change > +0.75% or 10Y US Treasury yield shifts by >= 15 bps contrary to bias"
                    if b != "neutral"
                    else "DXY breaks outside 5-day range by > 1.0%"
                )
            elif c in ("XAU", "GOLD"):
                invalidation_conditions[c] = (
                    "US 10Y real yield rises by >= 20 bps or DXY surges > 0.8%"
                    if b == "bullish"
                    else "VIX spikes > 25.0 or sudden safe-haven demand emerges"
                )
            elif c == "JPY":
                invalidation_conditions[c] = (
                    "BoJ surprise policy action or US-JP 10Y yield differential expands by >= 25 bps"
                )
            elif c == "OIL":
                invalidation_conditions[c] = (
                    "EIA crude inventory surprise > 5M barrels or OPEC+ emergency output change"
                )
            else:
                invalidation_conditions[c] = (
                    f"{c} central bank guidance shifts by >= 25 bps or core CPI surprise > 0.3%"
                )

        structured = {
            "macro_bias": currency_bias.get("USD", "neutral"),
            "macro_narrative": (
                "[DETERMINISTIC FALLBACK BRIEF]: AI fundamental stage encountered an upstream error or "
                "did not submit a structured brief. A rule-based baseline was synthesized from available indicators. "
                f"Market regime: {regime}, Sentiment: {sentiment} (VIX: {vix_val if vix_val is not None else 'N/A'}, DXY: {dxy_trend or 'neutral'}). "
                f"Downstream Stage 2 specialists should proceed with baseline confidence ({baseline_confidence:.2f})."
            ),
            "key_drivers": [
                f"VIX: {vix_val if vix_val is not None else 'baseline'}",
                f"DXY 5d Trend: {dxy_trend or 'neutral'}",
                "Deterministic baseline fallback",
            ],
            "risk_events": [],
            "narrative_shift": False,
            "macro_regime": regime,
            "risk_sentiment": sentiment,
            "currency_bias": currency_bias,
            "currency_confidence": currency_confidence,
            "invalidation_conditions": invalidation_conditions,
            "confidence": baseline_confidence,
            "priced_in_assessment": {
                "dominant_driver": "Deterministic baseline fallback",
                "priced_in_score": 5,
                "sell_the_news_risk": "low",
            },
            "strongest_counter_thesis": "Deterministic baseline holds technical-inferred bias; directional momentum may develop from technical or order-flow drivers.",
            "is_fallback": True,
            "is_deterministic_fallback": True,
            "_data_quality_degraded": True,
        }

        now_utc = clock.now()
        brief = FundamentalBrief(
            generated_at=now_utc,
            valid_until=now_utc + timedelta(hours=12),
            content_markdown=structured["macro_narrative"],
            structured_json=json.dumps(structured),
            confidence=baseline_confidence,
            risk_sentiment=sentiment,
            debate_bull_thesis="Deterministic neutral baseline",
            debate_bear_thesis="Deterministic neutral baseline",
            debate_winner="TIE",
            debate_escalation_required=False,
        )
        session.add(brief)
        await session.commit()
        await session.refresh(brief)
        logger.info(f"Generated deterministic fallback FundamentalBrief (id={brief.id}) successfully.")
        return brief
    except Exception as e:
        logger.error(f"Failed to generate deterministic fallback brief: {e}", exc_info=True)
        return None


async def patch_brief(
    stage_instance,
    session: AsyncSession,
    catalyst_text: str,
    catalyst_type: str = "breaking_news",
    affected_currencies: Optional[list[str]] = None,
) -> Optional[FundamentalBrief]:
    """
    Surgical Macro Delta Revision (Tier 2).
    Merevisi FundamentalBrief yang sudah ada secara inkremental menggunakan model ringan (Flash),
    menghemat ~85% token tanpa mengulang full debate dari nol.
    """
    logger.info(f"[MacroDeltaPatch] Memulai revisi delta makro (katalis={catalyst_type})...")
    current_brief: Optional[FundamentalBrief] = None
    try:
        stmt = select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
        current_brief = (await session.execute(stmt)).scalar_one_or_none()
        if not current_brief:
            logger.warning("[MacroDeltaPatch] Tidak ada brief aktif untuk ditambal, fallback ke full run.")
            await stage_instance.run(session, forced=True)
            return (await session.execute(stmt)).scalar_one_or_none()

        baseline_structured = {}
        if current_brief.structured_json:
            try:
                baseline_structured = json.loads(current_brief.structured_json)
            except Exception:
                baseline_structured = {}

        import monika.application.analysis.stages.fundamental_stage as _fundamental_stage_mod

        _get_client = getattr(_fundamental_stage_mod, "get_client_for_task", get_client_for_task)
        client = _get_client("stage1_delta_revision", stage_instance.settings)

        system_prompt = (
            "You are Monika's Macro Delta Auditor. Your objective is to perform a surgical, "
            "objective delta evaluation on an existing Fundamental Brief based on an incoming market catalyst.\n\n"
            "CRITICAL ANTI-BIAS & OBJECTIVITY RULES:\n"
            "1. DO NOT force a bias change or flip existing market regime if the catalyst does not justify it. "
            "Financial markets frequently experience news that simply CONFIRMS, REINFORCES, or ALIGNS WITH the established trend.\n"
            "2. If the incoming event/data aligns with or strengthens the current currency bias, you MUST maintain "
            "the existing bias and explicitly declare it as REINFORCING the current thesis (catalyst_impact='REINFORCES_EXISTING_BIAS').\n"
            "3. Evaluate if the catalyst was ALREADY PRICED-IN by the market before this event occurred. "
            "If priced-in, do NOT create artificial sentiment shocks.\n"
            "4. Only adjust directional currency bias or macro regime if the data objectively and significantly "
            "CONTRADICTS or INVALIDATES the baseline (e.g. unexpected rate decision, severe geopolitical shock, major statistical surprise).\n"
            "5. Return strictly a JSON object conforming to the required schema."
        )

        delta_schema = {
            "type": "object",
            "properties": {
                "has_thesis_changed": {
                    "type": "boolean",
                    "description": "True only if the core macro thesis or currency direction is fundamentally altered",
                },
                "catalyst_impact": {
                    "type": "string",
                    "enum": ["REINFORCES_EXISTING_BIAS", "INVALIDATES_BIAS", "MARKET_NOISE", "ALREADY_PRICED_IN"],
                },
                "revision_summary": {
                    "type": "string",
                    "description": "Concise 1-3 sentence summary explaining whether the catalyst changes or reinforces the macro picture",
                },
                "currency_bias_adjustments": {
                    "type": "object",
                    "description": "Key-value of currency (e.g. USD, EUR, GBP, XAU) to updated bias ('bullish', 'bearish', 'neutral'). Only include affected currencies.",
                },
                "macro_regime_adjustment": {
                    "type": "string",
                    "description": "Updated macro regime or null if unchanged",
                },
                "risk_sentiment_adjustment": {
                    "type": "string",
                    "enum": ["risk-on", "risk-off", "mixed"],
                    "description": "Updated risk sentiment or null if unchanged",
                },
                "confidence_delta": {
                    "type": "number",
                    "description": "Confidence adjustment between -0.3 and +0.3 (positive if reinforced, negative if uncertain)",
                },
            },
            "required": ["has_thesis_changed", "catalyst_impact", "revision_summary", "currency_bias_adjustments"],
        }

        curr_regime = (
            current_brief.macro_regime
            if isinstance(getattr(current_brief, "macro_regime", None), str)
            else baseline_structured.get("macro_regime", "mixed")
        )
        curr_sentiment = (
            current_brief.risk_sentiment
            if isinstance(getattr(current_brief, "risk_sentiment", None), str)
            else baseline_structured.get("risk_sentiment", "mixed")
        )
        curr_bias = (
            current_brief.currency_bias
            if isinstance(getattr(current_brief, "currency_bias", None), dict)
            else baseline_structured.get("currency_bias", {})
        )
        narrative_text = (current_brief.content_markdown or "")[:500]

        now_utc = clock.now()
        user_prompt = (
            f"INCOMING CATALYST TYPE: {catalyst_type}\n"
            f"AFFECTED CURRENCIES CANDIDATES: {affected_currencies or 'Global/All'}\n\n"
            f"--- INCOMING MARKET CATALYST ---\n{catalyst_text.strip()}\n\n"
            f"--- CURRENT BASELINE BRIEF (ID #{current_brief.id}, Generated {current_brief.generated_at}) ---\n"
            f"Macro Regime: {curr_regime}\n"
            f"Risk Sentiment: {curr_sentiment}\n"
            f"Confidence: {current_brief.confidence}\n"
            f"Current Currency Bias: {json.dumps(curr_bias)}\n"
            f"Baseline Narrative: {narrative_text}\n\n"
            "Task: Evaluate this catalyst against the baseline. Does it reinforce, contradict, or is it noise? Output valid JSON.\n\n"
            f"[EXECUTION_METADATA]: Current time is {now_utc.strftime('%Y-%m-%d %H:%M UTC')}"
        )

        res = None
        if hasattr(client, "classify_json"):
            res = await client.classify_json(prompt=user_prompt, system_prompt=system_prompt, schema=delta_schema)
        elif hasattr(client, "generate_json"):
            res = await client.generate_json(prompt=user_prompt, system_prompt=system_prompt, schema=delta_schema)
        elif hasattr(client, "generate"):
            raw_text = await client.generate(prompt=f"{system_prompt}\n\n{user_prompt}")
            try:
                clean = re.sub(r"^```json\s*|\s*```$", "", str(raw_text).strip(), flags=re.MULTILINE)
                res = json.loads(clean)
            except Exception:
                res = None

        if not isinstance(res, dict):
            logger.warning(f"[MacroDeltaPatch] LLM response invalid ({res}), keeping existing brief intact.")
            return current_brief

        updated_structured = dict(baseline_structured)
        current_biases = dict(updated_structured.get("currency_bias", {}))
        bias_adjs = res.get("currency_bias_adjustments") or {}
        if isinstance(bias_adjs, dict):
            for curr, new_b in bias_adjs.items():
                if new_b and isinstance(new_b, str):
                    clean_b = new_b.lower().strip()
                    if clean_b in ("bullish", "strong_bullish", "bearish", "strong_bearish", "neutral"):
                        current_biases[curr.upper()] = clean_b
        updated_structured["currency_bias"] = current_biases

        if res.get("macro_regime_adjustment"):
            updated_structured["macro_regime"] = str(res["macro_regime_adjustment"]).lower()
        if res.get("risk_sentiment_adjustment"):
            updated_structured["risk_sentiment"] = str(res["risk_sentiment_adjustment"]).lower()

        rev_summary = res.get("revision_summary", "Delta update applied.")
        impact_tag = res.get("catalyst_impact", "REINFORCES_EXISTING_BIAS")
        updated_structured["last_catalyst"] = {
            "type": catalyst_type,
            "impact": impact_tag,
            "summary": rev_summary,
            "timestamp": now_utc.isoformat(),
        }

        old_conf = float(current_brief.confidence or 0.7)
        conf_delta = float(res.get("confidence_delta", 0.0) or 0.0)
        new_conf = max(0.1, min(1.0, round(old_conf + conf_delta, 2)))
        updated_structured["confidence"] = new_conf

        new_markdown = (
            f"{current_brief.content_markdown or ''}\n\n"
            f"---\n"
            f"**[MACRO DELTA REVISION - {now_utc.strftime('%Y-%m-%d %H:%M UTC')} | Catalyst: {catalyst_type.upper()}]**\n"
            f"â€¢ Impact: **{impact_tag}**\n"
            f"â€¢ Assessment: {rev_summary}\n"
            f"â€¢ Thesis Shift: {'YES (Shift)' if res.get('has_thesis_changed') else 'NO (Reinforced / Noise)'}\n"
        )

        new_brief = FundamentalBrief(
            generated_at=now_utc,
            valid_until=current_brief.valid_until or (now_utc + timedelta(hours=8)),
            content_markdown=new_markdown,
            structured_json=json.dumps(updated_structured),
            confidence=new_conf,
            risk_sentiment=updated_structured.get("risk_sentiment", current_brief.risk_sentiment),
            debate_bull_thesis=f"Delta catalyst: {rev_summary}",
            debate_bear_thesis=f"Baseline regime: {current_brief.macro_regime}",
            debate_winner="DELTA_REVISION" if res.get("has_thesis_changed") else "DELTA_REINFORCED",
            debate_escalation_required=False,
        )
        session.add(new_brief)
        await session.commit()
        await session.refresh(new_brief)
        logger.info(
            f"[MacroDeltaPatch] Berhasil membuat FundamentalBrief Delta (id={new_brief.id}, "
            f"impact={impact_tag}, changed={res.get('has_thesis_changed')})"
        )
        await stage_instance._log(
            session,
            f"Macro Delta Revision #{new_brief.id} applied ({impact_tag}): {rev_summary[:120]}",
            category="analysis",
        )
        return new_brief
    except Exception as e:
        logger.error(f"[MacroDeltaPatch] Error in delta revision: {e}", exc_info=True)
        return current_brief
