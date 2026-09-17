import logging
import json
from analysis.providers.base_provider import BaseLLMClient, extract_and_parse_json

logger = logging.getLogger("TradingAgent.NeutralRisk")

RISK_SCHEMA = {'type': 'object', 'properties': {'risk_profile_assessment': {'type': 'string'}, 'recommended_multiplier': {'type': 'number'}, 'veto_trade': {'type': 'boolean', 'description': 'Set to true ONLY if a specific rule below is triggered'}}, 'required': ['risk_profile_assessment', 'recommended_multiplier', 'veto_trade']}

async def analyze_risk_neutral_llm(client: BaseLLMClient, symbol: str, strict_context: dict) -> dict:
    sys_prompt = """You are the NEUTRAL Risk Manager, balancing edge-capture against capital
preservation using explicit arithmetic.
RULES:
1. veto_trade=true if: (portfolio_heat_pct > 4.0% AND confluence_score < 9) OR (daily_pnl_pct <= -2.0%) OR (R:R < min_rr_ratio).
2. recommended_multiplier = 1.0, minus 0.15 per open_position beyond the first, minus 0.2 if daily_pnl_pct < -1.0%, clipped to [0.4, 1.5].
Return JSON with 'risk_profile_assessment' (show the multiplier arithmetic explicitly), 'recommended_multiplier', 'veto_trade'."""
    user_msg = f'Symbol: {symbol}\nContext: {json.dumps(strict_context)}'
    try:
        resp = await client.generate_content(system_prompt=sys_prompt, user_message=user_msg, temperature=0.1, response_schema=RISK_SCHEMA)
        if not resp:
            raise ValueError("Empty response from LLM")
        data = extract_and_parse_json(resp) if isinstance(resp, str) else (resp if isinstance(resp, dict) else None)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid JSON response format: {resp}")
        if 'veto_trade' not in data:
            data['veto_trade'] = False
        mult = data.get('recommended_multiplier')
        if mult is not None and not data.get('veto_trade') and (not 0.4 <= float(mult) <= 1.5):
            logger.warning(f"[RiskDebate][Neutral][{symbol}] LLM recommended_multiplier={mult} di luar rentang aritmetika terdokumentasi [0.4, 1.5]. Diteruskan (akan di-clamp), tapi mengindikasikan model salah menghitung formula preskriptif.")
        return data
    except Exception as e:
        logger.error(f'Neutral risk parse error: {e}')
        return {'risk_profile_assessment': 'Fallback error', 'recommended_multiplier': 1.0, 'veto_trade': False}

