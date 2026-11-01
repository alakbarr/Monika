import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from monika.infrastructure.database.models import AssetAnalysis
import json
from monika.application.analysis.validators.confluence_verifier import verify_confluence


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.mark.asyncio
async def test_verify_no_scorecard(mock_session):
    analysis = AssetAnalysis(symbol="BTCUSD", confluence_factors_json="[]")
    settings = {}
    with patch(
        "monika.application.analysis.validators.confluence_verifier.calculate_confluence",
        return_value={"computed_score": 0, "blocking_issues": []},
    ):
        result = await verify_confluence(mock_session, analysis, settings)
        assert result["verified"] is True


@pytest.mark.asyncio
async def test_verify_all_ok(mock_session):
    analysis = AssetAnalysis(symbol="BTCUSD", decision="buy", confluence_score=2)
    factors = [
        {"category": "F1_D1_TREND_ALIGNED", "score": 1},
        {"category": "F2_H4_MOMENTUM_ALIGNED", "score": 1},
        {"category": "F3_KEY_LEVEL_BOUNCE", "score": 0},
    ]
    analysis.confluence_factors_json = json.dumps(factors)
    settings = {}
    with patch(
        "monika.application.analysis.validators.confluence_verifier.calculate_confluence",
        return_value={"computed_score": 2, "blocking_issues": []},
    ):
        result = await verify_confluence(mock_session, analysis, settings)
        assert result["verified"] is True
        assert analysis.confluence_score == 2


@pytest.mark.asyncio
async def test_verify_discrepancy(mock_session):
    analysis = AssetAnalysis(symbol="BTCUSD", decision="buy", confluence_score=7)
    factors = [
        {"category": "F1_D1_TREND_ALIGNED", "score": 1},
        {"category": "F2_H4_MOMENTUM_ALIGNED", "score": 1},
        {"category": "F3_KEY_LEVEL_BOUNCE", "score": 1},
    ]
    analysis.confluence_factors_json = json.dumps(factors)
    settings = {}
    with patch(
        "monika.application.analysis.validators.confluence_verifier.calculate_confluence",
        return_value={"computed_score": 1, "blocking_issues": []},
    ):
        result = await verify_confluence(mock_session, analysis, settings)
        assert result["verified"] is False
        assert any("discrepancy" in issue.lower() for issue in result["blocking_issues"])


@pytest.mark.asyncio
async def test_verify_discrepancy_tolerance_boundary(mock_session):
    # Discrepancy of exactly 3 (4 - 1 = 3) should be permitted under default tolerance 3
    analysis = AssetAnalysis(symbol="BTCUSD", decision="buy", confluence_score=4)
    factors = [
        {"category": "F1_D1_TREND_ALIGNED", "score": 1},
        {"category": "F2_H4_MOMENTUM_ALIGNED", "score": 1},
    ]
    analysis.confluence_factors_json = json.dumps(factors)
    settings = {}
    with patch(
        "monika.application.analysis.validators.confluence_verifier.calculate_confluence",
        return_value={"computed_score": 1, "blocking_issues": []},
    ):
        result = await verify_confluence(mock_session, analysis, settings)
        assert result["verified"] is True


def test_specialist_council_identifies_uncrowded_institutional_synergy():
    from monika.application.analysis.stages.per_asset.specialist_council import (
        SpecialistCouncil,
        compute_specialist_consensus_summary,
    )

    synergy = compute_specialist_consensus_summary({"technical": "bullish", "macro": "bullish", "sentiment": "neutral"})
    assert synergy["synergy_state"] == "uncrowded_institutional_synergy"
    assert synergy["consensus"] == "majority_agreement"
    assert synergy["majority_agreement"] is True
    assert synergy["unanimous_agreement"] is False
    assert synergy["dominant_bias"] == "bullish"
    assert "UNCROWDED_INSTITUTIONAL_SYNERGY" in synergy["formatted_summary"]

    crowded = compute_specialist_consensus_summary({"technical": "bearish", "macro": "bearish", "sentiment": "bearish"})
    assert crowded["synergy_state"] == "crowded_unanimous_exhaustion"
    assert crowded["consensus"] == "unanimous_agreement"
    assert crowded["unanimous_agreement"] is True
    assert "CROWDED_3_OF_3_CAUTION" in crowded["formatted_summary"]

    trap = SpecialistCouncil.summarize_consensus({"technical": "bullish", "macro": "bearish", "sentiment": "bullish"})
    assert trap["synergy_state"] == "crowded_tech_sent_trap_vs_macro"
    assert trap["consensus"] == "majority_agreement"
    assert "CROWDED_TECH_SENT_TRAP_VS_MACRO" in trap["formatted_summary"]

    conflict = SpecialistCouncil.summarize_consensus(
        {"technical": "bullish", "macro": "bearish", "sentiment": "neutral"}
    )
    assert conflict["synergy_state"] == "technical_macro_conflict"
    assert conflict["consensus"] == "split_conflict"


@pytest.mark.asyncio
async def test_confluence_calculator_awards_full_points_for_uncrowded_institutional_synergy(mock_session):
    from monika.application.analysis.calculators.confluence_calculator import calculate_confluence

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch(
        "monika.application.analysis.calculators.daily_range_calculator.compute_daily_range_context",
        AsyncMock(return_value={}),
    ):
        base_res = await calculate_confluence(
            mock_session,
            symbol="USDJPY",
            direction="buy",
            entry_price=150.0,
        )
        synergy_res = await calculate_confluence(
            mock_session,
            symbol="USDJPY",
            direction="buy",
            entry_price=150.0,
            specialist_biases={"technical": "bullish", "macro": "bullish", "sentiment": "neutral"},
        )
        unanimous_res = await calculate_confluence(
            mock_session,
            symbol="USDJPY",
            direction="buy",
            entry_price=150.0,
            specialist_biases={"technical": "bullish", "macro": "bullish", "sentiment": "bullish"},
        )
        trap_res = await calculate_confluence(
            mock_session,
            symbol="USDJPY",
            direction="buy",
            entry_price=150.0,
            specialist_biases={"technical": "bullish", "macro": "bearish", "sentiment": "bullish"},
        )

    assert synergy_res["computed_score"] == base_res["computed_score"] + 2
    assert unanimous_res["computed_score"] == base_res["computed_score"]
    assert trap_res["computed_score"] == base_res["computed_score"]
    assert any("Uncrowded Institutional Synergy" in f for f in synergy_res["factors"])
    assert any("crowded_unanimous_exhaustion (0 pts)" in f for f in unanimous_res["factors"])
    assert any("crowded_tech_sent_trap_vs_macro (0 pts)" in f for f in trap_res["factors"])
