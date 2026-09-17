import logging
import json
from analysis.providers.base_provider import BaseLLMClient, extract_and_parse_json

logger = logging.getLogger("TradingAgent.PortfolioManager")

async def make_portfolio_decision(client: BaseLLMClient, symbol: str, risk_debate_states: dict, actual_risk_state: dict | None) -> dict:
    sys_prompt = (
        "You are a balanced Portfolio Manager focused on capturing opportunities while managing risk.\n\n"
        "MANDATORY REJECTION CRITERIA (override ALL other reasoning):\n"
        "- If portfolio_heat_pct > 4.0%: approval=false, reason='Portfolio heat exceeds 4% limit'\n"
        "- If daily_drawdown_pct > 3.0%: approval=false, reason='Daily drawdown exceeds 3% limit'\n"
        "- If open_positions >= max_concurrent_positions (default 5): approval=false, reason='Position limit reached'\n"
        "- If daily_sl_count >= 3: approval=false, reason='Daily SL limit reached'\n\n"
        "RISK MULTIPLIER RULES:\n"
        "- Default: 1.0 (full size)\n"
        "- If VIX > 30: max 0.5\n"
        "- If 2+ correlated positions already open in same direction: max 0.5\n"
        "- If symbol has 3+ consecutive SL hits recently: max 0.25\n"
        "- If 2+ risk debate personas voted veto_trade=true: max 0.5\n\n"
        "IMPORTANT: Apply these rules STRICTLY using the numerical data in Portfolio State. "
        "Do NOT override rejection criteria based on subjective reasoning.\n\n"
        "Return JSON: {\"approval\": boolean, \"recommended_risk_multiplier\": float, \"reason\": string}"
    )
    user_msg = f"Symbol: {symbol}\nRisk Debates: {json.dumps(risk_debate_states)}\nPortfolio State: {json.dumps(actual_risk_state)}"
    
    schema = {
        "type": "object",
        "properties": {
            "approval": {"type": "boolean"},
            "recommended_risk_multiplier": {"type": "number"},
            "reason": {"type": "string"}
        },
        "required": ["approval", "recommended_risk_multiplier", "reason"]
    }
    
    try:
        resp = await client.generate_content(system_prompt=sys_prompt, user_message=user_msg, response_schema=schema)
        if not resp:
            raise ValueError("Empty response from LLM")
        data = extract_and_parse_json(resp) if isinstance(resp, str) else (resp if isinstance(resp, dict) else None)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid JSON response format: {resp}")
        if "approval" not in data:
            data["approval"] = True
        if "recommended_risk_multiplier" not in data:
            data["recommended_risk_multiplier"] = 1.0
        if "reason" not in data:
            data["reason"] = "LLM portfolio decision"
        return data
    except Exception as e:
        logger.error(f"Failed to parse Portfolio Manager JSON: {e}")
        # FIX: Fail-open with cautious multiplier (trade passed preceding gates)
        return {"approval": True, "recommended_risk_multiplier": 0.5, "reason": f"Fallback - Parse Error (fail-open, reduced size): {e}", "parse_error": True}

