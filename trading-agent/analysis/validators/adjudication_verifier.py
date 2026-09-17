import json
import logging
from typing import Optional
from analysis.providers.llm_factory import get_client_for_task

logger = logging.getLogger('TradingAgent.AdjudicationVerifier')

ADJUDICATION_VERIFY_SCHEMA = {
    'type': 'object',
    'properties': {
        'adjudication_rule_correctly_applied': {'type': 'boolean'},
        'expected_outcome_per_rules': {'type': 'string', 'enum': ['buy', 'sell', 'wait', 'avoid', 'ambiguous']},
        'is_conditional_wait': {'type': 'boolean'},
        'mismatch_explanation': {'type': 'string'},
        'verdict': {'type': 'string', 'enum': ['CONFIRM', 'FLAG_FOR_REVIEW', 'CONTRADICTS_OWN_FRAMEWORK']},
    },
    'required': ['adjudication_rule_correctly_applied', 'expected_outcome_per_rules', 'verdict'],
}

ADJUDICATION_SYSTEM_PROMPT = """Synthesis Adjudication Framework Rules & Execution Principles:

1. DIRECTIONAL SYNTHESIS VS EXECUTION TIMING:
   - When specialists are fully aligned (e.g. ALL BULLISH):
     * Directional Bias is STRICTLY BULLISH.
     * An immediate BUY is expected IF price is in a valid entry zone AND confluence >= threshold.
     * A 'WAIT' decision is COMPLETELY VALID ('CONFIRM') if the rationale explains that price is overextended, waiting for a pullback/retest to key support/OB, confluence < threshold, or a risk gate applies.
     * A true contradiction ('CONTRADICTS_OWN_FRAMEWORK') occurs ONLY IF the decision is SELL, or if WAIT is given with an unmotivated bearish thesis contradicting the specialists.
   - When specialists are fully aligned (e.g. ALL BEARISH):
     * Directional Bias is STRICTLY BEARISH.
     * An immediate SELL is expected IF price is in a valid entry zone AND confluence >= threshold.
     * A 'WAIT' decision is COMPLETELY VALID ('CONFIRM') if the rationale explains that price is overextended, waiting for a retracement/retest to key resistance/OB, confluence < threshold, or a risk gate applies.
     * A true contradiction ('CONTRADICTS_OWN_FRAMEWORK') occurs ONLY IF the decision is BUY, or if WAIT is given with an unmotivated bullish thesis contradicting the specialists.

2. CONFLICT RESOLUTION & GATES:
   - IF Technical=BULLISH AND Macro=BEARISH -> WAIT unless technical evidence is strong (ADX>30, clear BOS) and Macro Trust < 0.8.
   - IF Technical=BEARISH AND Macro=BULLISH -> WAIT unless technical evidence is strong and Macro Trust < 0.8.
   - IF Confluence Score < Threshold or Risk Gate active -> 'WAIT' is mandatory and MUST be CONFIRMED.
   - IF all NEUTRAL/MIXED -> 'WAIT' is mandatory and MUST be CONFIRMED.
   - IF any non-WAIT bias is supported by a specialist with trust_weight < 0.4 -> Downgrade decision or WAIT.

Evaluation Task:
- Check if the final decision respects the directional consensus and execution constraints above.
- If final decision is 'wait' because of entry timing, pullback, threshold, or risk gate while respecting directional bias, set verdict='CONFIRM' and is_conditional_wait=true.
- Only return 'CONTRADICTS_OWN_FRAMEWORK' if there is a true directional conflict (e.g., BUY when Bearish, SELL when Bullish, or unexplained refusal to align).
- Respond in valid JSON adhering to the provided schema."""

async def verify_adjudication(settings: dict, symbol: str, specialist_biases: dict,
                                specialist_confidence: dict, final_decision: str, rationale: str,
                                specialist_trust_weights: Optional[dict] = None,
                                confluence_score: Optional[int] = None,
                                effective_threshold: Optional[int] = None,
                                reeval_trigger: Optional[dict] = None) -> dict:
    """
    Verifikasi independen: apakah keputusan akhir Stage 2 primary benar-benar
    konsisten dengan Synthesis Adjudication Framework yang seharusnya diterapkan,
    membedakan antara Directional Bias vs Execution Timing (misal: conditional WAIT for pullback).
    """
    client = get_client_for_task('stage2_adjudicator', settings)
    
    trust_str = f"Specialist Trust Weights: {json.dumps(specialist_trust_weights)}" if specialist_trust_weights else ""
    context_extras = []
    if confluence_score is not None:
        context_extras.append(f"Confluence Score: {confluence_score}")
    if effective_threshold is not None:
        context_extras.append(f"Effective Confluence Threshold: {effective_threshold}")
    if reeval_trigger:
        context_extras.append(f"Re-evaluation Trigger: {json.dumps(reeval_trigger)}")
    extras_str = " | ".join(context_extras) if context_extras else ""
    
    user_prompt = f"""Specialist biases for {symbol}: {json.dumps(specialist_biases)}
Specialist confidence: {json.dumps(specialist_confidence)}
{trust_str}
{extras_str}

Final decision: {final_decision}
Rationale: {rationale[:1500]}"""

    try:
        result = await client.classify_json(
            prompt=user_prompt,
            system_prompt=ADJUDICATION_SYSTEM_PROMPT,
            schema=ADJUDICATION_VERIFY_SCHEMA,
            temperature=0.0
        )
        if not result or not isinstance(result, dict):
            return {'verdict': 'UNVERIFIED', 'adjudication_rule_correctly_applied': None, 'expected_outcome_per_rules': final_decision, 'mismatch_explanation': 'Empty response from verifier model'}
        return {
            'verdict': str(result.get('verdict', 'CONFIRM')),
            'adjudication_rule_correctly_applied': bool(result.get('adjudication_rule_correctly_applied', True)),
            'is_conditional_wait': bool(result.get('is_conditional_wait', False)),
            'expected_outcome_per_rules': str(result.get('expected_outcome_per_rules', final_decision)),
            'mismatch_explanation': str(result.get('mismatch_explanation', ''))
        }
    except Exception as e:
        logger.warning(f'[AdjudicationVerifier] failed (non-fatal, unverified): {e}')
        return {'verdict': 'UNVERIFIED', 'adjudication_rule_correctly_applied': None, 'expected_outcome_per_rules': final_decision, 'mismatch_explanation': str(e)}
