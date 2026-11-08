# ==============================================================================
# File: application/analysis/stages/fundamental_debate.py
# ==============================================================================

"""
Macro Debate Execution Helper for FundamentalStage.
Runs Bull/Bear/Judge adversarial multi-agent debate before finalizing macro briefs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.FundamentalStage")


async def run_macro_debate(stage_instance, session: AsyncSession, brief, prefetched_data: Optional[Any] = None) -> dict:
    """Menjalankan debate Bull/Bear/Judge macro. Dijalankan SEBELUM keputusan eskalasi
    difinalisasi, supaya kontradiksi yang ditemukan debate bisa memicu eskalasi ke Opus
    (bukan cuma pasif menurunkan confidence)."""
    outcome = {
        "ran": False,
        "winner": "TIE",
        "legacy_winner": "TIE",
        "escalation_required": False,
        "contradicts_usd_bias": False,
        "internal_hallucination": False,
    }
    if not stage_instance.settings.get("agent_architecture", {}).get("enable_debate", False):
        return outcome
    try:
        from monika.application.analysis.debate.macro_bear_analyst import run_bear_analyst
        from monika.application.analysis.debate.macro_bull_analyst import run_bull_analyst
        from monika.application.analysis.debate.macro_debate_validator import validate_macro_judge_output
        from monika.application.analysis.debate.macro_judge import run_macro_judge

        chronicle_bullets = ""
        try:
            from monika.application.analysis.memory.chronicle_writer import ChronicleWriter

            c_writer = ChronicleWriter(stage_instance.settings)
            chronicle_bullets = await c_writer.get_condensed_chronicle_bullets(session, limit=4)
        except Exception:
            pass
        context = "BRIEF SO FAR:\n" + (brief.structured_json or brief.content_markdown or "")
        if chronicle_bullets:
            context = f"ACTIVE MACRO CHRONICLE (Ongoing Structural Regimes):\n{chronicle_bullets}\n\n{context}"
        if prefetched_data:
            if isinstance(prefetched_data, str):
                try:
                    pref_dict = json.loads(prefetched_data)
                except Exception:
                    pref_dict = None
            else:
                pref_dict = prefetched_data

            if isinstance(pref_dict, dict):
                macro_blocks = []
                for k in (
                    "central_bank_rates",
                    "cb_redline_diff",
                    "dxy",
                    "bond_yields",
                    "vix",
                    "cme_fedwatch",
                    "economic_calendar",
                    "cot_report",
                    "news_digest",
                ):
                    if k in pref_dict:
                        v_str = json.dumps(pref_dict[k], default=str)
                        macro_blocks.append(f"[{k.upper()}]:\n{v_str[:2500]}")
                pref_str = "\n\n".join(macro_blocks) if macro_blocks else json.dumps(pref_dict, default=str)[:15000]
            else:
                pref_str = str(prefetched_data)[:15000]
            context = f"RAW PREFETCHED MACRO DATA (Ground Truth):\n{pref_str}\n\n{context}"
        # Run macro bull and bear analysts concurrently
        bull_res, bear_res = await asyncio.gather(
            run_bull_analyst(context, stage_instance.settings),
            run_bear_analyst(context, stage_instance.settings),
            return_exceptions=True,
        )
        if isinstance(bull_res, BaseException):
            logger.error(f"Macro bull analyst failed: {bull_res}")
            bull = {"error": str(bull_res)}
        else:
            bull = bull_res

        if isinstance(bear_res, BaseException):
            logger.error(f"Macro bear analyst failed: {bear_res}")
            bear = {"error": str(bear_res)}
        else:
            bear = bear_res

        executor = getattr(stage_instance, "tool_executor", None)
        if executor is None and session is not None:
            try:
                from monika.application.analysis.tools.tool_executor import ToolExecutor

                executor = ToolExecutor(session, stage_instance.settings)
            except Exception:
                executor = None

        try:
            judge_raw = await run_macro_judge(bull, bear, context, stage_instance.settings, tool_executor=executor)
        except TypeError:
            judge_raw = await run_macro_judge(bull, bear, context, stage_instance.settings)
        judge = validate_macro_judge_output(judge_raw, bull, bear)

        bull_str = json.dumps(bull, indent=2) if isinstance(bull, dict) else str(bull)
        bear_str = json.dumps(bear, indent=2) if isinstance(bear, dict) else str(bear)
        brief.debate_bull_thesis = bull_str
        brief.debate_bear_thesis = bear_str
        brief.debate_winner = judge.get("winner", "TIE")
        brief.debate_escalation_required = judge.get("escalation_required", False)

        outcome.update(
            {
                "ran": True,
                "winner": brief.debate_winner,
                "legacy_winner": judge.get("legacy_winner", "TIE"),
                "dxy_bias": judge.get("dxy_bias", "NEUTRAL"),
                "risk_asset_bias": judge.get("risk_asset_bias", "NEUTRAL"),
                "bull_score": judge.get("bull_arguments_score", 5),
                "bear_score": judge.get("bear_arguments_score", 5),
                "escalation_required": brief.debate_escalation_required,
                "internal_hallucination": judge.get("internal_hallucination_detected", False),
            }
        )

        if brief.structured_json:
            b_data = json.loads(brief.structured_json)
            b_data["debate_winner"] = brief.debate_winner
            b_data["debate_winner_legacy"] = judge.get("legacy_winner", "TIE")
            b_data["debate_bull_thesis"] = bull
            b_data["debate_bear_thesis"] = bear
            b_data["debate_bull_score"] = judge.get("bull_arguments_score", 5)
            b_data["debate_bear_score"] = judge.get("bear_arguments_score", 5)
            b_data["debate_rationale"] = judge.get("rationale", "")
            b_data["dxy_bias_from_judge"] = judge.get("dxy_bias", "NEUTRAL")
            b_data["risk_asset_bias_from_judge"] = judge.get("risk_asset_bias", "NEUTRAL")
            b_data["debate_hallucination_detected"] = judge.get("internal_hallucination_detected", False)

            if judge.get("internal_hallucination_detected"):
                reasons_str = "; ".join(judge.get("hallucination_reasons", []))
                b_data["macro_narrative"] = b_data.get("macro_narrative", "") + (
                    f"\n\n[SYSTEM: Macro debate judge output contains internal inconsistencies: {reasons_str}. "
                    f"Confidence penalized and escalated.]"
                )
                brief.confidence = min(brief.confidence or 0.7, 0.65)

            from monika.domain.market.bias_utils import normalize_bias

            norm_dxy = normalize_bias(judge.get("dxy_bias"))
            norm_usd = normalize_bias(b_data.get("currency_bias", {}).get("USD"))
            if (norm_dxy == "bullish" and norm_usd == "bearish") or (norm_dxy == "bearish" and norm_usd == "bullish"):
                outcome["contradicts_usd_bias"] = True
                b_data["macro_narrative"] = b_data.get("macro_narrative", "") + (
                    f"\n\n[SYSTEM: Macro debate judge concluded DXY bias={norm_dxy}, while "
                    f"currency_bias['USD']={norm_usd}. Contradiction detected â€” escalated for adjudication.]"
                )
                brief.confidence = min(brief.confidence or 0.7, 0.70)
            brief.structured_json = json.dumps(b_data)
        await session.commit()
        logger.info(
            f"Macro Debate selesai. Winner: {brief.debate_winner} "
            f"(Bull: {judge.get('bull_arguments_score')}/10 vs Bear: {judge.get('bear_arguments_score')}/10 | "
            f"DXY Bias: {judge.get('dxy_bias')}, Risk Assets: {judge.get('risk_asset_bias')}), "
            f"escalation_required={outcome['escalation_required']}, "
            f"contradicts_usd={outcome['contradicts_usd_bias']}, "
            f"hallucination={outcome['internal_hallucination']}"
        )
    except Exception as e:
        logger.error(f"Macro debate failed: {e}")
    return outcome
