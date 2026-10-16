# ==============================================================================
# File: application/benchmark/task_specs/macro_cases.py
# ==============================================================================

"""
Macro analysis, escalation, verification, and synthesis benchmark task specs.
"""

from __future__ import annotations

import json
from typing import Any

from monika.application.analysis.prefetch.stage1_prefetcher import Stage1DataBundler
from monika.application.analysis.stages.fundamental_stage import USER_MESSAGE as STAGE1_USER_MESSAGE_TEXT
from monika.application.analysis.tools.tools_definitions import MACRO_ANALYSIS_TOOLS
from monika.application.analysis.validators.fundamental_verifier import (
    FUNDAMENTAL_VERIFIER_SYSTEM_PROMPT,
    VERIFIER_SCHEMA,
)
from monika.application.skills.loader import compose_system_prompt

from ..db_access import latest_brief
from ..fixture_loader import (
    get_golden_escalation_crisis,
    get_golden_shadow_check_audit,
    get_synthetic_compaction_payload,
    get_synthetic_fomc_transcript_payload,
    get_synthetic_fundamental_brief,
    get_synthetic_macro_anomaly_payload,
    get_synthetic_session_reports_payload,
    get_synthetic_stage1_bundle,
)
from .base import BenchmarkCase


def _stage1_system_prompt(settings: dict[str, Any]) -> str:
    skills = [
        "macro_analysis_framework",
        "market_dynamics_framework",
        "performance_notes",
        "fundamental_performance_notes",
    ]
    if settings.get("trading", {}).get("caveman_mode", False):
        skills.append("caveman_mode")
    return compose_system_prompt(*skills)


async def _case_stage1_fundamental(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    bundle = None
    if not use_fixtures and session:
        try:
            bundle, _, _ = await Stage1DataBundler(session, settings).prefetch_all_data()
        except Exception:
            bundle = None
    if not bundle:
        bundle = get_synthetic_stage1_bundle()
    user_msg = STAGE1_USER_MESSAGE_TEXT + f"\n\n[PRE-FETCHED DATA]\n{bundle}"
    return BenchmarkCase(
        "stage1",
        "macro",
        _stage1_system_prompt(settings),
        user_msg,
        tools=MACRO_ANALYSIS_TOOLS,
        stage_name="benchmark_stage1_fundamental",
        role_kwargs=dict(max_tokens=12000, max_tool_turns=8, thinking="high"),
        context_summary=bundle,
    )


async def _case_stage1_escalation(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    bundle = None
    if not use_fixtures and session:
        try:
            bundle, _, _ = await Stage1DataBundler(session, settings).prefetch_all_data()
        except Exception:
            bundle = None
    if not bundle:
        bundle = get_synthetic_stage1_bundle()
    prior_json = "{}"
    if use_fixtures:
        esc = get_golden_escalation_crisis()
        cat = esc.get("catalyst_event", {})
        prior_json = json.dumps(get_synthetic_fundamental_brief())
        escalation_note = f"\n\n--- CRITICAL ESCALATION TRIGGER ---\n{cat.get('headline')}\nImpact: {cat.get('impact')} | Source: {cat.get('source')}\nRe-evaluate macro regime and risk posture under acute crisis shock."
    elif session:
        try:
            prior_json = (await latest_brief(session)).structured_json or "{}"
        except Exception:
            pass
        escalation_note = "\n\n--- ESCALATION REQUIRED ---\nPrior brief had low confidence. Re-evaluate exhaustively with maximum rigor, resolving all ambiguities explicitly."
    else:
        prior_json = json.dumps(get_synthetic_fundamental_brief())
        escalation_note = "\n\n--- ESCALATION REQUIRED ---\nPrior brief had low confidence."

    user_msg = (
        STAGE1_USER_MESSAGE_TEXT + f"\n\n[PRE-FETCHED DATA]\n{bundle}{escalation_note}\nPRIOR BRIEF:\n{prior_json}"
    )
    return BenchmarkCase(
        "stage1_escalation",
        "macro",
        _stage1_system_prompt(settings),
        user_msg,
        tools=MACRO_ANALYSIS_TOOLS,
        stage_name="benchmark_stage1_escalation",
        role_kwargs=dict(max_tokens=16000, max_tool_turns=8, thinking="high"),
        context_summary=bundle[:6000],
    )


_SHADOW_SCHEMA = {
    "type": "object",
    "properties": {
        "currency_bias": {"type": "object"},
        "agreement_pct": {"type": "number"},
        "flagged_currencies": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["currency_bias", "agreement_pct", "flagged_currencies"],
}


async def _case_stage1_shadow_check(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    bundle = None
    if not use_fixtures and session:
        try:
            bundle, _, _ = await Stage1DataBundler(session, settings).prefetch_all_data()
        except Exception:
            bundle = None
    if not bundle:
        bundle = get_synthetic_stage1_bundle()
    declared_bias = {}
    if use_fixtures:
        audit_case = get_golden_shadow_check_audit()
        draft = audit_case.get("proposed_draft_brief", {})
        declared_bias = draft.get("currency_bias", {})
    elif session:
        try:
            declared_bias = json.loads((await latest_brief(session)).structured_json or "{}").get("currency_bias", {})
        except Exception:
            pass
    if not declared_bias:
        declared_bias = get_synthetic_fundamental_brief().get("currency_bias", {})
    prompt = (
        "Independently determine USD/EUR/GBP/JPY/AUD/XAU bias "
        "(bullish/bearish/neutral) based SOLELY on the following raw data:\n"
        + bundle
        + f"\n\nThe brief being verified concluded: {json.dumps(declared_bias)}\n"
        "Calculate agreement_pct and list any diverging flagged_currencies."
    )
    return BenchmarkCase(
        "stage1_shadow_check",
        "macro",
        "",
        prompt,
        schema=_SHADOW_SCHEMA,
        role_kwargs=dict(max_tokens=1200, thinking="low"),
        context_summary=bundle[:8000],
    )


async def _case_fundamental_verifier(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    st = {}
    if not use_fixtures and session:
        try:
            brief = await latest_brief(session)
            st = json.loads(brief.structured_json or "{}")
        except Exception:
            pass
    if not st:
        st = get_synthetic_fundamental_brief()
    prompt = f"""Narrative:
{st.get("macro_narrative", "")}

Currency Bias: {json.dumps(st.get("currency_bias", {}))}
Currency Confidence: {json.dumps(st.get("currency_confidence", {}))}
Risk Sentiment: {st.get("risk_sentiment")}
Overall Confidence: {st.get("confidence")}
Invalidation Conditions: {json.dumps(st.get("invalidation_conditions", {}))}
Strongest Counter Thesis: {st.get("strongest_counter_thesis")}"""
    return BenchmarkCase(
        "fundamental_verifier",
        "macro",
        system_prompt=FUNDAMENTAL_VERIFIER_SYSTEM_PROMPT,
        user_prompt=prompt,
        schema=VERIFIER_SCHEMA,
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=prompt[:4000],
    )


async def _case_deep_research(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    prompt = (
        "Conduct a deep macroeconomic research report analyzing the divergence between US Fed (+25bps hike to 3.75-4.00%) "
        "and ECB (+25bps to 2.50%) against the backdrop of the Middle East energy shock ($106 Brent). "
        "Evaluate the net impact on EUR/USD cross-asset liquidity and institutional positioning."
    )
    return BenchmarkCase(
        "deep_research",
        "macro",
        system_prompt="You are a Senior Quantitative Macro Researcher. Provide in-depth analysis citing specific yields, spreads, and liquidity dynamics.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=8192, thinking="high"),
        context_summary=prompt,
    )


async def _case_strategy_discovery(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    prompt = (
        "Discover and synthesize quantitative trading strategy hypotheses for forex and gold "
        "leveraging recent macroeconomic regime shifts, yield spreads, and volatility conditions."
    )
    return BenchmarkCase(
        "strategy_discovery",
        "macro",
        system_prompt="You are a Quantitative Strategy Discovery specialist. Propose structured strategy hypotheses with edge thesis, entry triggers, and risk invalidation.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=8192, thinking="none"),
        context_summary=prompt,
    )


async def _case_report_synthesizer(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    reports = get_synthetic_session_reports_payload()
    prompt = (
        "Synthesize an end-of-cycle executive portfolio brief across EURUSD, GBPUSD, USDJPY, and XAUUSD based on today's session reports below.\n\n"
        f"{reports}\n\n"
        "Instructions: Synthesize macro cross-currents, evaluate portfolio correlation risks, rank proposed opportunities by expected risk-adjusted edge, "
        "and formulate clear capital allocation recommendations for the upcoming Asian/London rollover."
    )
    return BenchmarkCase(
        "report_synthesizer",
        "macro",
        system_prompt="You are an Executive Trading Desk Synthesizer. Synthesize multi-asset reports into risk allocations, currency exposures, and trade prioritization.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=4096, thinking="medium"),
        context_summary=reports[:6000],
    )


async def _case_context_compaction(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    raw_payload = get_synthetic_compaction_payload()
    prompt = (
        "Compress the following 12-page economic calendar and news transcript into a strict 400-token high-signal fact sheet.\n\n"
        f"[RAW UNFILTERED DATA TRANSCRIPT]\n{raw_payload}\n\n"
        "Requirements: Retain all exact numerical prints, surprises, bond yields, spreads, and high-impact policy statements without hallucination."
    )
    return BenchmarkCase(
        "context_compaction",
        "macro",
        system_prompt="You are a lossless context compression engine. Retain all exact numbers, rates, and quotes.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=raw_payload[:6000],
    )


async def _case_summarizer(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    transcript = get_synthetic_fomc_transcript_payload()
    prompt = (
        "Provide a 3-bullet progressive summary of the latest FOMC press conference transcript below.\n\n"
        f"[FOMC TRANSCRIPT]\n{transcript}\n\n"
        "Requirements:\n"
        "- Bullet 1: Core policy decision and economic assessment (labor & inflation).\n"
        "- Bullet 2: Reaction function to energy shock and guidance on rate trajectory.\n"
        "- Bullet 3: Actionable takeaway for FX and rate traders."
    )
    return BenchmarkCase(
        "summarizer",
        "macro",
        system_prompt="You are an ultra-concise financial summarizer. Extract monetary policy posture, data dependencies, and risk shifts.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=512, thinking="low"),
        context_summary=transcript[:4000],
    )


async def _case_macro_analyst(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    anomaly_data = get_synthetic_macro_anomaly_payload()
    prompt = (
        "Investigate the real-yield divergence anomaly between US TIPS and German Bunds during the recent crude oil spike based on the market data below.\n\n"
        f"{anomaly_data}\n\n"
        "Provide in-depth quantitative analysis explaining causal mechanisms, transmission channels to EUR/USD, terms-of-trade degradation, and central bank reaction functions."
    )
    return BenchmarkCase(
        "macro_analyst",
        "macro",
        system_prompt="You are a Macro Anomaly Specialist. Analyze real yield divergence, terms-of-trade degradation, and central bank reaction functions.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=4096, thinking="high"),
        context_summary=anomaly_data[:4000],
    )
