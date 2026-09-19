import logging
import json
from typing import Dict, Any, Union
from analysis.providers.base_provider import BaseLLMClient
from utils.llm.prompt_disciplines import get_universal_execution_discipline
from analysis.harness.repetition_guard import detect_text_repetition

logger = logging.getLogger("TradingAgent.BullAnalyst")

async def generate_bull_advocacy(client: BaseLLMClient, symbol: str, original_context: dict, fact_sheet: Union[str, Dict[str, Any]]) -> dict:
    decision = str(original_context.get("decision", "buy")).lower()
    is_long = decision in ("buy", "long")
    
    if is_long:
        role_desc = (
            "You are the Bullish Analyst for the target asset specified in the user message.\n"
            "Your job is to defend the proposed BUY (Long) entry and take profit levels.\n"
            "Focus on identifying upside catalysts, strong technical support protecting the SL below, "
            "and why the upward TP is conservative or achievable.\n"
            "MANDATORY: Inspect and leverage the 'order_flow' data in the Fact Sheet. Cite CVD divergence "
            "(e.g. BULLISH accumulation/absorption) and order book imbalance (positive bid dominance) as critical microstructural confirmation."
        )
        score_desc = (
            "STRENGTH SCORE ANCHORS (mandatory reference):\n"
            "- 9-10: Multiple independent bullish confluences align (structure + macro + positioning), "
            "SL is well protected by support, no meaningful counter-evidence in the Fact Sheet.\n"
            "- 6-8: Solid bullish setup with macro support, but contains 1 minor caveat (e.g. approaching minor resistance).\n"
            "- 3-5: Bullish setup has merit but material counter-evidence exists that the Bear Analyst is likely to exploit.\n"
            "- 1-2: Bullish thesis is completely broken; all indicators, macro, and structure are strongly bearish."
        )
    else:
        role_desc = (
            "You are the Bullish Analyst for the target asset specified in the user message.\n"
            "A SELL (Short) trade has been proposed. Your job is to challenge this short setup from a bullish perspective.\n"
            "Identify why the market could reverse or bounce upward, why support underfoot threatens the short TP, "
            "and what upside catalysts or bullish market structures threaten the short SL above.\n"
            "MANDATORY: Inspect and leverage the 'order_flow' data in the Fact Sheet. Cite any bullish CVD divergence "
            "or positive book imbalance (bid stacking/absorption) threatening the short breakdown."
        )
        score_desc = (
            "BULLISH COUNTER-THESIS STRENGTH ANCHORS (mandatory reference):\n"
            "- 9-10: High bullish threat! Major unmitigated demand zone/support immediately below entry, strong bullish divergence or upside macro catalyst.\n"
            "- 6-8: Moderate bullish threat. Solid support zone exists that may stall or bounce price before short TP.\n"
            "- 3-5: Low bullish threat. Bearish market structure dominates; bullish counter-arguments are weak or minor.\n"
            "- 1-2: Negligible bullish threat. Clear bearish dominance with no credible upward reversal drivers."
        )

    system_prompt = f"""{role_desc}
Rely heavily on the 'original_context' (entry, SL, TP, invalidation) and the Fact Sheet provided in the user message.

{score_desc}

{get_universal_execution_discipline()}

[TELEGRAPHIC MANDATE]: Think strictly in dense analytical bullet points. Output valid JSON strictly conforming to the schema. bull_thesis must be concise (max 2 sentences) and grounded with exact numbers from Fact Sheet. Zero conversational filler.
Respond in valid JSON format ONLY conforming to the schema."""
    
    schema = {
        "type": "object",
        "properties": {
            "bull_thesis": {"type": "string"},
            "strength_score": {"type": "integer", "minimum": 1, "maximum": 10},
            "evidence_cited": {
                "type": "array",
                "minItems": 2,
                "items": {"type": "string"},
                "description": "MANDATORY: List of exact numerical data points from the Fact Sheet that support your thesis. Example: ['ATR_14(H4)=2.45', 'DXY_trend=weakening -0.4%', 'VIX=18.5', 'CVD_divergence=BULLISH', 'Book_imbalance=0.35']. Minimum 2 items."
            }
        },
        "required": ["bull_thesis", "strength_score", "evidence_cited"]
    }

    context_payload = {
        "original_context": original_context,
        "fact_sheet": fact_sheet
    }
    context_str = json.dumps(context_payload, separators=(',', ':'), default=str)
    
    temp = getattr(client, 'default_temperature', 0.2)
    last_err = None
    for attempt in range(2):
        try:
            base_user_msg = f"[TARGET ASSET]: {symbol} | [DIRECTION]: {decision.upper()}\nTrade Setup & Market Fact Sheet:\n{context_str}\n\nGenerate bull analysis based strictly on the setup and Fact Sheet above."
            user_msg = base_user_msg if attempt == 0 else f"{base_user_msg}\n\nYour previous response was not valid JSON ({last_err}). Return ONLY valid JSON matching the schema."
            resp = await client.generate_content(
                system_prompt=system_prompt,
                user_message=user_msg,
                temperature=temp,
                response_schema=schema,
                max_tokens=getattr(client, 'max_tokens', 4096) or 4096
            )
            if not resp:
                raise ValueError("Empty response from LLM")
            return json.loads(resp)
        except Exception as e:
            last_err = e
            logger.warning(f"Bull Analyst parse attempt {attempt+1}/2 failed: {e}")

    logger.error(f"Failed to parse Bull Analyst JSON after 2 attempts: {last_err}")
    return {
        "bull_thesis": f"Fallback to original rationale due to parse error: {last_err}",
        "strength_score": 5,
        "evidence_cited": ["Context data evaluated via fallback"],
        "parse_error": True
    }


async def generate_bull_rebuttal(
    client: BaseLLMClient,
    symbol: str,
    original_context: dict,
    fact_sheet: Union[str, Dict[str, Any]],
    bull_claim: dict,
    bear_dissent: dict
) -> dict:
    decision = str(original_context.get("decision", "buy")).lower()

    role_desc = (
        f"You are the Bullish Analyst for {symbol}.\n"
        f"The Bearish Analyst has issued a counter-argument/dissent (risk_severity={bear_dissent.get('risk_severity', 5)}) challenging the proposed {decision.upper()} setup.\n"
        f"Your task is to provide a grounded, rigorous Round 2 dialectic rebuttal.\n"
        f"Directly confront the specific criticisms in 'bear_dissent'. Cite precise numerical confluences from the Fact Sheet "
        f"(including 'order_flow' CVD divergence and order book imbalance) to demonstrate why the trade remains viable, "
        f"or concede specific structural risks if the Bear's points are insurmountable."
    )
    score_desc = (
        "REBUTTAL STRENGTH ANCHORS (mandatory reference):\n"
        "- 9-10: Complete refutation! Bear's arguments rely on false assumptions or out-of-context data; verified HTF support/catalysts completely nullify the bear threat.\n"
        "- 6-8: Effective mitigation. Bear raises valid risk, but entry/SL buffers or secondary indicators adequately cover the concern.\n"
        "- 3-5: Weak rebuttal. Bear's critique exposes genuine vulnerability; Bull can only offer partial or rhetorical defense.\n"
        "- 1-2: Capitulation. Bear's critique identifies a fatal flaw that cannot be defended."
    )

    system_prompt = f"""{role_desc}
Rely heavily on 'original_context', 'bull_claim', 'bear_dissent', and the Fact Sheet.

{score_desc}

[TELEGRAPHIC MANDATE]: Think strictly in dense analytical bullet points. Output valid JSON strictly conforming to the schema. rebuttal_thesis must be concise (max 2 sentences) and grounded with exact numbers from Fact Sheet. Zero conversational filler.
Respond in valid JSON format ONLY conforming to the schema."""

    schema = {
        "type": "object",
        "properties": {
            "rebuttal_thesis": {"type": "string"},
            "rebuttal_strength": {"type": "integer", "minimum": 1, "maximum": 10},
            "rebuttal_evidence": {
                "type": "array",
                "minItems": 2,
                "items": {"type": "string"},
                "description": "MANDATORY: List of exact numerical data points from the Fact Sheet refuting bear points. Minimum 2 items."
            },
            "conceded_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of valid points conceded to the Bear Analyst, if any."
            }
        },
        "required": ["rebuttal_thesis", "rebuttal_strength", "rebuttal_evidence"]
    }

    payload = {
        "original_context": original_context,
        "bull_claim": bull_claim,
        "bear_dissent": bear_dissent,
        "fact_sheet": fact_sheet
    }
    context_str = json.dumps(payload, separators=(',', ':'), default=str)
    temp = getattr(client, 'default_temperature', 0.2)
    last_err = None
    for attempt in range(2):
        try:
            base_user_msg = (
                f"[TARGET ASSET]: {symbol} | [DIRECTION]: {decision.upper()}\n"
                f"Round 1 Debate & Market Fact Sheet:\n{context_str}\n\n"
                f"Provide Round 2 Bullish Rebuttal confronting the Bear Dissent based strictly on the Fact Sheet."
            )
            user_msg = base_user_msg if attempt == 0 else f"{base_user_msg}\n\nYour previous response was not valid JSON ({last_err}). Return ONLY valid JSON matching the schema."
            resp = await client.generate_content(
                system_prompt=system_prompt,
                user_message=user_msg,
                temperature=temp,
                response_schema=schema,
                max_tokens=getattr(client, 'max_tokens', 4096) or 4096
            )
            if not resp:
                raise ValueError("Empty response from LLM")
            return json.loads(resp)
        except Exception as e:
            last_err = e
            logger.warning(f"Bull Rebuttal parse attempt {attempt+1}/2 failed: {e}")

    logger.error(f"Failed to parse Bull Rebuttal JSON after 2 attempts: {last_err}")
    return {
        "rebuttal_thesis": f"Fallback rebuttal due to parse error: {last_err}",
        "rebuttal_strength": 5,
        "rebuttal_evidence": ["Fact Sheet verified via fallback"],
        "conceded_points": [],
        "parse_error": True
    }

