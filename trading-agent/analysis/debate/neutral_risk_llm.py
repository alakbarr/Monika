import logging
import json
from analysis.providers.base_provider import BaseLLMClient, extract_and_parse_json

logger = logging.getLogger("TradingAgent.NeutralRisk")

RISK_SCHEMA = {'type': 'object', 'properties': {'risk_profile_assessment': {'type': 'string'}, 'recommended_multiplier': {'type': 'number'}, 'veto_trade': {'type': 'boolean', 'description': 'Set to true ONLY if a specific rule below is triggered'}}, 'required': ['risk_profile_assessment', 'recommended_multiplier', 'veto_trade']}

async def analyze_risk_neutral_llm(client: BaseLLMClient, symbol: str, strict_context: dict) -> dict:
    min_rr = float(strict_context.get("min_rr_ratio", 1.3) or 1.3)
    sys_prompt = f"""You are the NEUTRAL Risk Manager. Your role is balanced governance: capturing genuine edge while strictly enforcing capital preservation principles.
EVALUATION MANDATES:
1. VETO CONDITIONS: Set veto_trade=true if:
   - Portfolio heat is elevated (> 4.0%) with weak confluence (< 9/14).
   - Daily drawdown is severe (daily_pnl_pct <= -2.0%).
   - Risk:Reward is substandard (R:R < {min_rr} or ungrounded).
2. RISK MULTIPLIER GUIDANCE:
   - Baseline multiplier is 1.0 for clean setups with disciplined confluence (>=9).
   - Step down sizing (0.5 - 0.8) if open exposure is high, drawdown is building (daily_pnl < -1.0%), or liquidity conditions are mixed.
   - Recommend a multiplier in [0.4, 1.5]. (Exact numeric clamping is handled deterministically by the system).
Return JSON with 'risk_profile_assessment' (terse qualitative breakdown of heat, exposure, and structural edge), 'recommended_multiplier', 'veto_trade'."""
    user_msg = f'Symbol: {symbol}\nContext: {json.dumps(strict_context)}'
    try:
        from utils.typesafe.jev_primitives import build_risk_gate_neutral_questions
        direction = strict_context.get("direction") or strict_context.get("decision", "buy")
        jev_q = build_risk_gate_neutral_questions(symbol, direction=direction)

        resp = await client.generate_content(
            system_prompt=sys_prompt,
            user_message=user_msg,
            temperature=0.1,
            response_schema=RISK_SCHEMA,
            jev_questions=jev_q
        )
        if not resp:
            raise ValueError("Empty response from LLM")
        data = extract_and_parse_json(resp) if isinstance(resp, str) else (resp if isinstance(resp, dict) else None)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid JSON response format: {resp}")

        # If evaluated via Jev System One, map typed fields to expected schema
        if "overall_approval" in data or "_jev_model" in data:
            approval = data.get("overall_approval", "approve")
            timing_ok = data.get("timing_acceptable", True)
            sizing_ok = data.get("position_sizing_appropriate", True)
            rr_score = data.get("risk_reward_balance", 1)

            veto = (approval == "reject") or (timing_ok is False) or (rr_score is not None and rr_score >= 3)
            if approval == "approve":
                mult = 1.0 if sizing_ok else 0.85
            elif approval == "approve_with_reduced_size":
                mult = 0.70
            elif approval == "defer":
                mult = 0.50
            else:
                mult = 0.40

            data["veto_trade"] = veto
            data["recommended_multiplier"] = mult
            if not data.get("risk_profile_assessment") or data.get("risk_profile_assessment") in ("YES", "NO"):
                data["risk_profile_assessment"] = (
                    f"Jev Neutral Evaluation: verdict={approval}, rr_score={rr_score}, "
                    f"timing_ok={timing_ok}, sizing_ok={sizing_ok}, multiplier={mult}"
                )

        if 'veto_trade' not in data:
            data['veto_trade'] = False
        mult = data.get('recommended_multiplier')
        if mult is not None and not data.get('veto_trade') and (not 0.4 <= float(mult) <= 1.5):
            logger.warning(f"[RiskDebate][Neutral][{symbol}] LLM recommended_multiplier={mult} di luar rentang aritmetika terdokumentasi [0.4, 1.5]. Diteruskan (akan di-clamp), tapi mengindikasikan model salah menghitung formula preskriptif.")
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

