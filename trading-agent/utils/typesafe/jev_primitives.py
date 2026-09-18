"""
TypeSafe Jev Primitives & Question Builders for Quantitative Trading Agent.

Bridges existing JSON schemas and agent workflows into TypeSafe Jev System One
decision primitives (Choice, Score, Noul).
"""

from typing import Dict, Any, Optional, List, Union
import logging
from typesafe_sdk import Choice, Score, Noul, SystemOneResponse, ChoiceAnswer, ScoreAnswer, NoulAnswer

logger = logging.getLogger("TradingAgent.JevPrimitives")


def schema_to_jev_questions(schema: dict, base_prompt: str = "") -> Dict[str, Union[Choice, Score, Noul]]:
    """
    Dynamically converts a JSON Schema (commonly passed to classify_json)
    into a dictionary of TypeSafe Jev Questions (Choice, Score, Noul).
    """
    questions: Dict[str, Union[Choice, Score, Noul]] = {}
    if not isinstance(schema, dict):
        return questions

    properties = schema.get("properties", {})
    if not properties and schema.get("type") == "object":
        properties = {k: v for k, v in schema.items() if isinstance(v, dict)}
    elif not properties and schema.get("type") == "array":
        properties = schema.get("items", {}).get("properties", {})

    for prop_name, prop_def in properties.items():
        if not isinstance(prop_def, dict):
            continue

        desc = prop_def.get("description") or f"Evaluate {prop_name}"
        prop_type = prop_def.get("type", "string")
        enum_vals = prop_def.get("enum")

        # 0. Specialized macro currency bias map
        if prop_name == "currency_bias":
            for cur in ("USD", "EUR", "GBP", "JPY", "AUD", "XAU"):
                questions[f"bias_{cur}"] = Choice(
                    instructions=f"Directional bias for {cur} based on current macroeconomic context:",
                    criteria={
                        "bullish": f"Bullish / Strengthening {cur}",
                        "bearish": f"Bearish / Weakening {cur}",
                        "neutral": f"Neutral / Ranging / Mixed {cur}"
                    }
                )
            continue

        # 1. Binary yes/no decisions
        if prop_type == "boolean":
            questions[prop_name] = Noul(
                instructions=desc,
                criteria={"true": f"{prop_name} is true / satisfied", "false": f"{prop_name} is false / not satisfied"}
            )
            continue

        if enum_vals and len(enum_vals) == 2:
            upper_enums = [str(e).strip().upper() for e in enum_vals]
            if set(upper_enums) in ({"YES", "NO"}, {"TRUE", "FALSE"}, {"1", "0"}):
                true_val = "YES" if "YES" in upper_enums else "TRUE"
                questions[prop_name] = Noul(
                    instructions=desc,
                    criteria={"true": f"Return {true_val}", "false": f"Do not return {true_val}"}
                )
                continue

        # 2. Ordered scale / score
        if prop_type in ("integer", "number") and ("minimum" in prop_def or "maximum" in prop_def):
            min_val = prop_def.get("minimum", 1)
            max_val = prop_def.get("maximum", 5)
            # Build 2-5 level criteria
            steps = int(max_val - min_val) + 1
            if 2 <= steps <= 10:
                criteria = [f"Level {i} ({desc})" for i in range(int(min_val), int(max_val) + 1)]
                questions[prop_name] = Score(instructions=desc, criteria=criteria)
                continue

        # 3. Categorical choice
        if enum_vals:
            criteria_dict = {}
            for opt in enum_vals:
                opt_str = str(opt)
                criteria_dict[opt_str] = f"Option {opt_str}"
            questions[prop_name] = Choice(instructions=desc, criteria=criteria_dict)
            continue

        # 4. Fallback for string without enum: default to Noul if looks like a condition
        if prop_type == "string" and any(k in prop_name.lower() for k in ("valid", "check", "approve", "pass", "ok")):
            questions[prop_name] = Noul(instructions=desc)
        else:
            # Simple binary confirmation
            questions[prop_name] = Noul(instructions=f"Is {desc} applicable?")

    return questions


def parse_jev_response_to_dict(
    response: SystemOneResponse,
    schema: Optional[dict] = None,
    default_confidence_threshold: float = 0.7
) -> Dict[str, Any]:
    """
    Transforms a Jev SystemOneResponse into the standard dict expected by classify_json callers.
    Preserves confidence scores and probabilities under metadata keys.
    """
    result: Dict[str, Any] = {}
    confidences: Dict[str, float] = {}
    probabilities: Dict[str, Any] = {}
    overall_confidence: float = 1.0

    properties = (schema or {}).get("properties", {}) if isinstance(schema, dict) else {}

    for q_name, ans in response.answers.items():
        prop_spec = properties.get(q_name, {})
        prop_type = prop_spec.get("type")
        prop_enum = prop_spec.get("enum", [])

        if isinstance(ans, NoulAnswer):
            prob = float(ans.noul)
            confidences[q_name] = prob if prob >= 0.5 else (1.0 - prob)
            probabilities[q_name] = {"true": prob, "false": 1.0 - prob}

            # Type coercion based on expected schema
            if prop_type == "boolean":
                result[q_name] = (prob >= 0.5)
            elif prop_enum and any(str(e).upper() in ("YES", "NO") for e in prop_enum):
                # Match casing of schema enum
                yes_token = next((e for e in prop_enum if str(e).upper() == "YES"), "YES")
                no_token = next((e for e in prop_enum if str(e).upper() == "NO"), "NO")
                result[q_name] = yes_token if prob >= 0.5 else no_token
            elif prop_type in ("number", "float"):
                result[q_name] = prob
            else:
                result[q_name] = "YES" if prob >= 0.5 else "NO"

        elif isinstance(ans, ChoiceAnswer):
            result[q_name] = ans.choice
            conf = getattr(ans, "confidence", 1.0)
            confidences[q_name] = float(conf)
            probabilities[q_name] = getattr(ans, "probabilities", {})

        elif isinstance(ans, ScoreAnswer):
            score_val = float(ans.score)
            conf = getattr(ans, "confidence", 1.0)
            confidences[q_name] = float(conf)
            probabilities[q_name] = getattr(ans, "probabilities", {})
            if prop_type == "integer":
                result[q_name] = round(score_val)
            else:
                result[q_name] = score_val

    if confidences:
        overall_confidence = min(confidences.values())

    # Reassemble currency_bias dict if bias_* questions were generated
    bias_map = {}
    for k, v in list(result.items()):
        if k.startswith("bias_"):
            cur = k.replace("bias_", "").upper()
            bias_map[cur] = str(v).lower()
    if bias_map:
        result["currency_bias"] = bias_map
        if "agreement_pct" not in result:
            if confidences:
                bias_confs = [confidences.get(f"bias_{c.upper()}", 1.0) for c in bias_map]
                result["agreement_pct"] = round((sum(bias_confs) / len(bias_confs)) * 100, 1)
                result["flagged_currencies"] = [
                    c for c in bias_map if confidences.get(f"bias_{c.upper()}", 1.0) < 0.60
                ]
            else:
                result["agreement_pct"] = 85.0
                result["flagged_currencies"] = []

    result["_confidence"] = overall_confidence
    result["_confidences"] = confidences
    result["_probabilities"] = probabilities
    result["_is_high_confidence"] = overall_confidence >= default_confidence_threshold
    result["_jev_model"] = response.model

    return result


def is_high_confidence(result: Dict[str, Any], min_confidence: float = 0.70) -> bool:
    """Helper to check if a Jev result satisfies a confidence threshold."""
    if not isinstance(result, dict):
        return False
    conf = result.get("_confidence", 1.0)
    return float(conf) >= min_confidence


# ==============================================================================
# Specialized Domain Question Builders
# ==============================================================================

def build_news_classification_questions() -> Dict[str, Union[Choice, Score, Noul]]:
    """
    Speculative fan-out question set for financial news categorization & market impact.
    Single parallel pass answering 4 core dimensions.
    """
    return {
        "impact": Choice(
            instructions="What is the market impact level of this financial news item for forex and commodities trading?",
            criteria={
                "BREAKING": "Immediate market-moving shock: unexpected rate hike/cut, surprise emergency central bank statement, severe geopolitical escalation, flash crash, war/sanction announcement",
                "HIGH": "Scheduled top-tier data deviating significantly from consensus (CPI, NFP, GDP), major central bank policy speech with new policy shift",
                "MEDIUM": "Moderate economic release within consensus range, secondary macroeconomic data, standard corporate or commodity news",
                "LOW": "Routine market commentary, minor statistics, expected speeches with no new policy signaling",
                "NOISE": "Opinion pieces, previews, general recaps, unrelated political commentary, or stale rehashed news"
            }
        ),
        "urgency_score": Score(
            instructions="Rate urgency for immediate trading desk response on a 5-point scale",
            criteria=[
                "No urgency — ignore or archive",
                "Low urgency — informative background context",
                "Moderate urgency — incorporate into next scheduled analysis cycle",
                "High urgency — prompt targeted re-analysis of affected currency pairs",
                "Critical emergency — immediate position protection and emergency evaluation required"
            ]
        ),
        "is_fresh_catalyst": Noul(
            instructions="Does this news introduce a genuinely new market catalyst deviating from baseline expectations?",
            criteria={
                "true": "New surprise event, escalation, unexpected data deviation, fresh policy stance",
                "false": "Repetition, stale news, opinion, preview of upcoming scheduled event, already known situation"
            }
        ),
        "is_deescalation": Noul(
            instructions="Does this news item represent a de-escalation of active market tension (e.g., ceasefire, tariff pause, diplomatic accord)?",
            criteria={
                "true": "Tension relief, ceasefire, negotiation progress, tariff exemption or rollback",
                "false": "Continuation, escalation, new dispute, or unrelated to active geopolitical/economic conflicts"
            }
        )
    }


def build_prescreen_questions(symbol: str) -> Dict[str, Union[Noul, Score]]:
    """
    Fast prescreen check determining whether an asset setup warrants full Stage 2 analysis.
    """
    return {
        "decision": Noul(
            instructions=f"Should we proceed with full Stage 2 deep analysis for {symbol} right now?",
            criteria={
                "true": "Market is open, volatility/VIX is manageable, price is near actionable support/resistance or clear technical setup exists",
                "false": "Risk is paused, market closed for this asset, ADX dead/flat, VIX extreme (>35), or no setup nearby"
            }
        ),
        "opportunity_score": Score(
            instructions=f"Rate the immediate setup quality and opportunity for {symbol}",
            criteria=[
                "Dead / unpromising — avoid analyzing",
                "Marginal — only analyze if spare compute available",
                "Standard — ordinary viable setup for standard cycle",
                "High priority — strong confluence near key level",
                "Exceptional — prime high-conviction setup"
            ]
        )
    }


def build_shadow_check_questions() -> Dict[str, Union[Noul, Score]]:
    """
    Shadow consistency and hallucination detection questions for Stage 1 fundamental briefs.
    Decomposes macro validity checks into atomic snap judgments.
    """
    return {
        "is_internally_consistent": Noul(
            instructions="Is the fundamental analysis free of contradictory statements between macro assumptions and conclusions?"
        ),
        "cites_specific_numbers": Noul(
            instructions="Does the brief cite specific numeric data points (GDP %, interest rates, CPI numbers)?"
        ),
        "tone_matches_data": Noul(
            instructions="Is the narrative tone consistent with the data direction described?"
        ),
        "rate_direction_consistent": Noul(
            instructions="Is the stated interest rate direction consistent with the central bank stance described?"
        ),
        "has_data_hallucination": Noul(
            instructions="Does the brief cite specific macroeconomic data points, percentages, or rate numbers that contradict provided reality baseline?"
        ),
        "quality_score": Score(
            instructions="Rate overall analytic quality and reasoning coherence",
            criteria=[
                "Flawed or contradictory",
                "Acceptable but lacks grounding",
                "Sound analysis with good evidence",
                "Exceptional, rigorous macroeconomic synthesis"
            ]
        )
    }


def build_adjudication_questions() -> Dict[str, Union[Choice, Noul, Score]]:
    """
    Verification questions for Stage 2 specialist debate adjudication.
    Directly aligns with ADJUDICATION_VERIFY_SCHEMA while maintaining backwards compatibility.
    """
    return {
        "adjudication_rule_correctly_applied": Noul(
            instructions="Check if the final decision respects the directional consensus and execution constraints of the Adjudication Framework.",
            criteria={
                "true": "Decision properly follows the framework rules (aligned specialists respected, conditional wait for pullbacks/confluence valid)",
                "false": "Decision violates framework (e.g. BUY when bearish consensus, or unexplained refusal to align)"
            }
        ),
        "expected_outcome_per_rules": Choice(
            instructions="Based strictly on the specialist biases and confluence, what is the expected outcome per rules?",
            criteria={
                "buy": "Specialists aligned bullish and confluence threshold met",
                "sell": "Specialists aligned bearish and confluence threshold met",
                "wait": "Specialists mixed/neutral, confluence below threshold, or waiting for pullback/retest",
                "avoid": "Conflicting high-conviction signals or extreme risk gate active",
                "ambiguous": "Unclear or insufficient data"
            }
        ),
        "is_conditional_wait": Noul(
            instructions="Is the final decision 'wait' specifically because price is overextended, waiting for pullback/retest, or waiting for confluence threshold?",
            criteria={
                "true": "Decision is WAIT due to entry timing, pullback, or confluence threshold while respecting directional bias",
                "false": "Decision is not wait, or wait is unconditional / unrelated to timing"
            }
        ),
        "verdict": Choice(
            instructions="What is the overall adjudication verdict?",
            criteria={
                "CONFIRM": "Decision is consistent with rules or is a valid conditional wait",
                "FLAG_FOR_REVIEW": "Minor discrepancy or borderline rationale",
                "CONTRADICTS_OWN_FRAMEWORK": "Direct contradiction of specialist consensus without valid execution timing justification"
            }
        ),
        "mismatch_category": Choice(
            instructions="If there is a mismatch or issue, categorize it:",
            criteria={
                "none": "No mismatch, decision is confirmed",
                "directional_conflict": "Decision opposes specialist consensus",
                "ignored_risk_gate": "Risk gate or confluence threshold was ignored",
                "unjustified_thesis": "Decision introduced unmotivated counter-thesis"
            }
        ),
        # Backwards compatibility keys
        "verdict_valid": Noul(
            instructions="Does the debate adjudication appropriately synthesize specialist arguments without ignoring critical risk factors?"
        ),
        "direction_conviction": Choice(
            instructions="What is the overall directional conviction based on the debate synthesis?",
            criteria={
                "BULLISH": "Clear bullish confluence across macro and technicals with acceptable risk",
                "BEARISH": "Clear bearish confluence across macro and technicals with acceptable risk",
                "NEUTRAL_WAIT": "Conflicting signals, high uncertainty, or insufficient risk-reward ratio"
            }
        ),
        "risk_reward_score": Score(
            instructions="Rate proposed risk-reward viability and trade safety",
            criteria=[
                "Unacceptable / high risk of stop run",
                "Marginal R:R",
                "Favorable standard setup (>1.5:1 R:R)",
                "Excellent high-probability asymmetry (>2.5:1 R:R)"
            ]
        )
    }


def build_realtime_news_questions(open_positions: Optional[List[str]] = None) -> Dict[str, Union[Score, Noul]]:
    """
    Instant news evaluation questions for active PositionGuardian & NewsWatcher protection.
    """
    symbols_text = ", ".join(open_positions) if open_positions else "any active forex or commodity pairs"
    return {
        "market_sentiment": Score(
            instructions="Rate immediate market sentiment of this breaking headline",
            criteria=[
                "Strongly Bearish / Risk-Off Panic",
                "Bearish / Risk-Off",
                "Neutral / Mixed",
                "Bullish / Risk-On",
                "Strongly Bullish / Risk-On Euphoria"
            ]
        ),
        "threatens_positions": Noul(
            instructions=f"Does this headline introduce immediate sharp adverse volatility threat to open positions in {symbols_text}?"
        ),
        "requires_circuit_breaker": Noul(
            instructions="Is this an extreme systemic shock requiring emergency circuit breaker or stop tightening?"
        )
    }


def build_fundamental_verifier_questions() -> Dict[str, Union[Noul, Score, Choice]]:
    """
    Evaluates internal logical consistency of macro fundamental brief.
    Replaces free-text contradiction strings with 4 atomic Noul contradiction types.
    """
    return {
        "internally_consistent": Noul(
            instructions="Is the macro narrative free of internal contradictions between stated currency biases and reasoning provided?",
            criteria={
                "true": "Narrative tone, currency biases, and risk sentiment all align logically",
                "false": "Contradiction found: e.g. hawkish narrative with bearish USD bias, or risk-on with bullish XAU without specific catalyst"
            }
        ),
        "contradiction_bias_vs_narrative": Noul(
            instructions="Does the narrative tone CONTRADICT any stated currency bias? E.g. hawkish Fed language but USD listed as bearish.",
            criteria={
                "true": "Clear contradiction between narrative direction and at least one currency bias",
                "false": "Narrative tone and currency biases are aligned"
            }
        ),
        "contradiction_risk_vs_bias": Noul(
            instructions="Does the risk_sentiment CONTRADICT the currency biases? E.g. risk-on sentiment but XAU (safe haven) listed bullish without idiosyncratic reason.",
            criteria={
                "true": "Risk sentiment contradicts expected asset class behavior based on biases",
                "false": "Risk sentiment and biases are consistent"
            }
        ),
        "contradiction_confidence_vs_uncertainty": Noul(
            instructions="Is confidence > 0.7 despite the narrative describing significant uncertainty, conflicting data, or heavy hedging?",
            criteria={
                "true": "High confidence stated but narrative reveals substantial uncertainty or caveats",
                "false": "Confidence level is proportionate to narrative certainty"
            }
        ),
        "contradiction_data_vs_conclusion": Noul(
            instructions="Do any specific data points cited in the narrative contradict the directional conclusion drawn from them?",
            criteria={
                "true": "Data points cited lead to a different conclusion than what the narrative claims",
                "false": "Data points and conclusions are logically aligned"
            }
        ),
        "unjustified_confidence": Noul(
            instructions="Is the overall confidence level unjustifiably high given the uncertainty or contradictions in the analysis?",
            criteria={
                "true": "Confidence > 0.7 despite significant hedging language, data gaps, or conflicting signals",
                "false": "Confidence level is proportionate to the strength of evidence presented"
            }
        ),
        "counter_thesis_is_substantive": Noul(
            instructions="Is the strongest_counter_thesis specific, falsifiable, and non-generic?",
            criteria={
                "true": "Counter thesis references specific data threshold or event (e.g. 'If NFP > 250k')",
                "false": "Counter thesis is vague/generic (e.g. 'markets can be unpredictable', 'risks exist')"
            }
        ),
        "verdict": Choice(
            instructions="What is the overall verification verdict for this fundamental brief?",
            criteria={
                "pass": "Analysis is internally consistent, confidence justified, counter thesis is substantive",
                "flag_for_review": "Minor inconsistencies or borderline confidence justification",
                "reject": "Major internal contradiction or unjustified high confidence"
            }
        ),
        "quality_score": Score(
            instructions="Rate the overall analytical rigor and internal coherence of this fundamental brief",
            criteria=[
                "Fundamentally flawed — major contradictions or baseless claims",
                "Acceptable but with notable gaps or minor inconsistencies",
                "Solid analysis with good internal coherence and evidence-backed claims",
                "Excellent — rigorous, consistent, with well-calibrated confidence and specific counter-thesis"
            ]
        )
    }


def build_news_classification_verify_questions() -> Dict[str, Union[Choice, Noul]]:
    """
    Sub-100ms verification and calibration for classified news items.
    Handles High/Medium boundary calibration and Breaking downgrade skeptical check.
    """
    return {
        "impact_correct": Noul(
            instructions="Is the assigned impact level (BREAKING/HIGH/MEDIUM/LOW/NONE) appropriate for this news item?",
            criteria={
                "true": "Impact level matches the actual market-moving potential of this news",
                "false": "Impact level is too high or too low for this news content"
            }
        ),
        "corrected_impact": Choice(
            instructions="What should the correct impact level be?",
            criteria={
                "BREAKING": "Immediate market-moving shock: unexpected central bank action, major geopolitical escalation, black swan",
                "HIGH": "Significant scheduled data beat/miss or policy shift: NFP surprise, rate decision contrary to consensus",
                "MEDIUM": "Notable but within expected range: in-line data, expected guidance, moderate revision",
                "LOW": "Minor commentary or routine update: no immediate market impact expected",
                "NONE": "Noise, opinion, stale rehash, or non-financial content"
            }
        ),
        "currencies_relevant": Noul(
            instructions="Are the tagged currency pairs actually affected by this news?"
        ),
        "breaking_verdict": Choice(
            instructions="For items classified as BREAKING: should the classification be confirmed or downgraded?",
            criteria={
                "CONFIRM": "Genuinely BREAKING — unexpected, immediate market impact, not pre-scheduled",
                "DOWNGRADE_TO_HIGH": "Important but scheduled/expected — should be HIGH not BREAKING",
                "DOWNGRADE_TO_MEDIUM": "Not market-moving enough — should be MEDIUM at most"
            }
        )
    }


def build_digest_consistency_questions() -> Dict[str, Union[Noul, Score, Choice]]:
    """
    Gating questions for News Digest internal consistency.
    Determines whether expensive LLM reconciliation is needed.
    """
    return {
        "has_contradictions": Noul(
            instructions="Does the news digest contain any internal contradictions between different sections?",
            criteria={
                "true": "Two or more sections make conflicting claims about the same topic, asset, or event",
                "false": "Digest is internally consistent across all sections"
            }
        ),
        "contradiction_severity": Choice(
            instructions="If contradictions exist, what is their severity?",
            criteria={
                "none": "No contradictions detected",
                "minor": "Minor inconsistencies that don't affect trading decisions",
                "material": "Material contradictions that could mislead trading decisions"
            }
        ),
        "captures_key_events": Noul(
            instructions="Does the digest accurately capture the most market-moving events from the news batch?"
        ),
        "bias_balanced": Noul(
            instructions="Is the digest balanced, not overweighting minor news while underweighting major catalysts?"
        ),
        "digest_quality": Score(
            instructions="Rate the overall quality and utility of this news digest for trading decisions",
            criteria=[
                "Poor — misses key events or misleading emphasis",
                "Adequate — covers main events but lacks nuance",
                "Good — accurate prioritization with actionable insights",
                "Excellent — precise, concise, and actionable"
            ]
        )
    }


def build_position_guard_questions(symbol: str, direction: str) -> Dict[str, Union[Noul, Score]]:
    """
    Real-time position threat assessment questions for PositionGuardian.
    """
    return {
        "adverse_momentum": Noul(
            instructions=f"Given the current market data, is there strong adverse momentum against our {direction} position in {symbol}?",
            criteria={
                "true": "Price moving sharply against position direction, volume increasing, key level broken",
                "false": "Normal fluctuation, consolidation, or favorable momentum"
            }
        ),
        "sl_threat_level": Score(
            instructions=f"How close is the current price action to threatening the stop-loss of our {direction} {symbol} position?",
            criteria=[
                "Safe — price well within favorable zone",
                "Normal — standard volatility, no immediate concern",
                "Elevated — approaching danger zone, consider trailing stop",
                "Critical — stop-loss under immediate threat, consider defensive action"
            ]
        ),
        "should_tighten_stop": Noul(
            instructions=f"Based on current volatility and price structure, should the trailing stop for {symbol} be tightened?"
        )
    }


def build_telegram_intent_questions() -> Dict[str, Union[Choice, Noul]]:
    """
    Routes Telegram chat messages to appropriate model tier or direct handler.
    """
    return {
        "intent": Choice(
            instructions="What is the user's primary intent in this Telegram message?",
            criteria={
                "status_check": "User wants to know current system status, portfolio, or positions",
                "trade_command": "User wants to execute, modify, or close a trade",
                "analysis_request": "User wants analysis, market view, or chart review",
                "config_change": "User wants to change settings, risk parameters, or mode",
                "kill_switch": "User wants to stop/pause all trading or emergency shutdown",
                "general_question": "General question about the market or agent capabilities",
                "other": "Unrecognized or ambiguous intent"
            }
        ),
        "model_tier": Choice(
            instructions="What level of LLM processing does this message require?",
            criteria={
                "none": "Can be handled by direct code/database lookup without any LLM — e.g. status, portfolio balance, position list",
                "light": "Simple response — standard chat model sufficient",
                "medium": "Moderate complexity — needs precision for trade commands or config changes",
                "heavy": "Complex analysis or research — needs deep thinking model"
            }
        ),
        "is_urgent": Noul(
            instructions="Does this message convey urgency or time-sensitivity?"
        ),
        "requires_confirmation": Noul(
            instructions="Does this action require explicit confirmation before execution (e.g., trade execution, kill switch)?"
        )
    }


def build_risk_gate_neutral_questions(symbol: str, direction: str) -> Dict[str, Union[Score, Noul, Choice]]:
    """
    System One questions for neutral/balanced risk gate evaluation.
    Replaces generative LLM with structured score & confidence gating.
    """
    return {
        "risk_reward_balance": Score(
            instructions=f"Rate the risk-reward balance of this proposed {direction} trade on {symbol}",
            criteria=[
                "Strongly favorable — clear asymmetric opportunity with well-defined risk",
                "Mildly favorable — reasonable setup with acceptable risk parameters",
                "Neutral — no clear edge, risk and reward roughly balanced",
                "Unfavorable — risk outweighs potential reward given current conditions"
            ]
        ),
        "position_sizing_appropriate": Noul(
            instructions=f"Is the proposed position size appropriate given current portfolio exposure and volatility for {symbol}?",
            criteria={
                "true": "Position size is within acceptable bounds considering portfolio diversification and current volatility",
                "false": "Position size is too large relative to portfolio, or creates dangerous concentration"
            }
        ),
        "timing_acceptable": Noul(
            instructions=f"Is the timing of this {direction} entry on {symbol} acceptable from a balanced risk perspective?",
            criteria={
                "true": "Entry at reasonable price level, not chasing, volatility conditions manageable",
                "false": "Chasing extended move, entering ahead of known high-impact event, or volatile conditions advise waiting"
            }
        ),
        "portfolio_correlation_safe": Noul(
            instructions=f"Would adding {symbol} {direction} maintain healthy portfolio diversification?",
            criteria={
                "true": "Low correlation with existing positions, adds diversification benefit",
                "false": "High correlation with existing positions, amplifies portfolio risk"
            }
        ),
        "overall_approval": Choice(
            instructions=f"What is the balanced risk assessment verdict for this {symbol} {direction} trade?",
            criteria={
                "approve": "Risk-reward acceptable, position sizing and timing appropriate — proceed",
                "approve_with_reduced_size": "Generally acceptable but recommend smaller position due to concentration or volatility",
                "reject": "Risk too high from balanced perspective — do not proceed",
                "defer": "Insufficient information or marginal case — escalate to conservative gate"
            }
        )
    }


def build_exit_review_prescreen(symbol: str, direction: str, thesis: str = "") -> Dict[str, Union[Noul, Score]]:
    """
    Pre-screen questions for PositionExitReviewer to avoid full Stage 2 runs if thesis remains intact.
    """
    return {
        "thesis_still_valid": Noul(
            instructions=f"Is the original trading thesis for {direction} {symbol} still valid given current market conditions?",
            criteria={
                "true": "Key levels holding, no major contrary catalyst, original rationale intact",
                "false": "Key invalidation level breached, major contrary catalyst occurred, or thesis premise no longer holds"
            }
        ),
        "exit_urgency": Score(
            instructions=f"How urgently should we consider exiting the {direction} {symbol} position?",
            criteria=[
                "No urgency — thesis intact, position performing well",
                "Low urgency — minor concerns but thesis holds",
                "Moderate — thesis weakening, consider partial exit or tighter stop",
                "High — thesis materially damaged, active exit planning needed",
                "Critical — immediate exit recommended to preserve capital"
            ]
        )
    }


def build_scenario_branch_questions() -> Dict[str, Union[Choice, Score]]:
    """
    Scenario Tree branch classifier for dominant market path and conviction.
    """
    return {
        "dominant_scenario": Choice(
            instructions="Based on technical and fundamental state, which scenario is most likely for this asset?",
            criteria={
                "bull": "Bullish continuation — price likely to move higher based on structure and fundamentals",
                "bear": "Bearish continuation — price likely to move lower based on structure and fundamentals",
                "chop": "Range-bound / choppy — consolidation, no clear directional expansion"
            }
        ),
        "scenario_conviction": Score(
            instructions="How strong is the conviction for the dominant scenario?",
            criteria=[
                "Very weak — nearly equal probability across scenarios",
                "Weak — slight edge but highly uncertain",
                "Moderate — reasonable directional bias with supporting evidence",
                "Strong — clear confluence of signals supporting one direction",
                "Very strong — overwhelming evidence for directional move"
            ]
        )
    }


def build_adversarial_check_questions(symbol: str = "") -> Dict[str, Union[Choice, Noul, Score]]:
    """
    Structured System One questions for adversarial trade checks.
    Avoids free-text fields and evaluates risks via typed primitives.
    """
    return {
        "approve": Noul(
            instructions=f"Based on the analysis and deterministic risk flags for {symbol}, is this trade proposal approved to proceed?",
            criteria={
                "true": "Trade proposal has sound logic, acceptable risk-reward, and no fatal flaws",
                "false": "Trade proposal has major flaws, contradictions, or unacceptably elevated risk"
            }
        ),
        "overall_quality": Choice(
            instructions="What is the overall analytical quality of the trade proposal?",
            criteria={
                "high": "Rigorous thesis, clear confluence, properly bounded risk",
                "medium": "Standard acceptable setup with minor reservations",
                "low": "Weak thesis, questionable levels, or unaddressed counter-arguments"
            }
        ),
        "hard_block": Noul(
            instructions="Should this trade be HARD BLOCKED due to objective, verifiable flaws (contradictions, invalid R:R, ignored invalidation)?",
            criteria={
                "true": "Objective fatal flaw detected — must block unconditionally",
                "false": "No objective disqualifying flaw"
            }
        ),
        "recommend_block": Noul(
            instructions="Is a discretionary block recommended due to low setup quality or elevated market risk?",
            criteria={
                "true": "Setup quality is poor or risk/reward is unfavorable — recommend skip",
                "false": "Risk is manageable and within tolerable limits"
            }
        ),
        "primary_risk_category": Choice(
            instructions="What is the primary risk concern for this proposed trade?",
            criteria={
                "none": "No major concerns, setup is clean",
                "rr_unfavorable": "Risk-to-reward ratio is insufficient",
                "priced_in": "Catalyst or move is already heavily priced in",
                "technical_resistance": "Entering directly into major support/resistance or liquidity pool",
                "volatility_shock": "High event risk, upcoming news shock, or VIX extreme",
                "thesis_inconsistency": "Internal contradiction in directional reasoning"
            }
        )
    }


async def classify_news_batch_with_jev(
    client: Any,
    batch: list,
    now_utc: Any,
    calendar_priors: Optional[dict] = None,
    macro_context: str = "",
    min_confidence: float = 0.60
) -> Optional[List[Dict[str, Any]]]:
    """
    Classifies a batch of NewsItem instances using TypeSafe Jev System One in parallel.
    Returns list of dicts conforming to NEWS_CLASSIFICATION_SCHEMA if all pass confidence threshold.
    Returns None if Jev is unavailable or confidence is too low (triggering LLM fallback).
    """
    import asyncio
    from database.adapters import extract_currency_tags

    calendar_priors = calendar_priors or {}

    async def _classify_item(idx: int, item: Any) -> Optional[Dict[str, Any]]:
        t_sys = round((now_utc - item.fetched_at).total_seconds() / 60) if getattr(item, "fetched_at", None) else None
        prior = calendar_priors.get(idx)

        state = {
            "title": str(item.title or "")[:300],
            "summary": str(item.summary or "")[:1000],
            "time_in_system_minutes": t_sys,
            "calendar_prior_impact": str(prior) if prior else None,
            "macro_context": macro_context[:500] if macro_context else None,
        }

        questions = {
            "impact": Choice(
                instructions="Classify the market impact level for financial trading:",
                criteria={
                    "BREAKING": "Immediate market-moving shock: unexpected rate decision, major geopolitical escalation, flash crash, surprise economic data",
                    "HIGH": "Important scheduled data release (CPI, NFP, GDP), major policy speech with new guidance, significant market catalyst",
                    "MEDIUM": "Notable market development within expected range, routine economic update, standard corporate/commodity news",
                    "LOW": "Minor commentary, routine statistics, minor updates with no immediate trading impact",
                    "NONE": "Opinion pieces, previews, general recaps, commentary, or stale rehashed news"
                }
            ),
            "surprise_magnitude": Choice(
                instructions="For economic data releases only, estimate actual vs forecast surprise. For non-data news, choose none:",
                criteria={
                    "none": "Non-data news (speeches, geopolitical, opinions) OR release matching expectations",
                    "small": "Minor deviation from consensus",
                    "moderate": "Notable deviation from consensus",
                    "large": "Major surprise deviation from consensus (>2 sigma)"
                }
            ),
            "is_fresh_catalyst": Noul(
                instructions="Does this news introduce a genuinely new market catalyst not already priced in?"
            ),
            "is_deescalation": Noul(
                instructions="Does this news represent de-escalation of active market/geopolitical tension?"
            ),
            "is_risk_off": Noul(
                instructions="Does this news trigger risk-off flight to safety sentiment?"
            ),
            "is_risk_on": Noul(
                instructions="Does this news trigger risk-on optimism in financial markets?"
            ),
            "key_asset_classes": Choice(
                instructions="Which asset class is MOST directly impacted by this news?",
                criteria={
                    "forex": "Major/minor currency pair directly affected — central bank, employment, inflation data",
                    "commodity": "Oil, gold, or other commodity directly mentioned or impacted",
                    "index": "Equity index directly affected — tech earnings, sector rotation, risk appetite shift",
                    "cross_asset": "Multiple asset classes equally impacted — e.g. broad risk-off event",
                    "none": "No clear asset class directly impacted"
                }
            ),
        }

        try:
            # Handle both raw client or provider adapter
            if hasattr(client, "system_one"):
                resp = await client.system_one(state=state, questions=questions, timeout=15.0)
            elif hasattr(client, "_get_client"):
                raw_c = client._get_client()
                resp = await raw_c.system_one(state=state, questions=questions, timeout=15.0)
            else:
                return None

            impact_ans = resp.answers.get("impact")
            surprise_ans = resp.answers.get("surprise_magnitude")
            fresh_ans = resp.answers.get("is_fresh_catalyst")
            deesc_ans = resp.answers.get("is_deescalation")
            risk_off_ans = resp.answers.get("is_risk_off")
            risk_on_ans = resp.answers.get("is_risk_on")
            asset_class_ans = resp.answers.get("key_asset_classes")

            if not (impact_ans and surprise_ans):
                return None

            impact_val = impact_ans.choice
            impact_conf = getattr(impact_ans, "confidence", 1.0)
            surprise_val = surprise_ans.choice
            asset_class_val = getattr(asset_class_ans, "choice", "none")

            # Strict guardrails: if fetched > 90 mins ago, cannot be BREAKING
            if impact_val == "BREAKING" and t_sys is not None and t_sys > 90:
                impact_val = "HIGH"

            # Calendar prior enforcement
            if prior and prior.upper() == "HIGH" and impact_val in ("MEDIUM", "LOW", "NONE"):
                impact_val = "HIGH"
            elif prior and prior.upper() == "LOW" and impact_val in ("BREAKING", "HIGH"):
                impact_val = "MEDIUM"

            # Currencies extraction
            tags_str = extract_currency_tags(f"{item.title} {item.summary or ''}")
            currencies = [c for c in (tags_str.split(',') if tags_str else []) if c] or ['NON']

            # Sentiments compilation
            sentiments = []
            if fresh_ans and fresh_ans.noul > 0.65:
                sentiments.append("FRESH_CATALYST")
            if deesc_ans and deesc_ans.noul > 0.65:
                sentiments.append("DEESCALATION_RELIEF")
            if risk_off_ans and risk_off_ans.noul > 0.65:
                sentiments.append("RISK_OFF")
            if risk_on_ans and risk_on_ans.noul > 0.65:
                sentiments.append("RISK_ON")
            if not sentiments:
                sentiments.append("NEUTRAL")

            key_data = ""
            if surprise_val in ("moderate", "large"):
                # Extract numbers from title if available
                key_data = str(item.title)[:100]

            return {
                "index": idx,
                "news_id": getattr(item, "id", idx),
                "reasoning": f"TypeSafe Jev System One (impact={impact_val}, conf={impact_conf:.2f}, fresh={getattr(fresh_ans, 'noul', 0):.2f})",
                "impact": impact_val,
                "confidence": round(float(impact_conf), 2),
                "surprise_magnitude": surprise_val,
                "key_asset_class": asset_class_val,
                "currencies": currencies,
                "sentiments": sentiments,
                "key_data_point": key_data,
                "_is_jev": True,
            }
        except Exception as e:
            logger.debug(f"[JevNewsBatch] Item {idx} classification error: {e}")
            return None

    # Run all items in batch concurrently via asyncio.gather
    tasks = [_classify_item(j + 1, item) for j, item in enumerate(batch)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    classified_items = []
    for r in results:
        if isinstance(r, dict) and r.get("confidence", 0) >= min_confidence:
            classified_items.append(r)
        else:
            # If any item failed or has low confidence, return None to trigger safe LLM fallback
            logger.info(f"[JevNewsBatch] Low confidence or item error in Jev batch — falling back to LLM chain")
            return None

    return classified_items
