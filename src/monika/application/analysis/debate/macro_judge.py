import json
import logging
from typing import Any, Optional

from monika.infrastructure.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.MacroJudge")

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "bull_arguments_score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Objective score (1-10) for the Risk-On / Dollar-Bear thesis based on empirical data quality.",
        },
        "bear_arguments_score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Objective score (1-10) for the Risk-Off / Dollar-Bull thesis based on empirical data quality.",
        },
        "rationale": {
            "type": "string",
            "description": "Detailed explanation of why one thesis prevailed over the other based on macro data.",
        },
        "winner": {
            "type": "string",
            "enum": ["RISK_ON_USD_BEAR", "RISK_OFF_USD_BULL", "US_EXCEPTIONALISM", "STAGFLATION", "TIE"],
            "description": "Winner of the debate. 'RISK_ON_USD_BEAR' means risk-on / weak dollar thesis won. 'RISK_OFF_USD_BULL' means risk-off / strong dollar thesis won. 'US_EXCEPTIONALISM' means both USD and US risk assets are bullish. 'STAGFLATION' means risk assets and USD are both struggling. 'TIE' if balanced.",
        },
        "dxy_bias": {
            "type": "string",
            "enum": ["BULLISH", "BEARISH", "NEUTRAL"],
            "description": "Directional bias for US Dollar Index (DXY). MANDATORY: If RISK_ON_USD_BEAR won, dxy_bias MUST be BEARISH. If RISK_OFF_USD_BULL or US_EXCEPTIONALISM won, dxy_bias MUST be BULLISH.",
        },
        "risk_asset_bias": {
            "type": "string",
            "enum": ["BULLISH", "BEARISH", "NEUTRAL"],
            "description": "Directional bias for Risk Assets (equities, crypto, commodities, pro-cyclical FX). MANDATORY: If RISK_ON_USD_BEAR or US_EXCEPTIONALISM won, risk_asset_bias MUST be BULLISH. If RISK_OFF_USD_BULL or STAGFLATION won, risk_asset_bias MUST be BEARISH.",
        },
        "escalation_required": {
            "type": "boolean",
            "description": "True if score difference <= 1, high uncertainty, severe data contradiction, or TIE.",
        },
    },
    "required": [
        "bull_arguments_score",
        "bear_arguments_score",
        "rationale",
        "winner",
        "dxy_bias",
        "risk_asset_bias",
        "escalation_required",
    ],
}


async def run_macro_judge(
    bull_thesis: dict | str,
    bear_thesis: dict | str,
    context: str,
    settings: dict,
    tool_executor: Optional[Any] = None,
) -> dict:
    """
    Executes Chief Macro Judge to evaluate Risk-On/Dollar-Bear vs Risk-Off/Dollar-Bull debate.
    When agentic mode is enabled and client supports run_chat_loop, Judge performs an active
    fact-checking turn using macro verification tools to resolve factual disputes between analysts.
    """
    try:
        client = get_client_for_task("debate_judge", settings)
    except Exception:
        client = get_client_for_task("stage1_fundamental", settings)

    bull_str = json.dumps(bull_thesis, indent=2) if isinstance(bull_thesis, dict) else str(bull_thesis)
    bear_str = json.dumps(bear_thesis, indent=2) if isinstance(bear_thesis, dict) else str(bear_thesis)

    from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

    anchor = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()

    adj_skill_text = ""
    try:
        from monika.application.skills.loader import load_skill

        adj_skill = load_skill("adjudication-framework")
        if adj_skill:
            adj_skill_text = f"\n\n[AUTHORITATIVE ADJUDICATION SKILL]\n{adj_skill[:3500]}\n"
    except Exception:
        pass

    system_prompt = (
        f"{anchor}{adj_skill_text}\n\n---\n\n"
        "You are the CHIEF MACRO JUDGE.\n"
        "Your responsibility is to objectively adjudicate a macroeconomic debate between two opposing analysts:\n"
        "1. Analyst 1: Risk-On / Dollar-Bear Thesis (Bullish Risk Assets, Bearish USD)\n"
        "2. Analyst 2: Risk-Off / Dollar-Bull Thesis (Bearish Risk Assets, Bullish USD)\n\n"
        "CRITICAL LOGICAL MAPPING RULES:\n"
        "- If Analyst 1 (Risk-On / Dollar-Bear) has stronger data: winner='RISK_ON_USD_BEAR', dxy_bias='BEARISH', risk_asset_bias='BULLISH'.\n"
        "- If Analyst 2 (Risk-Off / Dollar-Bull) has stronger data: winner='RISK_OFF_USD_BULL', dxy_bias='BULLISH', risk_asset_bias='BEARISH'.\n"
        "- If economic growth/yield divergence favors strong USD alongside resilient equities (US Exceptionalism): winner='US_EXCEPTIONALISM', dxy_bias='BULLISH', risk_asset_bias='BULLISH'.\n"
        "- If both sides are equally balanced or data is contradictory: check TIE-BREAKING PROTOCOL below before declaring TIE.\n"
        "- TIE-BREAKING PROTOCOL: If scores are tied (e.g. 5 vs 5 or 6 vs 6), prioritize dominant Higher Timeframe Trend (DXY D1 trend and Real US 10Y Yield slope). Only award 'TIE' (dxy_bias='NEUTRAL', escalation_required=True) if HTF trend is also flat/indecisive.\n\n"
        "MANDATORY FACT-CHECKING CHECKLIST:\n"
        "1. Score higher ONLY the thesis that cites concrete, grounded macro data (Yield curve slope, FedWatch probabilities, COT net positioning, recent CPI/NFP figures).\n"
        "2. Rhetorical or speculative arguments unsupported by the provided DATA CONTEXT must be awarded <= 4 points.\n"
        "3. Active Fact-Checking: If Analyst 1 and Analyst 2 present contradictory assertions regarding yields, rate cut odds, or spreads, call verification tools to obtain ground truth.\n"
        "4. Penalize Fabrication: Any analyst claiming fabricated, inverted, or hallucinated figures must be awarded <= 2 points.\n"
    )

    prompt = f"""DATA CONTEXT:
{context}

=== TIER 2 CYCLE CACHE BREAKPOINT ===

Adjudicate the macro debate based strictly on the empirical data context and analyst arguments.

BULL ANALYST (Risk-On / Dollar-Bear):
{bull_str}

BEAR ANALYST (Risk-Off / Dollar-Bull):
{bear_str}

Evaluate the merits, assign scores (1-10), declare the winner ('RISK_ON_USD_BEAR', 'RISK_OFF_USD_BULL', 'US_EXCEPTIONALISM', 'STAGFLATION', or 'TIE'), set dxy_bias and risk_asset_bias according to the mapping rules, and set escalation_required to true if score difference <= 1 or arguments are closely contested."""

    is_agentic = bool(settings.get("analysis", {}).get("agentic", {}).get("enabled", True))

    try:
        res: Optional[dict] = None
        if is_agentic and hasattr(client, "run_chat_loop") and tool_executor is not None:
            from monika.application.analysis.tools.tools_definitions import (
                MACRO_ANALYSIS_TOOLS,
                minify_tool_definitions,
            )

            macro_verification_names = {
                "get_bond_yield_spreads",
                "get_treasury_yields",
                "get_interest_rates",
                "get_central_bank_expectations",
                "get_fedwatch_probabilities",
                "get_vix",
                "get_dxy",
                "web_search",
            }
            judge_tools = minify_tool_definitions(
                [
                    t
                    for t in MACRO_ANALYSIS_TOOLS
                    if (t.get("name") or t.get("function", {}).get("name")) in macro_verification_names
                ]
            )
            agentic_user_prompt = (
                f"================================================================================\n"
                f"DIALECTICAL DEBATE ADJUDICATION CONTRACT\n"
                f"================================================================================\n"
                f"DATA CONTEXT:\n{context}\n\n"
                f"ANALYST 1 (BULL THESIS - RISK-ON / USD WEAKNESS):\n{bull_str}\n\n"
                f"ANALYST 2 (BEAR THESIS - RISK-OFF / USD STRENGTH):\n{bear_str}\n\n"
                f"ADJUDICATION MANDATE:\n"
                f"1. SCAN FOR FACTUAL DISPUTES: Check if Bull and Bear make conflicting claims regarding US Treasury yields, CME FedWatch rate probabilities, DXY levels, or sovereign yield spreads.\n"
                f"2. VERIFICATION TURN: If a dispute exists, call the relevant tool (e.g., `get_fedwatch_probabilities`, `get_treasury_yields`, `get_bond_yield_spreads`, `web_search`) to verify market reality.\n"
                f"3. FINAL RULING: Formulate your definitive verdict in valid JSON matching this schema:\n"
                f"```json\n"
                f'{{\n  "bull_arguments_score": <1-10>,\n  "bear_arguments_score": <1-10>,\n  "rationale": "<Detailed factual explanation citing verified numbers>",\n  "winner": "<RISK_ON_USD_BEAR | RISK_OFF_USD_BULL | US_EXCEPTIONALISM | STAGFLATION | TIE>",\n  "dxy_bias": "<BULLISH | BEARISH | NEUTRAL>",\n  "risk_asset_bias": "<BULLISH | BEARISH | NEUTRAL>",\n  "escalation_required": <true | false>\n}}\n'
                f"```\n"
                f"================================================================================\n"
                f"Begin by identifying disputes and calling verification tools."
            )
            chat_res = await client.run_chat_loop(
                system_prompt=system_prompt,
                conversation_history=[],
                new_user_message=agentic_user_prompt,
                tools=judge_tools,
                tool_executor=tool_executor,
            )
            content = (
                chat_res.get("reply") or chat_res.get("content") or (chat_res if isinstance(chat_res, str) else "")
            )
            if content:
                import re

                cleaned = str(content).strip()
                if "```" in cleaned:
                    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
                    if match:
                        cleaned = match.group(1).strip()
                if "{" in cleaned and "}" in cleaned:
                    start = cleaned.find("{")
                    end = cleaned.rfind("}") + 1
                    cleaned = cleaned[start:end]
                try:
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, dict) and "winner" in parsed and "bull_arguments_score" in parsed:
                        res = parsed
                except Exception:
                    pass

        if not res:
            res = await client.classify_json(prompt=prompt, schema=JUDGE_SCHEMA, system_prompt=system_prompt)
        if not res or not isinstance(res, dict):
            raise ValueError("Judge evaluation returned empty/None result")
        # Fail-closed escalation if either upstream analyst returned degraded fallback
        bull_degraded = isinstance(bull_thesis, dict) and (
            bull_thesis.get("degraded_fallback") or bull_thesis.get("is_fallback")
        )
        bear_degraded = isinstance(bear_thesis, dict) and (
            bear_thesis.get("degraded_fallback") or bear_thesis.get("is_fallback")
        )
        if bull_degraded or bear_degraded:
            res["escalation_required"] = True
            logger.warning("[MacroJudge] Upstream macro debate participant degraded; escalation_required enforced.")
        return res
    except Exception as e:
        logger.error(f"Macro Judge failed: {e}")
        return {
            "bull_arguments_score": 5,
            "bear_arguments_score": 5,
            "winner": "TIE",
            "dxy_bias": "NEUTRAL",
            "risk_asset_bias": "NEUTRAL",
            "rationale": f"Fallback due to judge error: {e}",
            "escalation_required": True,
        }
