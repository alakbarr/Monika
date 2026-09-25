import logging
import json
from analysis.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.MacroJudge")

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "bull_arguments_score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Objective score (1-10) for the Risk-On / Dollar-Bear thesis based on empirical data quality."
        },
        "bear_arguments_score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Objective score (1-10) for the Risk-Off / Dollar-Bull thesis based on empirical data quality."
        },
        "winner": {
            "type": "string",
            "enum": ["RISK_ON_USD_BEAR", "RISK_OFF_USD_BULL", "US_EXCEPTIONALISM", "STAGFLATION", "TIE", "BULL", "BEAR"],
            "description": "Winner of the debate. 'RISK_ON_USD_BEAR' (or BULL) means risk-on/weak dollar won. 'RISK_OFF_USD_BULL' (or BEAR) means risk-off/strong dollar won. 'US_EXCEPTIONALISM' means both USD and US risk assets are bullish. 'STAGFLATION' means risk assets and USD are both struggling. 'TIE' if balanced."
        },
        "dxy_bias": {
            "type": "string",
            "enum": ["BULLISH", "BEARISH", "NEUTRAL"],
            "description": "Directional bias for US Dollar Index (DXY). MANDATORY: If RISK_ON_USD_BEAR won, dxy_bias MUST be BEARISH. If RISK_OFF_USD_BULL or US_EXCEPTIONALISM won, dxy_bias MUST be BULLISH."
        },
        "risk_asset_bias": {
            "type": "string",
            "enum": ["BULLISH", "BEARISH", "NEUTRAL"],
            "description": "Directional bias for Risk Assets (equities, crypto, commodities, pro-cyclical FX). MANDATORY: If RISK_ON_USD_BEAR or US_EXCEPTIONALISM won, risk_asset_bias MUST be BULLISH. If RISK_OFF_USD_BULL or STAGFLATION won, risk_asset_bias MUST be BEARISH."
        },
        "rationale": {
            "type": "string",
            "description": "Detailed explanation of why one thesis prevailed over the other based on macro data."
        },
        "escalation_required": {
            "type": "boolean",
            "description": "True if score difference <= 1, high uncertainty, severe data contradiction, or TIE."
        }
    },
    "required": [
        "bull_arguments_score", "bear_arguments_score", "winner",
        "dxy_bias", "risk_asset_bias", "rationale", "escalation_required"
    ]
}


async def run_macro_judge(bull_thesis: dict | str, bear_thesis: dict | str, context: str, settings: dict) -> dict:
    """
    Executes Chief Macro Judge to evaluate Risk-On/Dollar-Bear vs Risk-Off/Dollar-Bull debate.
    """
    try:
        client = get_client_for_task("debate_judge", settings)
    except Exception:
        client = get_client_for_task("stage1_fundamental", settings)

    bull_str = json.dumps(bull_thesis, indent=2) if isinstance(bull_thesis, dict) else str(bull_thesis)
    bear_str = json.dumps(bear_thesis, indent=2) if isinstance(bear_thesis, dict) else str(bear_thesis)

    system_prompt = (
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
        "3. If both analysts rely primarily on speculation and HTF data is flat, declare 'TIE' and set escalation_required=True.\n"
    )

    prompt = f"""Adjudicate the macro debate based strictly on the empirical data context and analyst arguments.

DATA CONTEXT:
{context}

BULL ANALYST (Risk-On / Dollar-Bear):
{bull_str}

BEAR ANALYST (Risk-Off / Dollar-Bull):
{bear_str}

Evaluate the merits, assign scores (1-10), declare the winner ('RISK_ON_USD_BEAR', 'RISK_OFF_USD_BULL', or 'TIE'), set dxy_bias and risk_asset_bias according to the mapping rules, and set escalation_required to true if score difference <= 1 or arguments are closely contested."""

    try:
        res = await client.classify_json(prompt=prompt, schema=JUDGE_SCHEMA, system_prompt=system_prompt)
        if not res or not isinstance(res, dict):
            raise ValueError("classify_json returned empty/None result")
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
            "escalation_required": True
        }
