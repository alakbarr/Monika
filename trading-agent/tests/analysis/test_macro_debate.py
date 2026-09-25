import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.debate.macro_bull_analyst import run_bull_analyst, MACRO_BULL_SCHEMA
from analysis.debate.macro_bear_analyst import run_bear_analyst, MACRO_BEAR_SCHEMA
from analysis.debate.macro_judge import run_macro_judge, JUDGE_SCHEMA
from analysis.debate.macro_debate_validator import (
    validate_macro_judge_output,
    normalize_winner,
)


# =============================================================================
# Unit Tests: Normalization & Validation
# =============================================================================

def test_normalize_winner():
    assert normalize_winner("BULL") == "RISK_ON_USD_BEAR"
    assert normalize_winner("bull") == "RISK_ON_USD_BEAR"
    assert normalize_winner("RISK_ON") == "RISK_ON_USD_BEAR"
    assert normalize_winner("RISK_ON_USD_BEAR") == "RISK_ON_USD_BEAR"
    assert normalize_winner("BEAR") == "RISK_OFF_USD_BULL"
    assert normalize_winner("bear") == "RISK_OFF_USD_BULL"
    assert normalize_winner("RISK_OFF") == "RISK_OFF_USD_BULL"
    assert normalize_winner("RISK_OFF_USD_BULL") == "RISK_OFF_USD_BULL"
    assert normalize_winner("TIE") == "TIE"
    assert normalize_winner("UNKNOWN") == "TIE"
    assert normalize_winner("") == "TIE"


def test_validator_valid_risk_on():
    raw_judge = {
        "bull_arguments_score": 8,
        "bear_arguments_score": 4,
        "winner": "RISK_ON_USD_BEAR",
        "dxy_bias": "BEARISH",
        "risk_asset_bias": "BULLISH",
        "rationale": "Strong easing and low yields favor risk assets over dollar.",
        "escalation_required": False
    }
    validated = validate_macro_judge_output(raw_judge)
    assert validated["winner"] == "RISK_ON_USD_BEAR"
    assert validated["legacy_winner"] == "BULL"
    assert validated["dxy_bias"] == "BEARISH"
    assert validated["risk_asset_bias"] == "BULLISH"
    assert validated["bull_arguments_score"] == 8
    assert validated["bear_arguments_score"] == 4
    assert validated["internal_hallucination_detected"] is False
    assert validated["escalation_required"] is False


def test_validator_valid_risk_off():
    raw_judge = {
        "bull_arguments_score": 3,
        "bear_arguments_score": 9,
        "winner": "RISK_OFF_USD_BULL",
        "dxy_bias": "BULLISH",
        "risk_asset_bias": "BEARISH",
        "rationale": "Persistent inflation and hawkish Fed boost USD and pressure risk assets.",
        "escalation_required": False
    }
    validated = validate_macro_judge_output(raw_judge)
    assert validated["winner"] == "RISK_OFF_USD_BULL"
    assert validated["legacy_winner"] == "BEAR"
    assert validated["dxy_bias"] == "BULLISH"
    assert validated["risk_asset_bias"] == "BEARISH"
    assert validated["internal_hallucination_detected"] is False
    assert validated["escalation_required"] is False


def test_validator_detects_inversion_hallucination():
    # Hallucination: Winner is RISK_ON_USD_BEAR but DXY is declared BULLISH
    raw_judge = {
        "bull_arguments_score": 8,
        "bear_arguments_score": 4,
        "winner": "RISK_ON_USD_BEAR",
        "dxy_bias": "BULLISH",  # Inverted!
        "risk_asset_bias": "BULLISH",
        "rationale": "Hallucinated judge output",
        "escalation_required": False
    }
    validated = validate_macro_judge_output(raw_judge)
    assert validated["internal_hallucination_detected"] is True
    assert validated["escalation_required"] is True
    assert any("Inversion" in r for r in validated["hallucination_reasons"])


def test_validator_detects_score_mismatch():
    # Score mismatch: Winner is declared RISK_ON but bear score is higher
    raw_judge = {
        "bull_arguments_score": 3,
        "bear_arguments_score": 8,
        "winner": "RISK_ON_USD_BEAR",
        "dxy_bias": "BEARISH",
        "risk_asset_bias": "BULLISH",
        "rationale": "Scoring mismatch",
        "escalation_required": False
    }
    validated = validate_macro_judge_output(raw_judge)
    assert validated["internal_hallucination_detected"] is True
    assert validated["escalation_required"] is True
    assert any("score" in r.lower() for r in validated["hallucination_reasons"])


def test_validator_tight_score_triggers_escalation():
    # Decisive 1-point edge (7 vs 6) should be respected without forcing escalation
    raw_judge_edge = {
        "bull_arguments_score": 7,
        "bear_arguments_score": 6,
        "winner": "RISK_ON_USD_BEAR",
        "dxy_bias": "BEARISH",
        "risk_asset_bias": "BULLISH",
        "rationale": "Bull has valid edge",
        "escalation_required": False
    }
    validated_edge = validate_macro_judge_output(raw_judge_edge)
    assert validated_edge["internal_hallucination_detected"] is False
    assert validated_edge["escalation_required"] is False

    # Exact tie (7 vs 7 or canonical winner TIE) must trigger escalation
    raw_judge_tie = {
        "bull_arguments_score": 7,
        "bear_arguments_score": 7,
        "winner": "TIE",
        "dxy_bias": "NEUTRAL",
        "risk_asset_bias": "NEUTRAL",
        "rationale": "True tie",
        "escalation_required": False
    }
    validated_tie = validate_macro_judge_output(raw_judge_tie)
    assert validated_tie["escalation_required"] is True


# =============================================================================
# Async Analyst & Judge Unit Tests
# =============================================================================

@pytest.mark.asyncio
async def test_run_bull_analyst_success():
    mock_client = AsyncMock()
    mock_client.classify_json.return_value = {
        "bull_thesis": "Liquidity is expanding and yields are dropping.",
        "strength_score": 8,
        "evidence_cited": ["10Y Yield=4.05%", "FedWatch=82% cut"],
        "primary_catalysts": ["Dovish pivot", "Global disinflation"]
    }
    with patch("analysis.debate.macro_bull_analyst.get_client_for_task", return_value=mock_client):
        res = await run_bull_analyst("Test context", {})
        assert res["strength_score"] == 8
        assert len(res["evidence_cited"]) == 2
        assert "bull_thesis" in res


@pytest.mark.asyncio
async def test_run_bull_analyst_fallback():
    mock_client = AsyncMock()
    mock_client.classify_json.side_effect = Exception("Schema parse failed")
    mock_client.generate.return_value = "Fallback raw text thesis."
    with patch("analysis.debate.macro_bull_analyst.get_client_for_task", return_value=mock_client):
        res = await run_bull_analyst("Test context", {})
        assert res["strength_score"] == 5
        assert "Fallback raw text thesis" in res["bull_thesis"]


@pytest.mark.asyncio
async def test_run_bear_analyst_success():
    mock_client = AsyncMock()
    mock_client.classify_json.return_value = {
        "bear_thesis": "Inflation is sticky and yields are surging.",
        "strength_score": 9,
        "evidence_cited": ["10Y Yield=4.50%", "VIX=26.0"],
        "primary_risks": ["Hawkish surprise", "Liquidity shock"]
    }
    with patch("analysis.debate.macro_bear_analyst.get_client_for_task", return_value=mock_client):
        res = await run_bear_analyst("Test context", {})
        assert res["strength_score"] == 9
        assert len(res["evidence_cited"]) == 2
        assert "bear_thesis" in res


@pytest.mark.asyncio
async def test_run_macro_judge_success():
    mock_client = AsyncMock()
    mock_client.classify_json.return_value = {
        "bull_arguments_score": 8,
        "bear_arguments_score": 4,
        "winner": "RISK_ON_USD_BEAR",
        "dxy_bias": "BEARISH",
        "risk_asset_bias": "BULLISH",
        "rationale": "Clear macro divergence favors risk assets.",
        "escalation_required": False
    }
    with patch("analysis.debate.macro_judge.get_client_for_task", return_value=mock_client):
        res = await run_macro_judge({"bull_thesis": "..."}, {"bear_thesis": "..."}, "Context", {})
        assert res["winner"] == "RISK_ON_USD_BEAR"
        assert res["dxy_bias"] == "BEARISH"
        assert res["risk_asset_bias"] == "BULLISH"


# =============================================================================
# Integration Test: fundamental_stage._run_macro_debate
# =============================================================================

@pytest.mark.asyncio
async def test_run_macro_debate_in_fundamental_stage():
    from analysis.stages.fundamental_stage import FundamentalStage
    from database.models import FundamentalBrief
    import datetime

    mock_session = AsyncMock()
    settings = {
        "agent_architecture": {
            "enable_debate": True
        }
    }
    stage = FundamentalStage(settings=settings)

    brief = FundamentalBrief(
        id=1,
        generated_at=datetime.datetime.now(datetime.timezone.utc),
        confidence=0.8,
        content_markdown="Macro context brief",
        structured_json=json.dumps({
            "currency_bias": {"USD": "bearish", "EUR": "bullish"},
            "macro_narrative": "Initial narrative"
        })
    )

    mock_bull_res = {
        "bull_thesis": "Strong risk on thesis",
        "strength_score": 8,
        "evidence_cited": ["10Y=4.05%", "VIX=13"],
        "primary_catalysts": ["Easing"]
    }
    mock_bear_res = {
        "bear_thesis": "Weak risk off thesis",
        "strength_score": 4,
        "evidence_cited": ["CPI sticky"],
        "primary_risks": ["Sticky inflation"]
    }
    mock_judge_res = {
        "bull_arguments_score": 8,
        "bear_arguments_score": 4,
        "winner": "RISK_ON_USD_BEAR",
        "dxy_bias": "BEARISH",
        "risk_asset_bias": "BULLISH",
        "rationale": "Risk on clearly prevails.",
        "escalation_required": False
    }

    with patch("analysis.debate.macro_bull_analyst.run_bull_analyst", return_value=mock_bull_res), \
         patch("analysis.debate.macro_bear_analyst.run_bear_analyst", return_value=mock_bear_res), \
         patch("analysis.debate.macro_judge.run_macro_judge", return_value=mock_judge_res):
        
        outcome = await stage._run_macro_debate(mock_session, brief)

        assert outcome["ran"] is True
        assert outcome["winner"] == "RISK_ON_USD_BEAR"
        assert outcome["legacy_winner"] == "BULL"
        assert outcome["dxy_bias"] == "BEARISH"
        assert outcome["risk_asset_bias"] == "BULLISH"
        assert outcome["escalation_required"] is False
        assert outcome["contradicts_usd_bias"] is False

        # Verify structured_json persistence
        saved_data = json.loads(brief.structured_json)
        assert saved_data["debate_winner"] == "RISK_ON_USD_BEAR"
        assert saved_data["debate_winner_legacy"] == "BULL"
        assert saved_data["debate_bull_score"] == 8
        assert saved_data["debate_bear_score"] == 4
        assert saved_data["dxy_bias_from_judge"] == "BEARISH"
        assert saved_data["risk_asset_bias_from_judge"] == "BULLISH"
        assert saved_data["debate_hallucination_detected"] is False
