import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import FundamentalBrief
from analysis.providers.llm_factory import get_client_for_task

logger = logging.getLogger('TradingAgent.FundamentalVerifier')

VERIFIER_SCHEMA = {
    'type': 'object',
    'properties': {
        'internally_consistent': {'type': 'boolean'},
        'contradictions_found': {'type': 'array', 'items': {'type': 'string'}},
        'unjustified_confidence': {'type': 'boolean',
            'description': 'True if confidence seems too high given data quality/contradictions in the narrative'},
        'recommended_confidence_cap': {'type': 'number'},
        'counter_thesis_is_substantive': {'type': 'boolean',
            'description': 'True if the strongest_counter_thesis is substantive, specific, and falsifiable (not generic).'},
        'verdict': {'type': 'string', 'enum': ['pass', 'flag_for_review', 'reject']}
    },
    'required': ['internally_consistent', 'contradictions_found', 'unjustified_confidence',
                 'recommended_confidence_cap', 'counter_thesis_is_substantive', 'verdict']
}

FUNDAMENTAL_VERIFIER_SYSTEM_PROMPT = """Review the provided macro trading brief for INTERNAL LOGICAL CONSISTENCY ONLY.

Evaluation Checkpoints:
1. Does the narrative tone match currency_bias (e.g. narrative describes hawkish Fed/USD strength but USD bias is listed 'bearish' = contradiction)?
2. Is risk_sentiment consistent with the biases (e.g. risk-on but XAU bullish without idiosyncratic reason)?
3. Is overall confidence justified, or does the narrative describe significant uncertainty/contradiction while confidence is high (>0.7)?
4. Is the 'Strongest Counter Thesis' substantive, specific, and falsifiable? (e.g. 'If NFP > 250k...' is good. 'Markets can be unpredictable' is bad).

Do NOT judge whether the macro CALL is correct — check only internal logical consistency.
Respond in strictly valid JSON conforming to the schema."""

async def verify_fundamental_brief(session: AsyncSession, brief: FundamentalBrief, settings: dict) -> dict:
    """Independent, cheap re-read of a freshly submitted Stage 1 brief. Uses a DIFFERENT
    model family than the primary Stage 1 model to avoid self-consistency bias — checks
    ONLY internal logical consistency, never re-derives the macro call itself."""
    FAIL_CLOSED_CONFIDENCE_CAP = 0.6
    default = {
        'internally_consistent': True,
        'contradictions_found': [],
        'unjustified_confidence': True,
        'recommended_confidence_cap': min(brief.confidence or 0.7, FAIL_CLOSED_CONFIDENCE_CAP),
        'counter_thesis_is_substantive': True,
        'verdict': 'UNVERIFIED'
    }
    try:
        client = get_client_for_task('fundamental_verifier', settings)
        structured = json.loads(brief.structured_json) if brief.structured_json else {}
        user_prompt = f"""Narrative:
{structured.get('macro_narrative', '')[:2500]}

Currency Bias: {json.dumps(structured.get('currency_bias', {}))}
Currency Confidence: {json.dumps(structured.get('currency_confidence', {}))}
Risk Sentiment: {structured.get('risk_sentiment')}
Overall Confidence: {structured.get('confidence')}
Invalidation Conditions: {json.dumps(structured.get('invalidation_conditions', {}))}
Strongest Counter Thesis: {structured.get('strongest_counter_thesis')}"""

        from utils.typesafe.jev_primitives import build_fundamental_verifier_questions
        jev_q = build_fundamental_verifier_questions()

        result = await client.classify_json(
            prompt=user_prompt,
            system_prompt=FUNDAMENTAL_VERIFIER_SYSTEM_PROMPT,
            schema=VERIFIER_SCHEMA,
            jev_questions=jev_q,
            temperature=0.0
        )
        if not result or not isinstance(result, dict):
            return default

        contradictions = list(result.get('contradictions_found', []))
        # Map typed contradiction checks from Jev System One into contradictions_found list
        for ctype, cdesc in [
            ("contradiction_bias_vs_narrative", "Narrative tone contradicts currency bias"),
            ("contradiction_risk_vs_bias", "Risk sentiment contradicts currency bias"),
            ("contradiction_confidence_vs_uncertainty", "High confidence despite material uncertainty"),
            ("contradiction_data_vs_conclusion", "Cited data contradicts directional conclusion"),
        ]:
            c_val = result.get(ctype)
            if (isinstance(c_val, bool) and c_val) or (isinstance(c_val, (int, float)) and c_val > 0.60):
                if cdesc not in contradictions:
                    contradictions.append(cdesc)

        rec_cap = result.get('recommended_confidence_cap')
        if rec_cap is None or not isinstance(rec_cap, (int, float)):
            verdict_val = str(result.get('verdict', 'pass')).lower()
            if verdict_val == 'reject':
                rec_cap = 0.50
            elif verdict_val == 'flag_for_review':
                rec_cap = 0.65
            else:
                rec_cap = float(brief.confidence or 0.70)

        return {
            'internally_consistent': bool(result.get('internally_consistent', True)),
            'contradictions_found': contradictions,
            'unjustified_confidence': bool(result.get('unjustified_confidence', False)),
            'recommended_confidence_cap': float(rec_cap),
            'counter_thesis_is_substantive': bool(result.get('counter_thesis_is_substantive', True)),
            'verdict': str(result.get('verdict', 'pass'))
        }
    except Exception as e:
        logger.warning(f"Fundamental verifier error (fail-closed: confidence capped at {FAIL_CLOSED_CONFIDENCE_CAP}): {e}")
        return default
