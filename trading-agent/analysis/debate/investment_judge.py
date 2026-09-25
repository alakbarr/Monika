import logging
import json
from typing import Optional, Dict, Any
from analysis.providers.base_provider import BaseLLMClient
from utils.llm.prompt_disciplines import get_universal_execution_discipline

logger = logging.getLogger("TradingAgent.InvestmentJudge")

REGIME_WEIGHT_MATRIX = {
    "trending": {
        "trend_thesis_weight": 0.65,
        "counter_thesis_weight": 0.35,
        "volatility_penalty": 0.0,
        "description": "Trending market: higher weight on trend momentum, require verified structural failure to veto."
    },
    "ranging": {
        "trend_thesis_weight": 0.50,
        "counter_thesis_weight": 0.50,
        "volatility_penalty": 0.10,
        "description": "Ranging market: balanced weight, mean-reversion favored, tight SL required."
    },
    "volatile": {
        "trend_thesis_weight": 0.30,
        "counter_thesis_weight": 0.70,
        "volatility_penalty": 0.20,
        "description": "High volatility/shock: heavy weight to risk dissent, aggressive size reduction or veto."
    },
    "unknown": {
        "trend_thesis_weight": 0.50,
        "counter_thesis_weight": 0.50,
        "volatility_penalty": 0.0,
        "description": "Neutral baseline regime."
    }
}


def resolve_regime_weights(original_context: dict) -> dict:
    """Determine dynamic calibration weights based on market regime and VIX."""
    raw_regime = str(
        original_context.get("market_regime")
        or original_context.get("regime")
        or original_context.get("volatility_regime")
        or ""
    ).lower()
    
    try:
        vix = float(original_context.get("vix") or 0.0)
    except (ValueError, TypeError):
        vix = 0.0

    if "volatil" in raw_regime or "shock" in raw_regime or vix >= 25.0:
        regime_key = "volatile"
    elif "trend" in raw_regime or "bull" in raw_regime or "bear" in raw_regime:
        regime_key = "trending"
    elif "range" in raw_regime or "chop" in raw_regime or "sideway" in raw_regime:
        regime_key = "ranging"
    else:
        regime_key = "unknown"

    weights = dict(REGIME_WEIGHT_MATRIX[regime_key])
    weights["detected_regime"] = regime_key
    return weights


def _snap_boundary(text: str, max_chars: int = 1000) -> str:
    """Snaps text to the nearest sentence/paragraph boundary within max_chars to save tokens cleanly."""
    if not text or len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    for punct in ["\n\n", "\n", ". ", "; ", ", "]:
        last_idx = truncated.rfind(punct)
        if last_idx > max_chars // 2:
            return truncated[:last_idx + len(punct)].strip() + " [compacted]"
    return truncated.rstrip() + "... [compacted]"


def compress_debate_trajectory(data: Any, max_text_len: int = 800) -> Any:
    """Recursively compresses long narrative fields in debate payload while preserving numeric and key thesis fields."""
    if isinstance(data, dict):
        compressed = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > max_text_len:
                compressed[k] = _snap_boundary(v, max_chars=max_text_len)
            elif isinstance(v, (dict, list)):
                compressed[k] = compress_debate_trajectory(v, max_text_len=max_text_len)
            else:
                compressed[k] = v
        return compressed
    elif isinstance(data, list):
        return [compress_debate_trajectory(item, max_text_len=max_text_len) for item in data]
    return data


async def evaluate_debate(
    client: BaseLLMClient,
    symbol: str,
    original_context: dict,
    bull_claim: dict,
    bear_dissent: dict,
    bull_rebuttal: Optional[dict] = None
) -> dict:
    from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
    anchor = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR.strip()
    decision = str(original_context.get("decision", "buy")).upper()
    regime_weights = resolve_regime_weights(original_context)
    detected_regime = regime_weights["detected_regime"]

    system_prompt = f"""{anchor}

---

You are the Chief Investment Officer (Judge).
You must evaluate the proposed trade setup in 'original_context', alongside the Bull Analyst's analysis, the Bear Analyst's analysis, and any Round 2 Rebuttal (Bull or Bear) provided in the user prompt.
Determine if the trade should proceed at full size, needs size adjustment, level adjustment, or REJECTION.
Your role is to critically evaluate trade viability and protect capital.

MARKET REGIME CALIBRATION CONTEXT:
- Detected Regime: {detected_regime.upper()}
- Thesis Weight (Trend): {regime_weights['trend_thesis_weight']:.2f}
- Counter Thesis Weight: {regime_weights['counter_thesis_weight']:.2f}
- Volatility Penalty: {regime_weights['volatility_penalty']:.2f}
- Guidance: {regime_weights['description']}

DIRECTIONAL ADJUDICATION RULES:
If original_context decision is SELL:
- Pro-Thesis Advocate: Bear Analyst defending the short entry and breakdown catalysts (higher score = stronger short setup).
- Counter-Thesis Dissenter: Bull Analyst challenging the short setup with upside reversal threats (higher score = dangerous upside threat).
- If the Bull Analyst proves a FATAL FLAW to the short (bull strength_score >= 9) and short defense fails to refute it, you MUST REJECT (final_decision = 'avoid', risk_multiplier = 0.0).
- If Bear proves strong short conviction (score >= 8) with low bull threat (<= 3), approve short trade at full size (risk_multiplier 0.75 - 1.0).
If original_context decision is BUY:
- Pro-Thesis Advocate: Bull Analyst defending the long entry and upside catalysts.
- Counter-Thesis Dissenter: Bear Analyst challenging the long setup with downside risks (higher score = dangerous downside threat).
- If the Bear Analyst proves a FATAL FLAW to the long (bear risk_severity >= 9) and Bull Rebuttal fails to refute it, you MUST REJECT (final_decision = 'avoid', risk_multiplier = 0.0).
- If bear threat is 7-8 and Bull presents strong defense (strength >= 7), do NOT reject; proceed with calibrated risk multiplier (0.50 to 0.75).
In volatile regimes, high counter-thesis threat (>= 8) requires severe size reduction or rejection.
Otherwise, calibrate risk and evaluate the viability of the Entry, SL, and TP.

RISK MULTIPLIER CALIBRATION TABLE (mandatory reference — pick the closest match):
- 1.0  = Counter-arguments have no material weakness in the trade thesis; proceed at full size.
- 0.75 = Counter-arguments raise a valid but non-fatal concern (e.g., minor R:R softness or near-term barrier); reduce size slightly.
- 0.5  = Counter-arguments identify a structural weakness (e.g., SL too tight, contradicts HTF trend) that the trade defense only partially mitigates; proceed cautiously.
- 0.25 = Counter-arguments are strong; proceed with minimal size as a probe trade.
- 0.0  = Fatal flaw detected in trade thesis; final_decision MUST be 'avoid'.

ROUND 2 REBUTTAL & BAYESIAN CALIBRATION:
- If a Round 2 Rebuttal ('bull_rebuttal' or 'bear_rebuttal') is present, assess its rebuttal_evidence against the opposing critiques:
  * Strong Rebuttal (rebuttal_strength >= 7 with verified numerical confluences): Mitigates counter-thesis severity. If the dissenter claimed severity >= 8 but the advocate successfully refuted it with factual data, do NOT reject solely on dissenter claim; calibrate risk according to residual risk (e.g. 0.50 - 0.75).
  * Concessions Made (conceded_points): If the advocate conceded specific weaknesses (e.g. SL too close or overhead barrier), adjust entry/SL/TP or cap risk_multiplier <= 0.50.
  * Weak/Failed Rebuttal (rebuttal_strength <= 4 or ungrounded): Opposing dissent is validated. If counter-threat >= 9, enforce final_decision = 'avoid' and risk_multiplier = 0.0.

TELEMETRY & SPECIALIST TRUST GUIDELINES:
- Inspect 'fact_sheet.specialist_reliability' if present:
  * If a specialist (technical, sentiment, macro) has trust_weight < 0.50 or is chronically_unreliable=true, heavily discount arguments relying primarily on that specialist's input.
  * If a thesis was built on an unreliable specialist and challenged by a reliable specialist (trust_weight >= 1.0), rule in favor of the reliable specialist.
- Inspect 'fact_sheet.news_calibration_directives': If news tier calibration reports over-classification in recent cycles, do NOT allow breaking news sentiment to override higher-timeframe technical market structure.

MANDATORY FACT-CHECKING STEP:
Before adjusting any risk multiplier or proposing level adjustments, verify:
1. Is the counter-argument supported by concrete technical levels (Swing High/Low, Order Block, FVG, ATR distance) or specific macro data points?
2. Does the proposed Stop Loss violate the 1.0x ATR minimum distance from entry?
3. If the counter-argument is purely rhetorical without factual data basis, do NOT penalize the trade — maintain risk_multiplier = 1.0.

MANDATORY ADJUSTMENT CONSTRAINT: If proposing adjusted_entry, adjusted_sl, or adjusted_tp, the resulting Risk-to-Reward ratio MUST remain >= 1.3 (i.e. |adjusted_tp - entry| >= 1.3 * |entry - adjusted_sl|). Any proposed adjustment with R:R < 1.3 will be automatically rejected by backend risk validators.

{get_universal_execution_discipline()}

[TELEGRAPHIC MANDATE]: Think strictly in dense analytical bullet points. Verify math against ATR and risk tables. reason must be at most 2 concise sentences based strictly on factual evidence. Zero fluff.
Respond in valid JSON format conforming to the schema."""
    
    schema = {
        "type": "object",
        "properties": {
            "final_decision": {"type": "string", "enum": ["buy", "sell", "avoid"]},
            "reason": {"type": "string"},
            "risk_multiplier": {"type": "number"},
            "adjusted_entry": {"type": ["number", "null"]},
            "adjusted_sl": {"type": ["number", "null"]},
            "adjusted_tp": {"type": ["number", "null"]},
            "regime_weights_used": {"type": "object"}
        },
        "required": ["final_decision", "reason", "risk_multiplier"]
    }

    debate_payload = {
        "symbol": symbol,
        "direction": decision,
        "original_context": compress_debate_trajectory(original_context, max_text_len=600),
        "regime_weights": regime_weights,
        "bull_claim": compress_debate_trajectory(bull_claim, max_text_len=800),
        "bear_dissent": compress_debate_trajectory(bear_dissent, max_text_len=800),
    }
    if bull_rebuttal:
        rebuttal_key = "bear_rebuttal" if decision == "SELL" else "bull_rebuttal"
        debate_payload[rebuttal_key] = compress_debate_trajectory(bull_rebuttal, max_text_len=800)

    user_prompt = f"Evaluate Debate for {symbol} ({decision}):\n{json.dumps(debate_payload, separators=(',', ':'), default=str)}\n\nProceed with evaluation based strictly on the data above."
    
    try:
        parsed: Optional[Dict[str, Any]] = None
        judge_max_tokens = getattr(client, 'max_tokens', 6144) or 6144
        if hasattr(client, 'classify_json'):
            parsed = await client.classify_json(
                user_prompt,
                system_prompt=system_prompt,
                schema=schema,
                max_tokens=judge_max_tokens
            )
        elif hasattr(client, 'generate_content'):
            resp = await client.generate_content(
                system_prompt=system_prompt,
                user_message=user_prompt,
                response_schema=schema,
                max_tokens=judge_max_tokens
            )
            if resp:
                import re
                cleaned = resp.strip()
                if "```" in cleaned:
                    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned)
                    if match:
                        cleaned = match.group(1)
                parsed = json.loads(cleaned)

        if not parsed or not isinstance(parsed, dict):
            raise ValueError(f"Empty or invalid response from LLM: {parsed}")

        # Ensure risk multiplier is bounded with Bayesian rebuttal mitigation
        final_dec = str(parsed.get("final_decision", "")).lower()
        is_sell = (decision == "SELL")
        if is_sell:
            # For SELL: Counter-threat is Bull's strength_score, Pro-strength is Bear's score
            counter_threat = int((bull_claim or {}).get("strength_score", 5) or 5)
            pro_strength = int((bear_dissent or {}).get("risk_severity", 5) or 5)
        else:
            # For BUY: Counter-threat is Bear's risk_severity, Pro-strength is Bull's score
            counter_threat = int((bear_dissent or {}).get("risk_severity", 5) or 5)
            pro_strength = int((bull_claim or {}).get("strength_score", 5) or 5)

        bull_reb_str = int((bull_rebuttal or {}).get("rebuttal_strength", 0) or 0) if bull_rebuttal else 0

        # Effective counter threat is downgraded if strong factual defense was presented
        effective_counter_threat = counter_threat
        if bull_rebuttal and bull_reb_str >= 7:
            effective_counter_threat = max(1, counter_threat - 3)

        raw_multiplier = float(parsed.get("risk_multiplier", 1.0) or 1.0)

        # In volatile regimes, penalize raw risk multiplier or enforce avoid on high counter threat
        if detected_regime == "volatile":
            if effective_counter_threat >= 7 and pro_strength < 8:
                final_dec = "avoid"
                raw_multiplier = 0.0
            else:
                raw_multiplier = max(0.20, raw_multiplier - regime_weights["volatility_penalty"])

        if final_dec == "avoid" or (effective_counter_threat >= 9 and raw_multiplier <= 0.25):
            parsed["final_decision"] = "avoid"
            parsed["risk_multiplier"] = 0.0
        else:
            parsed["risk_multiplier"] = max(0.20, min(1.0, raw_multiplier))

        parsed["regime_weights_used"] = regime_weights
        return parsed
    except Exception as e:
        logger.critical(f"FATAL: Failed to parse Investment Judge JSON: {e}. Enforcing fail-closed capital protection.")
        return {
            "final_decision": "avoid",
            "reason": f"CRITICAL: Investment Judge evaluation failed or crashed ({e}). Trade rejected for capital protection.",
            "risk_multiplier": 0.0,
            "regime_weights_used": regime_weights,
            "parse_error": True,
            "fail_closed_triggered": True
        }
