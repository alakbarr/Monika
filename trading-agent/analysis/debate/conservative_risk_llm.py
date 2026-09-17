import logging
import json
from analysis.providers.base_provider import BaseLLMClient, extract_and_parse_json

logger = logging.getLogger("TradingAgent.ConservativeRisk")

RISK_SCHEMA = {'type': 'object', 'properties': {'risk_profile_assessment': {'type': 'string'}, 'recommended_multiplier': {'type': 'number'}, 'veto_trade': {'type': 'boolean', 'description': 'Set to true ONLY if a specific rule below is triggered'}}, 'required': ['risk_profile_assessment', 'recommended_multiplier', 'veto_trade']}

async def analyze_risk_conservative_llm(client: BaseLLMClient, symbol: str, strict_context: dict) -> dict:
    sys_prompt = """You are the CONSERVATIVE Risk Manager. Your mandate: protect capital above all else.
APPLY THESE RULES IN ORDER — cite the SPECIFIC rule number you triggered (or state 'no rule triggered'):
1. If actual_risk_state.daily_pnl_pct <= -1.5%: veto_trade=true.
2. If actual_risk_state.open_positions >= 3: veto_trade=true (over-concentration).
3. If actual_risk_state.portfolio_heat_pct > 3.0%: recommended_multiplier <= 0.5.
4. Otherwise: recommended_multiplier in range 0.3-1.0, biased LOW unless confluence_score >= 10/14.
Return JSON with 'risk_profile_assessment' (must cite the rule number applied), 'recommended_multiplier', 'veto_trade'."""
    user_msg = f'Symbol: {symbol}\nContext: {json.dumps(strict_context)}'
    try:
        resp = await client.generate_content(system_prompt=sys_prompt, user_message=user_msg, response_schema=RISK_SCHEMA)
        if not resp:
            raise ValueError("Empty response from LLM")
        data = extract_and_parse_json(resp) if isinstance(resp, str) else (resp if isinstance(resp, dict) else None)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid JSON response format: {resp}")
        if 'veto_trade' not in data:
            data['veto_trade'] = False
        mult = data.get('recommended_multiplier')
        if mult is not None and not data.get('veto_trade') and (not 0.3 <= float(mult) <= 1.0):
            logger.warning(f"[RiskDebate][Conservative][{symbol}] LLM recommended_multiplier={mult} di luar rentang aritmetika terdokumentasi [0.3, 1.0]. Diteruskan (akan di-clamp oleh _apply_deterministic_risk_clamp), tapi mengindikasikan model salah menghitung formula preskriptif.")
        return data
    except Exception as e:
        logger.error(f'Conservative risk parse error: {e}')
        return {'risk_profile_assessment': 'Fallback error', 'recommended_multiplier': 0.5, 'veto_trade': False}

