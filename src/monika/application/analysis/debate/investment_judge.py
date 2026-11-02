import asyncio
import json
import logging
from typing import Any, Dict, Optional

from monika.infrastructure.llm.prompt_disciplines import get_universal_execution_discipline
from monika.infrastructure.providers.base_provider import BaseLLMClient

logger = logging.getLogger("TradingAgent.InvestmentJudge")

REGIME_WEIGHT_MATRIX = {
    "trending": {
        "trend_thesis_weight": 0.65,
        "counter_thesis_weight": 0.35,
        "volatility_penalty": 0.0,
        "description": "Trending market: higher weight on trend momentum, require verified structural failure to veto.",
    },
    "ranging": {
        "trend_thesis_weight": 0.50,
        "counter_thesis_weight": 0.50,
        "volatility_penalty": 0.10,
        "description": "Ranging market: balanced weight, mean-reversion favored, tight SL required.",
    },
    "volatile": {
        "trend_thesis_weight": 0.30,
        "counter_thesis_weight": 0.70,
        "volatility_penalty": 0.20,
        "description": "High volatility/shock: heavy weight to risk dissent, aggressive size reduction or veto.",
    },
    "unknown": {
        "trend_thesis_weight": 0.50,
        "counter_thesis_weight": 0.50,
        "volatility_penalty": 0.0,
        "description": "Neutral baseline regime.",
    },
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
    except ValueError, TypeError:
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
            return truncated[: last_idx + len(punct)].strip() + " [compacted]"
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
    bull_rebuttal: Optional[dict] = None,
    fact_sheet: Optional[Any] = None,
) -> dict:
    if not bull_claim or not bear_dissent or not original_context:
        missing_name = "bull_claim" if not bull_claim else ("bear_dissent" if not bear_dissent else "original_context")
        logger.warning(
            f"[{symbol}] Incomplete debate inputs ({missing_name} missing). Enforcing fail-closed capital protection."
        )
        return {
            "final_decision": "avoid",
            "decision": "wait",
            "risk_multiplier": 0.0,
            "reason": f"CRITICAL: Missing debate input ({missing_name}). Trade avoided.",
            "fail_closed_triggered": True,
            "regime_weights_used": resolve_regime_weights(original_context or {}),
        }

    from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

    system_prompt = CacheBreakpointManager.get_canonical_debate_system_prompt()
    decision = str(original_context.get("decision", "buy")).upper()
    regime_weights = resolve_regime_weights(original_context)
    detected_regime = regime_weights["detected_regime"]

    bull_brier = float(original_context.get("bull_brier_score") or original_context.get("bull_brier") or 0.25)
    bear_brier = float(original_context.get("bear_brier_score") or original_context.get("bear_brier") or 0.25)
    bw_bull = 1.0 / max(0.01, bull_brier)
    bw_bear = 1.0 / max(0.01, bear_brier)
    tot_bw = bw_bull + bw_bear
    norm_bull_bw = bw_bull / tot_bw
    norm_bear_bw = bw_bear / tot_bw

    task_directive = f"""[EVALUATE DEBATE FOR {symbol} ({decision})]:
You are the Chief Investment Officer (Judge).
Evaluate the proposed trade setup in 'original_context', alongside the Bull Analyst's analysis, the Bear Analyst's analysis, and any Round 2 Rebuttal.

MARKET REGIME CALIBRATION CONTEXT:
- Detected Regime: {detected_regime.upper()}
- Thesis Weight (Trend): {regime_weights["trend_thesis_weight"]:.2f}
- Counter Thesis Weight: {regime_weights["counter_thesis_weight"]:.2f}
- Volatility Penalty: {regime_weights["volatility_penalty"]:.2f}
- Guidance: {regime_weights["description"]}

BRIER SCORE CALIBRATION WEIGHING (Subsystem 4):
- Bull Analyst Historical Brier: {bull_brier:.3f} (Calibration weight: {norm_bull_bw:.0%})
- Bear Analyst Historical Brier: {bear_brier:.3f} (Calibration weight: {norm_bear_bw:.0%})
- The analyst with lower Brier score has superior empirical calibration; give their arguments proportionally higher weight.

DIRECTIONAL ADJUDICATION RULES:
- INTRADAY ADR GEOMETRY & R:R COMPLIANCE (CRITICAL):
  * Any bracket with net R:R >= 1.50 (including LONG_OPTION_A and SHORT_OPTION_B with R:R = 1.50 - 1.65) and SL >= 1.0x H4 ATR (or ADR-harmonized floor >= 0.95x ATR / <= 0.50x ADR) is 100% COMPLIANT with Monika's intraday ADR geometry.
  * NEVER reject or downgrade a trade solely because R:R is 1.50 - 1.70 instead of R:R >= 1.75 or R:R >= 2.00.
- REGIME CLASSIFICATION & SPECIALIST SYNERGY ADJUDICATION:
  * Explicitly evaluate 'regime_classification', 'dealing_range_pos', 'h4_impulse_atr', and 'specialist_consensus.synergy_state' from the 'fact_sheet':
  * APPROVE ('buy' / 'sell') when 'proposed_decision' aligns with:
    1) DISCOUNT_ACCUMULATION_ZONE (dealing_range_pos <= 0.38 for 'buy', even if lagging Stage 1 macro or unanimous specialists are bearish),
    2) PREMIUM_DISTRIBUTION_ZONE (dealing_range_pos >= 0.62 for 'sell', even if lagging Stage 1 macro or unanimous specialists are bullish),
    3) institutional_contrarian_synergy or uncrowded_institutional_synergy,
    4) CROWDED_TECH_SENT_TRAP_VS_MACRO (favoring 'macro' direction against the retail Technical+Sentiment trap),
    5) BULLISH_IMPULSE_BREAKOUT / BEARISH_IMPULSE_BREAKOUT (|h4_impulse_atr| >= 1.25).
  * REJECT ('avoid', risk_multiplier = 0.0) when the trade:
    1) Enters inside EQUILIBRIUM_DEAD_ZONE_CHOP (0.40 <= dealing_range_pos <= 0.60 and |h4_impulse_atr| < 0.25),
    2) Market-chases at range extremes without a structure breakout (e.g. buying at pos >= 0.80 or selling at pos <= 0.20), or
    3) Falls into crowded_tech_sent_trap_vs_macro against the Macro Specialist.
If original_context decision is CONFLICT_ADJUDICATION or WAIT or NEUTRAL (Two-Sided Dialectical Debate):
- Symmetrical Evaluation: Bull Analyst proposes Long setup; Bear Analyst proposes Short/Downside setup.
- 3-Zone Spatial Dealing Range & Dual-Engine Rules:
  * DEEP DISCOUNT (dealing range pos <= 0.35) / DISCOUNT_ACCUMULATION_ZONE (pos <= 0.38): Institutional accumulation territory. APPROVE BUY if either:
    1) Engine 1 (Macro-Aligned/Neutral): Unmitigated Demand OB/FVG retest with net R:R >= 1.50 and SL >= 1.0x H4 ATR (or >= 0.95x ATR / <= 0.50x ADR). Calibrated risk multiplier 0.75 - 1.0.
    2) Engine 2 (Contra-Macro): DISCOUNT_ACCUMULATION_ZONE (pos <= 0.38) or Confirmed Liquidity Sweep of swing low (Turtle Soup) + MSS displacement with net R:R >= 1.50. Downscale risk multiplier to 0.65 - 0.85.
    If contra-macro outside Discount Accumulation and NO confirmed sweep (untethered falling knife), declare final_decision = 'avoid' with risk_multiplier = 0.0.
  * DEEP PREMIUM (dealing range pos >= 0.65): Institutional distribution territory. APPROVE SELL if either:
    1) Engine 1 (Macro-Aligned/Neutral): Unmitigated Supply OB/FVG retest with net R:R >= 1.50 and SL >= 1.0x H4 ATR (or >= 0.95x ATR / <= 0.50x ADR). Calibrated risk multiplier 0.75 - 1.0.
    2) Engine 2 (Contra-Macro): Confirmed Liquidity Sweep of swing high + MSS displacement with net R:R >= 1.50. Downscale risk multiplier to 0.65 - 0.85.
    If contra-macro and NO confirmed sweep (untethered parabolic rally), declare final_decision = 'avoid' with risk_multiplier = 0.0.
  * EQUILIBRIUM REGIME (0.35 < pos < 0.65): Mid-range environment. Reject ('avoid') if regime_classification is EQUILIBRIUM_DEAD_ZONE_CHOP. Otherwise APPROVE either Long (Option A) or Short (Option B) if backed by verified structural POI (unmitigated FVG, Order Block, or clean breakout beyond local swing high/low) with net R:R >= 1.50 and SL >= 1.0x H4 ATR (or >= 0.95x ATR / <= 0.50x ADR). Calibrate risk multiplier to 0.70 - 0.85. Only declare 'avoid' if price action is completely directionless with no identifiable structural anchor.
- Trend Climax & Anti-Exhaustion Guard: If ADX > 50 or regime_classification is OVEREXTENDED_RANGE_CEILING_PULLBACK_RISK without a structure breakout, evaluate as potential climax exhaustion rather than fresh breakout. Require retest of structural POI.
- Minimum Asymmetry: Approve the side that demonstrates verified structural edge, Stop Loss distance >= 1.0x H4 ATR (or ADR-harmonized floor >= 0.95x ATR / <= 0.50x ADR), and net R:R >= 1.50. If both sides lack structural edge, rule 'avoid' with risk_multiplier = 0.0.
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

ASYMMETRIC EDGE & RISK-SCALING PROTOCOL (DO NOT DEFAULT TO AVOID):
Financial markets inherently carry risk and dissenting arguments can always be made. If the trade proposal satisfies canonical structural criteria (R:R >= 1.50, structural SL outside 1.0x ATR noise floor, clear dealing range discount/premium alignment):
- DO NOT DEFAULT TO AVOID simply because Bull and Bear are evenly matched or macro uncertainty exists.
- If the thesis has a positive structural edge but carries macroeconomic or timing uncertainty, you MUST APPROVE the trade with scaled-down risk (risk_multiplier between 0.50 and 0.75).
- You are ONLY permitted to declare final_decision = 'avoid' (risk_multiplier = 0.0) if the dissenter proves a catastrophic factual failure: e.g. key market structure level already broken, major high-impact CPI/NFP event in < 1 hour, or extreme orderbook illiquidity.
- Preserving profitable expectancy: Capturing high-probability R:R >= 1.50 setups with controlled position sizing is superior to paralyzing the system into 100% avoid.

MANDATORY ADJUSTMENT CONSTRAINT: If proposing adjusted_entry, adjusted_sl, or adjusted_tp, the resulting Risk-to-Reward ratio MUST remain >= 1.50 (i.e. |adjusted_tp - entry| >= 1.50 * |entry - adjusted_sl|). Any proposed adjustment with R:R < 1.50 will be automatically rejected by backend risk validators. If adjusting SL wider to clear structural noise, you MUST proportionally adjust TP outward to preserve R:R >= 1.50.

Proceed with evaluation based strictly on the data above. Respond in valid JSON format conforming to the schema."""

    schema = {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Dense analytical synthesis evaluating thesis vs dissent and factual evidence",
            },
            "regime_weights_used": {"type": "object"},
            "risk_multiplier": {"type": "number"},
            "adjusted_entry": {"type": ["number", "null"]},
            "adjusted_sl": {"type": ["number", "null"]},
            "adjusted_tp": {"type": ["number", "null"]},
            "final_decision": {"type": "string", "enum": ["buy", "sell", "avoid"]},
        },
        "required": ["reason", "risk_multiplier", "final_decision"],
        "additionalProperties": False,
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
        if isinstance(bull_rebuttal, dict) and "bull_rebuttal" in bull_rebuttal and "bear_rebuttal" in bull_rebuttal:
            debate_payload["bull_rebuttal"] = compress_debate_trajectory(
                bull_rebuttal["bull_rebuttal"], max_text_len=800
            )
            debate_payload["bear_rebuttal"] = compress_debate_trajectory(
                bull_rebuttal["bear_rebuttal"], max_text_len=800
            )
        else:
            rebuttal_key = "bear_rebuttal" if decision == "SELL" else "bull_rebuttal"
            debate_payload[rebuttal_key] = compress_debate_trajectory(bull_rebuttal, max_text_len=800)

    # S²-MAD Sparse Debate: Inject structured blackboard state for dense, low-token evaluation
    try:
        from monika.application.analysis.debate.blackboard import DebateBlackboard

        bb = DebateBlackboard(symbol=symbol, fact_sheet=original_context)
        b_thesis = (
            (bull_claim or {}).get("thesis")
            or (bull_claim or {}).get("bull_thesis")
            or (bull_claim or {}).get("argument")
            or str(bull_claim or "")[:300]
        )
        bb.add_bull_thesis(
            b_thesis,
            confidence=float((bull_claim or {}).get("strength_score", 5.0) or 5.0) / 10.0,
            claim_dict=bull_claim or {},
        )
        br_thesis = (
            (bear_dissent or {}).get("counter_thesis")
            or (bear_dissent or {}).get("bear_dissent")
            or (bear_dissent or {}).get("bear_thesis")
            or (bear_dissent or {}).get("argument")
            or str(bear_dissent or "")[:300]
        )
        bb.add_bear_thesis(
            br_thesis,
            confidence=float((bear_dissent or {}).get("risk_severity", 5.0) or 5.0) / 10.0,
            claim_dict=bear_dissent or {},
        )
        debate_payload["sparse_blackboard"] = bb.render_sparse_summary()
    except Exception as bb_err:
        logger.debug(f"DebateBlackboard injection non-fatal: {bb_err}")

    effective_fact_sheet = fact_sheet if fact_sheet is not None else original_context.get("fact_sheet", {})
    append_ledger = dict(debate_payload)
    append_ledger.pop("original_context", None)

    user_prompt = CacheBreakpointManager.build_shared_debate_user_message(
        fact_sheet=effective_fact_sheet,
        original_context=original_context,
        append_ledger=append_ledger,
        task_directive=task_directive,
    )

    try:
        parsed: Optional[Dict[str, Any]] = None
        from monika.infrastructure.providers.capabilities import resolve_effective_max_tokens

        raw_model = getattr(client, "model", None)
        clean_model = str(raw_model) if isinstance(raw_model, str) else None

        raw_prov = getattr(client, "provider_name", None)
        clean_prov = str(raw_prov) if isinstance(raw_prov, str) else None

        raw_budget = getattr(client, "thinking_budget", None)
        clean_budget = (
            int(raw_budget) if isinstance(raw_budget, (int, float)) and not isinstance(raw_budget, bool) else None
        )

        raw_th_level = getattr(client, "thinking_level", None)
        clean_th_level = str(raw_th_level) if isinstance(raw_th_level, str) else None

        raw_settings = getattr(client, "settings", None)
        clean_settings = raw_settings if isinstance(raw_settings, dict) else None

        judge_max_tokens = resolve_effective_max_tokens(
            model_name=clean_model,
            provider_name=clean_prov,
            requested_max_tokens=None,
            thinking_budget=clean_budget,
            thinking_level=clean_th_level,
            settings=clean_settings,
            min_answer_headroom=1536,
        )

        # Resilience: 2 attempts with exponential backoff on transient upstream socket/rate errors
        for attempt in range(2):
            try:
                if hasattr(client, "classify_json"):
                    parsed = await client.classify_json(
                        user_prompt, system_prompt=system_prompt, schema=schema, max_tokens=judge_max_tokens
                    )
                elif hasattr(client, "generate_content"):
                    resp = await client.generate_content(
                        system_prompt=system_prompt,
                        user_message=user_prompt,
                        response_schema=schema,
                        max_tokens=judge_max_tokens,
                    )
                    if resp:
                        import re

                        cleaned = resp.strip()
                        if "```" in cleaned:
                            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
                            if match:
                                cleaned = match.group(1)
                        parsed = json.loads(cleaned)
                if parsed and isinstance(parsed, dict):
                    break
            except Exception as retry_err:
                if attempt == 0:
                    logger.warning(
                        f"[{symbol}] Investment Judge call failed (attempt 1/2: {retry_err}). Retrying in 0.5s..."
                    )
                    await asyncio.sleep(0.5)
                else:
                    logger.error(f"[{symbol}] Investment Judge retry failed (attempt 2/2: {retry_err})")

        if not parsed or not isinstance(parsed, dict):
            # Fallback: if debate inputs were clean (no parse error), check if evidence strongly favors the trade
            is_sell_prep = decision == "SELL"
            c_threat_est = int(
                (bull_claim if is_sell_prep else bear_dissent or {}).get(
                    "strength_score" if is_sell_prep else "risk_severity", 5
                )
                or 5
            )
            pro_str_est = int(
                (bear_dissent if is_sell_prep else bull_claim or {}).get(
                    "risk_severity" if is_sell_prep else "strength_score", 5
                )
                or 5
            )
            has_corrupt_inputs = bool((bull_claim or {}).get("parse_error") or (bear_dissent or {}).get("parse_error"))

            if not has_corrupt_inputs and pro_str_est >= c_threat_est + 2 and c_threat_est < 7:
                logger.warning(
                    f"[{symbol}] LLM Judge unavailable, but debate inputs show decisive pro-strength "
                    f"({pro_str_est} vs {c_threat_est}). Applying defensive algorithmic fallback adjudication (0.40x risk)."
                )
                parsed = {
                    "final_decision": decision.lower(),
                    "risk_multiplier": 0.40,
                    "reason": (
                        f"Algorithmic fallback adjudication: upstream Judge LLM timed out, but debate evidence "
                        f"confirms pro-strength ({pro_str_est}) exceeds counter-threat ({c_threat_est}). "
                        f"Trade preserved with defensive 0.40x risk multiplier."
                    ),
                    "rationale": "Automated debate adjudication under transient LLM failover.",
                    "counter_thesis_flaws": [
                        "Upstream LLM judge timed out; fallback applied from structured debate claims."
                    ],
                }
            else:
                raise ValueError(f"Empty or invalid response from LLM: {parsed}")

        # Enforce fail-closed safety if either debate participant experienced a parse or upstream failure
        if (bull_claim or {}).get("parse_error") or (bear_dissent or {}).get("parse_error"):
            logger.warning(
                f"[{symbol}] Corrupted or failed debate inputs detected. Enforcing fail-closed capital protection."
            )
            parsed["final_decision"] = "avoid"
            parsed["risk_multiplier"] = 0.0
            parsed["reason"] = "CRITICAL: Debate inputs contained parse errors or corrupted arguments. Trade avoided."
            parsed["fail_closed_triggered"] = True
            parsed["regime_weights_used"] = regime_weights
            return parsed

        # Ensure risk multiplier is bounded with Bayesian rebuttal mitigation
        final_dec = str(parsed.get("final_decision", "")).lower()
        is_conflict_mode = decision in ("CONFLICT_ADJUDICATION", "WAIT", "NEUTRAL")
        is_sell = (decision == "SELL") or (is_conflict_mode and final_dec == "sell")
        if is_sell:
            # For SELL: Counter-threat is Bull's strength_score, Pro-strength is Bear's score
            counter_threat = int((bull_claim or {}).get("strength_score", 5) or 5)
            pro_strength = int(
                (bear_dissent or {}).get("risk_severity") or (bear_dissent or {}).get("strength_score") or 5
            )
        else:
            # For BUY: Counter-threat is Bear's risk_severity, Pro-strength is Bull's score
            counter_threat = int(
                (bear_dissent or {}).get("risk_severity") or (bear_dissent or {}).get("strength_score") or 5
            )
            pro_strength = int((bull_claim or {}).get("strength_score", 5) or 5)

        bull_reb_str = int((bull_rebuttal or {}).get("rebuttal_strength", 0) or 0) if bull_rebuttal else 0
        proposer_rebuttal_score = max(bull_reb_str, pro_strength) if is_conflict_mode else bull_reb_str

        # Effective counter threat is downgraded if strong factual defense was presented
        effective_counter_threat = counter_threat
        if (bull_rebuttal and bull_reb_str >= 7) or (is_conflict_mode and proposer_rebuttal_score >= 7):
            effective_counter_threat = max(1, counter_threat - 3)

        raw_multiplier = float(parsed.get("risk_multiplier", 1.0) or 1.0)

        # Brier-score post-processing calibration (Subsystem 4)
        dissenter_brier = bull_brier if is_sell else bear_brier
        pro_brier = bear_brier if is_sell else bull_brier
        if dissenter_brier < pro_brier - 0.08:
            # Dissenter has superior empirical calibration; heighten caution on counter-threats
            if effective_counter_threat >= 6:
                raw_multiplier = round(raw_multiplier * 0.75, 2)
                logger.info(
                    f"[{symbol}] Dissenter Brier calibration advantage ({dissenter_brier:.3f} vs {pro_brier:.3f}) applied: "
                    f"risk dampened to {raw_multiplier}x."
                )
        elif pro_brier < dissenter_brier - 0.08:
            # Advocate has superior empirical calibration; mitigate ungrounded dissenter penalties
            if effective_counter_threat < 8 and raw_multiplier < 1.0:
                raw_multiplier = min(1.0, round(raw_multiplier * 1.15, 2))

        # In volatile regimes, penalize raw risk multiplier or enforce avoid on high counter threat
        if detected_regime == "volatile":
            if effective_counter_threat >= 7 and pro_strength < 8:
                final_dec = "avoid"
                raw_multiplier = 0.0
            else:
                raw_multiplier = max(0.20, raw_multiplier - regime_weights["volatility_penalty"])

        fatal_flaw_override = (decision in ("BUY", "SELL")) and (effective_counter_threat >= 9)
        if final_dec == "avoid" or fatal_flaw_override:
            parsed["final_decision"] = "avoid"
            parsed["risk_multiplier"] = 0.0
            if fatal_flaw_override and final_dec != "avoid":
                parsed["rationale"] = (
                    f"[FATAL FLAW OVERRIDE] Critical counter-threat established ({effective_counter_threat}/10). "
                    f"Decision overridden to avoid. {parsed.get('rationale', '')}"
                )
        else:
            parsed["risk_multiplier"] = max(0.20, min(1.0, raw_multiplier))

        parsed["regime_weights_used"] = regime_weights
        parsed["brier_calibration"] = {
            "bull_brier": bull_brier,
            "bear_brier": bear_brier,
            "bull_weight": round(norm_bull_bw, 3),
            "bear_weight": round(norm_bear_bw, 3),
        }
        return parsed
    except Exception as e:
        logger.critical(f"FATAL: Failed to parse Investment Judge JSON: {e}. Enforcing fail-closed capital protection.")
        return {
            "final_decision": "avoid",
            "reason": f"CRITICAL: Investment Judge evaluation failed or crashed ({e}). Trade rejected for capital protection.",
            "risk_multiplier": 0.0,
            "regime_weights_used": regime_weights,
            "parse_error": True,
            "fail_closed_triggered": True,
        }
