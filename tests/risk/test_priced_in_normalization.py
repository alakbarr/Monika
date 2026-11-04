import pytest
from monika.application.analysis.schemas.sub_models import PricedInAssessment
from monika.application.analysis.schemas.analysis_schemas import SubmitAssetAnalysisSchema
from monika.core.risk.quant_scorecard import evaluate_analysis_scorecard


def test_priced_in_percentage_scale_normalization():
    # An LLM returning 40% (meaning 4/10 priced-in, NOT fully priced-in)
    # Tier 1: Schema validator must normalize 40 -> 4, not clamp to 10
    pi_int = PricedInAssessment(dominant_driver="Fed cuts", priced_in_score=40, sell_the_news_risk="low")
    assert pi_int.priced_in_score == 4, f"Expected 40 to be normalized to 4, got {pi_int.priced_in_score}"

    pi_str = PricedInAssessment(dominant_driver="Fed cuts", priced_in_score="40%", sell_the_news_risk="low")
    assert pi_str.priced_in_score == 4, f"Expected '40%' to be normalized to 4, got {pi_str.priced_in_score}"

    pi_float = PricedInAssessment(dominant_driver="Fed cuts", priced_in_score=35.0, sell_the_news_risk="low")
    assert pi_float.priced_in_score == 4, f"Expected 35.0 to be normalized to 4, got {pi_float.priced_in_score}"

    # Standard 1-10 scale should remain unaffected
    pi_normal = PricedInAssessment(dominant_driver="Fed cuts", priced_in_score=6, sell_the_news_risk="low")
    assert pi_normal.priced_in_score == 6

    # Tier 2: SubmitAssetAnalysisSchema normalization
    analysis = SubmitAssetAnalysisSchema(
        symbol="EURUSD",
        decision="BUY",
        confidence=0.85,
        confluence_score=12,
        priced_in_score=50,  # 50% -> should normalize to 5
        entry_price=1.0850,
        stop_loss=1.0820,
        take_profit=1.0920,
        invalidation_price=1.0815,
        invalidation_direction="below",
        thesis="Bullish breakout",
        rationale="Strong technical breakout above 1.0850 with macro tailwinds",
    )
    assert analysis.priced_in_score == 5

    # Tier 3: RiskGate evaluate_analysis_scorecard must accept normalized score
    passed, reason = evaluate_analysis_scorecard(
        decision_source="llm",
        quant_scorecard=None,
        confluence_score=analysis.confluence_score,
        priced_in_score=analysis.priced_in_score,
        min_confidence=0.6,
        min_rr_ratio=1.5,
        min_confluence=8,
    )
    assert passed is True, f"Expected trade with priced_in_score=5 to pass, got rejected with: {reason}"
