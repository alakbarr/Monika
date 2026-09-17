import logging
import json
from analysis.providers.base_provider import BaseLLMClient, extract_and_parse_json

logger = logging.getLogger("TradingAgent.AggressiveRisk")

RISK_SCHEMA = {'type': 'object', 'properties': {'risk_profile_assessment': {'type': 'string'}, 'recommended_multiplier': {'type': 'number'}, 'veto_trade': {'type': 'boolean', 'description': 'Set to true ONLY if a specific rule below is triggered'}}, 'required': ['risk_profile_assessment', 'recommended_multiplier', 'veto_trade']}

async def analyze_risk_aggressive_llm(client: BaseLLMClient, symbol: str, strict_context: dict) -> dict:
    sys_prompt = """You are the AGGRESSIVE Risk Manager. Your mandate: maximize capture of genuine
edge; only intervene for STRUCTURAL flaws, never for routine caution (that is
the Conservative persona's job — do not duplicate their logic).
APPLY THESE RULES:
1. veto_trade=true ONLY if: R:R < 1.5, OR stop_loss is not beyond a structural level, OR confluence_score < 5.
2. Do NOT veto solely because of daily_pnl_pct or open_positions count.
3. recommended_multiplier: 1.0-2.0 if confluence_score >= 9, else 0.75-1.25.
Return JSON with 'risk_profile_assessment' (cite the specific rule if triggered), 'recommended_multiplier', 'veto_trade'."""
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
        if mult is not None and not data.get('veto_trade') and (not 0.75 <= float(mult) <= 2.0):
            logger.warning(f"[RiskDebate][Aggressive][{symbol}] LLM recommended_multiplier={mult} di luar rentang aritmetika terdokumentasi [0.75, 2.0]. Diteruskan (akan di-clamp), tapi mengindikasikan model salah menghitung formula preskriptif.")
        return data
    except Exception as e:
        logger.error(f'Aggressive risk parse error: {e}')
        return {'risk_profile_assessment': 'Fallback error', 'recommended_multiplier': 1.0, 'veto_trade': False}

