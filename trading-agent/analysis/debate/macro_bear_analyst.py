import logging
import json
from analysis.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.MacroBear")

MACRO_BEAR_SCHEMA = {
    "type": "object",
    "properties": {
        "bear_thesis": {
            "type": "string",
            "description": "Concise, evidence-based thesis (max 2 focused paragraphs) advocating Risk-Off / Bullish USD macro conditions."
        },
        "strength_score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Conviction score for Risk-Off / Bullish USD thesis based strictly on empirical data."
        },
        "evidence_cited": {
            "type": "array",
            "minItems": 2,
            "items": {"type": "string"},
            "description": "MANDATORY: Minimum 2 exact numerical/macro data points from context (e.g. '10Y Yield=4.45%', 'Sticky Core CPI', 'VIX=24.5', 'DXY=strengthening')."
        },
        "primary_risks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of 2-3 key risk-off triggers or dollar strength catalysts."
        }
    },
    "required": ["bear_thesis", "strength_score", "evidence_cited", "primary_risks"]
}


async def run_bear_analyst(context: str, settings: dict) -> dict:
    """
    Executes Macro Bear Analyst advocating Risk-Off / Bullish USD thesis.
    """
    try:
        client = get_client_for_task("debate_bear", settings)
    except Exception:
        client = get_client_for_task("stage1_fundamental", settings)

    from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
    anchor = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()
    system_prompt = (
        f"{anchor}\n\n---\n\n"
        "You are the Macro Risk-Off / Dollar-Bull Analyst.\n"
        "Your role is to build the strongest evidence-based macro thesis advocating RISK-OFF market conditions and a STRONGER US DOLLAR (bullish DXY).\n"
        "Core thesis pillars: Persistent inflation, hawkish central bank posture, liquidity contraction, geopolitical/growth headwinds, and safe-haven flows pressuring risk-assets (equities, crypto, pro-cyclical currencies, commodities).\n\n"
        "MANDATORY CENTRAL BANK DIVERGENCE & 2Y YIELD ANALYSIS:\n"
        "- Evaluate relative policy divergence: Is the Fed remaining higher-for-longer while foreign central banks (ECB, BoE, RBA) cut or face growth slowdowns? Widening US-DE, US-UK, US-AU 2Y short-end spreads directly support the Dollar-Bull thesis.\n"
        "- Check carry trade dynamics: Does wide US-JP yield differential sustain institutional capital inflows into USD assets?\n\n"
        "STRENGTH SCORE ANCHORS (mandatory reference):\n"
        "- 9-10: Dominant risk-off alignment (rising/elevated yields, hawkish repricing, high VIX > 22, strengthening DXY, safe-haven dollar demand).\n"
        "- 6-8: Solid risk-off / dollar-bull bias with 1-2 minor caveats (e.g. softening labor data but sticky services inflation).\n"
        "- 3-5: Weak risk-off case; data indicates robust liquidity and disinflation trend.\n"
        "- 1-2: Risk-off thesis invalid; clear monetary easing, collapsing dollar, risk-on euphoria across markets."
    )

    prompt = f"""Rigorously evaluate the provided macro data to build the strongest Risk-Off / Dollar-Bull thesis.
Directly cite concrete numerical data points rather than making generic claims.

DATA CONTEXT:
{context}

Provide your structured evaluation in JSON matching the schema."""

    try:
        res = await client.classify_json(prompt=prompt, schema=MACRO_BEAR_SCHEMA, system_prompt=system_prompt, max_tokens=4096)
        if res and isinstance(res, dict) and "bear_thesis" in res:
            return res
    except Exception as e:
        logger.warning(f"Macro Bear classify_json failed, attempting fallback generation: {e}")

    try:
        raw = await client.generate(prompt=prompt, system=system_prompt)
        return {
            "bear_thesis": raw or "No bearish thesis generated.",
            "strength_score": 5,
            "evidence_cited": ["Context data analyzed via fallback"],
            "primary_risks": ["Fallback macro evaluation"]
        }
    except Exception as e:
        logger.error(f"Macro Bear analyst failed completely: {e}")
        return {
            "bear_thesis": f"Error generating bear thesis: {e}",
            "strength_score": 1,
            "evidence_cited": [],
            "primary_risks": []
        }
