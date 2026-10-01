import logging
import json
from analysis.providers.base_provider import BaseLLMClient, extract_and_parse_json

logger = logging.getLogger("TradingAgent.ConservativeRisk")

RISK_SCHEMA = {'type': 'object', 'properties': {'risk_profile_assessment': {'type': 'string'}, 'recommended_multiplier': {'type': 'number'}, 'veto_trade': {'type': 'boolean', 'description': 'Set to true ONLY if a specific rule below is triggered'}}, 'required': ['risk_profile_assessment', 'recommended_multiplier', 'veto_trade']}

async def analyze_risk_conservative_llm(client: BaseLLMClient, symbol: str, strict_context: dict) -> dict:
    sys_prompt = """You are the CONSERVATIVE Risk Manager. Your mandate: protect capital above all else and defend against catastrophic tail risk.
EVALUATION MANDATES (apply and cite specifically):
1. VETO CONDITIONS: Set veto_trade=true if:
   - Daily drawdown is active (actual_risk_state.daily_pnl_pct <= -1.5%).
   - Portfolio concentration is high (open_positions >= 3).
   - Severe tail risk present: impending Tier-1 economic event (CPI/NFP/FOMC within rollover window), high VIX volatility spike, or unmitigated cross-asset contagion.
2. SIZING CONSTRAINTS:
   - If portfolio_heat_pct > 3.0%: recommended_multiplier <= 0.5.
   - Baseline sizing is heavily defensive (0.3 to 0.7), only allowing up to 1.0 if confluence_score >= 10/14 and macro alignment is impeccable.
Return JSON with 'risk_profile_assessment' (cite rule/threat evaluated: tail risk, rollover freeze, or concentration), 'recommended_multiplier', 'veto_trade'."""
    user_msg = f'Symbol: {symbol}\nContext: {json.dumps(strict_context)}'
    try:
        from utils.typesafe.jev_primitives import build_risk_gate_conservative_questions
        direction = strict_context.get("direction") or strict_context.get("decision", "buy")
        jev_q = build_risk_gate_conservative_questions(symbol, direction=direction)

        resp = await client.generate_content(
            system_prompt=sys_prompt,
            user_message=user_msg,
            response_schema=RISK_SCHEMA,
            jev_questions=jev_q
        )
        if not resp:
            raise ValueError("Empty response from LLM")
        data = extract_and_parse_json(resp) if isinstance(resp, str) else (resp if isinstance(resp, dict) else None)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid JSON response format: {resp}")

        # If evaluated via Jev System One, map typed fields to expected schema
        if "risk_level" in data or "_jev_model" in data or "recommended_multiplier_bucket" in data:
            veto = bool(data.get("veto_trade", False))
            bucket = str(data.get("recommended_multiplier_bucket", "STANDARD")).upper()
            risk_level = str(data.get("risk_level", "LOW")).upper()
            if risk_level == "CRITICAL":
                veto = True

            if veto:
                mult = 0.0
            elif bucket == "MINIMAL":
                mult = 0.4
            elif bucket == "STANDARD":
                mult = 0.7
            elif bucket == "NORMAL":
                mult = 1.0
            else:
                mult = 0.5

            data["veto_trade"] = veto
            data["recommended_multiplier"] = mult
            if not data.get("risk_profile_assessment") or data.get("risk_profile_assessment") in ("YES", "NO"):
                data["risk_profile_assessment"] = (
                    f"Jev Conservative Evaluation: veto={veto}, risk_level={risk_level}, mult={mult}"
                )

        if 'veto_trade' not in data:
            data['veto_trade'] = False
        mult = data.get('recommended_multiplier')
        if mult is not None and not data.get('veto_trade') and (not 0.3 <= float(mult) <= 1.0):
            logger.warning(f"[RiskDebate][Conservative][{symbol}] LLM recommended_multiplier={mult} di luar rentang aritmetika terdokumentasi [0.3, 1.0]. Diteruskan (akan di-clamp oleh _apply_deterministic_risk_clamp), tapi mengindikasikan model salah menghitung formula preskriptif.")
        return data
    except Exception as e:
        logger.error(f"Risk LLM failed: {e}")
        return {
            "veto_trade": True,
            "recommended_multiplier": 0.0,
            "reasoning": f"Fail-closed: {e}",
            "risk_profile_assessment": f"Fail-closed: {e}",
            "parse_error": True,
        }

