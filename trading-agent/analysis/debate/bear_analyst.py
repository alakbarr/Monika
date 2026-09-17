import logging
import json
from typing import Dict, Any, Union
from analysis.providers.base_provider import BaseLLMClient

logger = logging.getLogger("TradingAgent.BearAnalyst")

async def generate_bear_dissent(client: BaseLLMClient, symbol: str, original_context: dict, bull_claim: dict, fact_sheet: Union[str, Dict[str, Any]]) -> dict:
    decision = str(original_context.get("decision", "buy")).lower()
    is_long = decision in ("buy", "long")
    
    if is_long:
        role_desc = (
            "You are the Bearish Analyst for the target asset specified in the user message.\n"
            "A BUY (Long) trade has been proposed. Your job is to aggressively challenge the long thesis and 'original_context'.\n"
            "Scrutinize the entry price, SL, and TP. Identify why the Long SL is vulnerable to downside sweeps, "
            "overhead resistance levels that could block the upward TP, and any ignored bearish catalysts in the Fact Sheet.\n"
            "MANDATORY: Inspect and leverage the 'order_flow' data in the Fact Sheet. Look for bearish CVD divergence "
            "(distribution/selling into highs) and negative book imbalance (heavy ask walls) indicating institutional liquidation."
        )
        score_desc = (
            "RISK SEVERITY ANCHORS (mandatory reference):\n"
            "- 9-10: Fatal flaw! Long SL placed in liquidity grab zone, heavy overhead resistance, or thesis opposes dominant macro/DXY trends.\n"
            "- 6-8: Significant downside risk. Poor R:R or setup trades against elevated VIX / imminent high-impact news event.\n"
            "- 3-5: Standard risk. Minor resistance levels exist en route to TP, but overall bullish trend structure supports the setup.\n"
            "- 1-2: Negligible downside risk. Bullish thesis is clean with strong multi-timeframe confirmation and no obvious resistance."
        )
    else:
        role_desc = (
            "You are the Bearish Analyst for the target asset specified in the user message.\n"
            "Your job is to defend the proposed SELL (Short) entry and take profit levels.\n"
            "Focus on identifying downside breakdown catalysts, strong overhead resistance protecting the SL above, "
            "and why the lower TP is conservative or achievable in the current bearish market structure.\n"
            "MANDATORY: Inspect and leverage the 'order_flow' data in the Fact Sheet. Cite aggressive delta selling "
            "(CVD divergence = BEARISH) and negative book imbalance (bid exhaustion / heavy ask presence) as primary structural proof."
        )
        score_desc = (
            "SHORT THESIS STRENGTH ANCHORS (mandatory reference):\n"
            "- 9-10: Multiple independent bearish confluences align (structure + macro + positioning), SL protected by overhead resistance, no meaningful upside counter-evidence in Fact Sheet.\n"
            "- 6-8: Solid bearish setup with macro support, but contains 1 minor caveat (e.g. approaching minor support).\n"
            "- 3-5: Short setup has merit but material bullish counter-evidence exists.\n"
            "- 1-2: Bearish thesis is completely broken; all indicators, macro, and structure are strongly bullish."
        )

    system_prompt = f"""{role_desc}
Rely heavily on the 'original_context' (entry, SL, TP, invalidation), the Bull's argument, and the Fact Sheet provided in the user message.

{score_desc}

[TELEGRAPHIC MANDATE]: Think strictly in dense analytical bullet points. Output valid JSON strictly conforming to the schema. bear_dissent must be concise (max 2 sentences) and grounded with exact numbers from Fact Sheet. Zero conversational filler.
Respond in valid JSON format ONLY conforming to the schema."""
    
    schema = {
        "type": "object",
        "properties": {
            "bear_dissent": {"type": "string"},
            "risk_severity": {"type": "integer", "minimum": 1, "maximum": 10},
            "evidence_cited": {
                "type": "array",
                "minItems": 2,
                "items": {"type": "string"},
                "description": "MANDATORY: List of exact numerical data points from the Fact Sheet that support your thesis. Example: ['ATR_14(H4)=2.45', 'DXY_trend=strengthening +0.4%', 'VIX=28.5', 'CVD_divergence=BEARISH', 'Book_imbalance=-0.45']. Minimum 2 items."
            }
        },
        "required": ["bear_dissent", "risk_severity", "evidence_cited"]
    }

    context_payload = {
        "original_context": original_context,
        "bull_claim": bull_claim,
        "fact_sheet": fact_sheet
    }
    context_str = json.dumps(context_payload, separators=(',', ':'), default=str)
    
    temp = getattr(client, 'default_temperature', 0.2)
    last_err = None
    for attempt in range(2):
        try:
            base_user_msg = f"[TARGET ASSET]: {symbol} | [DIRECTION]: {decision.upper()}\nTrade Setup, Bull Claim & Market Fact Sheet:\n{context_str}\n\nGenerate bear analysis based strictly on the data above."
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
            logger.warning(f"Bear Analyst parse attempt {attempt+1}/2 failed: {e}")

    logger.error(f"Failed to parse Bear Analyst JSON after 2 attempts: {last_err}")
    return {
        "bear_dissent": f"Failed to generate dissent due to parse error: {last_err}",
        "risk_severity": 5,
        "evidence_cited": ["Context data evaluated via fallback"],
        "parse_error": True
    }
