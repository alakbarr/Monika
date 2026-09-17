import logging
import json
from analysis.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.MacroBull")

MACRO_BULL_SCHEMA = {
    "type": "object",
    "properties": {
        "bull_thesis": {
            "type": "string",
            "description": "Concise, evidence-based thesis (max 2 focused paragraphs) advocating Risk-On / Bearish USD macro conditions."
        },
        "strength_score": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Conviction score for Risk-On / Bearish USD thesis based strictly on empirical data."
        },
        "evidence_cited": {
            "type": "array",
            "minItems": 2,
            "items": {"type": "string"},
            "description": "MANDATORY: Minimum 2 exact numerical/macro data points from context (e.g. '10Y Yield=4.05%', 'FedWatch=78% cut', 'VIX=14.2', 'DXY=weakening')."
        },
        "primary_catalysts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of 2-3 key catalysts driving risk-on sentiment and USD softening."
        }
    },
    "required": ["bull_thesis", "strength_score", "evidence_cited", "primary_catalysts"]
}


async def run_bull_analyst(context: str, settings: dict) -> dict:
    """
    Executes Macro Bull Analyst advocating Risk-On / Bearish USD thesis.
    """
    try:
        client = get_client_for_task("debate_bull", settings)
    except Exception:
        client = get_client_for_task("stage1_fundamental", settings)

    from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
    anchor = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()
    system_prompt = (
        f"{anchor}\n\n---\n\n"
        "You are the Macro Risk-On / Dollar-Bear Analyst.\n"
        "Your role is to build the strongest evidence-based macro thesis advocating RISK-ON market conditions and a WEAKER US DOLLAR (bearish DXY).\n"
        "Core thesis pillars: Easing financial conditions, dovish central bank expectations, resilient global growth, disinflation, and expanding liquidity favoring risk-assets (equities, crypto, pro-cyclical currencies, commodities).\n\n"
        "MANDATORY CENTRAL BANK DIVERGENCE & 2Y YIELD ANALYSIS:\n"
        "- Evaluate relative policy divergence: Are foreign central banks (ECB, BoE, RBA) tightening or holding rates while Fed eases? Narrowing US-DE, US-UK, US-AU 2Y short-end spreads directly support the Dollar-Bear thesis.\n"
        "- Check BoJ normalization: Does Japanese rate hike momentum threaten carry trade funding, supporting pro-cyclical or Yen strength?\n\n"
        "STRENGTH SCORE ANCHORS (mandatory reference):\n"
        "- 9-10: Dominant risk-on alignment (falling yields, high rate cut probabilities, low VIX < 16, weakening DXY, broad risk asset momentum).\n"
        "- 6-8: Solid risk-on bias supported by macro data, with 1-2 minor caveats (e.g. sticky core inflation component or mixed COT).\n"
        "- 3-5: Weak risk-on case; macro indicators are mixed or largely support USD strength.\n"
        "- 1-2: Risk-on thesis invalid; aggressive hawkish regime, soaring yields, high VIX > 25, dominant dollar rally."
    )

    prompt = f"""Rigorously evaluate the provided macro data to build the strongest Risk-On / Dollar-Bear thesis.
Directly cite concrete numerical data points rather than making generic claims.

DATA CONTEXT:
{context}

Provide your structured evaluation in JSON matching the schema."""

    try:
        res = await client.classify_json(prompt=prompt, schema=MACRO_BULL_SCHEMA, system_prompt=system_prompt, max_tokens=4096)
        if res and isinstance(res, dict) and "bull_thesis" in res:
            return res
    except Exception as e:
        logger.warning(f"Macro Bull classify_json failed, attempting fallback generation: {e}")

    try:
        raw = await client.generate(prompt=prompt, system=system_prompt)
        return {
            "bull_thesis": raw or "No bullish thesis generated.",
            "strength_score": 5,
            "evidence_cited": ["Context data analyzed via fallback"],
            "primary_catalysts": ["Fallback macro evaluation"]
        }
    except Exception as e:
        logger.error(f"Macro Bull analyst failed completely: {e}")
        return {
            "bull_thesis": f"Error generating bull thesis: {e}",
            "strength_score": 1,
            "evidence_cited": [],
            "primary_catalysts": []
        }
