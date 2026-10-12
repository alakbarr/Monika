import pytest
from unittest import mock
from datetime import datetime, timezone

from typesafe_sdk import SystemOneResponse, ChoiceAnswer, NoulAnswer, ScoreAnswer, Usage
from utils.typesafe.jev_primitives import (
    parse_jev_response_to_dict,
    build_fundamental_verifier_questions,
    build_news_classification_verify_questions,
    build_digest_consistency_questions,
    build_position_guard_questions,
    build_telegram_intent_questions,
    build_risk_gate_neutral_questions,
    build_exit_review_prescreen,
    build_scenario_branch_questions,
    build_adversarial_check_questions,
    build_shadow_check_questions,
    build_adjudication_questions,
    classify_news_batch_with_jev,
)


def test_all_new_question_builders():
    """Verify all newly created Jev question builders construct expected primitives."""
    fund_q = build_fundamental_verifier_questions()
    assert "internally_consistent" in fund_q
    assert "contradiction_bias_vs_narrative" in fund_q
    assert "contradiction_risk_vs_bias" in fund_q
    assert "contradiction_confidence_vs_uncertainty" in fund_q
    assert "contradiction_data_vs_conclusion" in fund_q
    assert "verdict" in fund_q
    assert "quality_score" in fund_q

    news_v_q = build_news_classification_verify_questions()
    assert "impact_correct" in news_v_q
    assert "corrected_impact" in news_v_q
    assert "currencies_relevant" in news_v_q
    assert "breaking_verdict" in news_v_q

    digest_q = build_digest_consistency_questions()
    assert "has_contradictions" in digest_q
    assert "contradiction_severity" in digest_q
    assert "digest_quality" in digest_q

    pos_guard_q = build_position_guard_questions("XAUUSD", "buy")
    assert "adverse_momentum" in pos_guard_q
    assert "sl_threat_level" in pos_guard_q
    assert "should_tighten_stop" in pos_guard_q

    tel_q = build_telegram_intent_questions()
    assert "intent" in tel_q
    assert "model_tier" in tel_q
    assert "is_urgent" in tel_q

    risk_neu_q = build_risk_gate_neutral_questions("EURUSD", "sell")
    assert "overall_approval" in risk_neu_q
    assert "risk_reward_balance" in risk_neu_q
    assert "timing_acceptable" in risk_neu_q

    exit_q = build_exit_review_prescreen("GBPUSD", "buy")
    assert "thesis_still_valid" in exit_q
    assert "exit_urgency" in exit_q

    scenario_q = build_scenario_branch_questions()
    assert "dominant_scenario" in scenario_q
    assert "scenario_conviction" in scenario_q

    adv_q = build_adversarial_check_questions("USDJPY")
    assert "approve" in adv_q
    assert "overall_quality" in adv_q
    assert "hard_block" in adv_q
    assert "primary_risk_category" in adv_q


def test_shadow_and_adjudication_updated_builders():
    """Verify shadow check and adjudication builders have both atomic and legacy keys."""
    shadow_q = build_shadow_check_questions()
    assert "is_internally_consistent" in shadow_q
    assert "cites_specific_numbers" in shadow_q
    assert "tone_matches_data" in shadow_q
    assert "rate_direction_consistent" in shadow_q
    assert "has_data_hallucination" in shadow_q

    adj_q = build_adjudication_questions()
    assert "adjudication_rule_correctly_applied" in adj_q
    assert "expected_outcome_per_rules" in adj_q
    assert "is_conditional_wait" in adj_q
    assert "verdict" in adj_q
    assert "mismatch_category" in adj_q
    assert "verdict_valid" in adj_q


def test_dynamic_agreement_pct_not_hardcoded():
    """Verify agreement_pct is computed dynamically from confidence distribution, not hardcoded 85.0."""
    resp = SystemOneResponse(
        model="jev-1.13.0",
        usage=Usage(input_tokens=100, output_tokens=0),
        answers={
            "bias_USD": ChoiceAnswer(choice="bullish", confidence=0.50, probabilities={"bullish": 0.50}),
            "bias_EUR": ChoiceAnswer(choice="bearish", confidence=0.40, probabilities={"bearish": 0.40}),
            "bias_GBP": ChoiceAnswer(choice="neutral", confidence=0.60, probabilities={"neutral": 0.60}),
        }
    )
    result = parse_jev_response_to_dict(resp)
    assert "currency_bias" in result
    assert result["currency_bias"]["USD"] == "bullish"
    # Average of (0.50 + 0.40 + 0.60) / 3 = 0.50 -> 50.0%
    assert result["agreement_pct"] == 50.0
    assert "USD" in result["flagged_currencies"]
    assert "EUR" in result["flagged_currencies"]
    assert "GBP" not in result["flagged_currencies"]


@pytest.mark.asyncio
async def test_classify_news_batch_with_key_asset_classes():
    """Verify news batch classifier extracts key_asset_class from parallel questions."""
    mock_item = mock.MagicMock()
    mock_item.id = 42
    mock_item.title = "Federal Reserve cuts interest rates unexpectedly"
    mock_item.summary = "Federal Open Market Committee moves target rate down 50bps."
    mock_item.fetched_at = datetime.now(timezone.utc)

    mock_client = mock.AsyncMock()
    mock_client.system_one.return_value = SystemOneResponse(
        model="jev-1.13.0",
        usage=Usage(input_tokens=80, output_tokens=0),
        answers={
            "impact": ChoiceAnswer(choice="BREAKING", confidence=0.95, probabilities={"BREAKING": 0.95}),
            "surprise_magnitude": ChoiceAnswer(choice="large", confidence=0.90, probabilities={"large": 0.90}),
            "is_fresh_catalyst": NoulAnswer(noul=0.92),
            "is_deescalation": NoulAnswer(noul=0.05),
            "is_risk_off": NoulAnswer(noul=0.10),
            "is_risk_on": NoulAnswer(noul=0.88),
            "key_asset_classes": ChoiceAnswer(choice="forex", confidence=0.92, probabilities={"forex": 0.92}),
        }
    )

    results = await classify_news_batch_with_jev(
        client=mock_client,
        batch=[mock_item],
        now_utc=datetime.now(timezone.utc)
    )

    assert results is not None
    assert len(results) == 1
    item_res = results[0]
    assert item_res["impact"] == "BREAKING"
    assert item_res["key_asset_class"] == "forex"
    assert "RISK_ON" in item_res["sentiments"]
    assert item_res["_is_jev"] is True


@pytest.mark.asyncio
async def test_position_guardian_jev_threat():
    """Verify PositionGuardian evaluate_position_threat_with_jev evaluates threat without errors."""
    from scheduler.position_guardian import PositionGuardian

    settings = {
        "llm": {
            "task_roles": {
                "jev_position_guard": {
                    "primary": "jev-latest",
                    "fallback_1": "gemini-3.5-flash-lite",
                }
            }
        }
    }
    guardian = PositionGuardian(settings=settings)

    mock_pos = mock.MagicMock()
    mock_pos.symbol = "XAUUSD"
    mock_pos.direction = "buy"
    mock_pos.entry_price = 2650.0
    mock_pos.sl = 2640.0
    mock_pos.tp = 2680.0
    mock_pos.volume = 0.1

    with mock.patch("analysis.providers.llm_factory.get_client_for_task") as mock_factory:
        mock_client = mock.AsyncMock()
        mock_client.classify_json.return_value = {
            "adverse_momentum": False,
            "sl_threat_level": 1,
            "should_tighten_stop": False,
        }
        mock_factory.return_value = mock_client

        threat = await guardian.evaluate_position_threat_with_jev(mock_pos, current_price=2655.0)
        assert threat.get("adverse_momentum") is False
        assert threat.get("sl_threat_level") == 1
        assert threat.get("should_tighten_stop") is False
