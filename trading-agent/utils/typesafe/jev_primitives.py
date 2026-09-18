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
            result["agreement_pct"] = 85.0
        if "flagged_currencies" not in result:
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
    """
    return {
        "is_internally_consistent": Noul(
            instructions="Is the fundamental analysis free of contradictory statements between macro assumptions and conclusions?"
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
    """
    return {
        "verdict_valid": Noul(
            instructions="Does the debate adjudication appropriately synthesize the specialist arguments without ignoring critical bearish risk factors?"
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
            instructions="Rate the proposed risk-reward viability and trade safety",
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

            if not (impact_ans and surprise_ans):
                return None

            impact_val = impact_ans.choice
            impact_conf = getattr(impact_ans, "confidence", 1.0)
            surprise_val = surprise_ans.choice

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
