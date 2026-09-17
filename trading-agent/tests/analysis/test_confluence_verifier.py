import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from database.models import AssetAnalysis
import json
from analysis.validators.confluence_verifier import verify_confluence

@pytest.fixture
def mock_session():
    return AsyncMock()

@pytest.mark.asyncio
async def test_verify_no_scorecard(mock_session):
    analysis = AssetAnalysis(symbol="BTCUSD", confluence_factors_json="[]")
    settings = {}
    with patch('analysis.validators.confluence_verifier.calculate_confluence', return_value={"computed_score": 0, "blocking_issues": []}):
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
    with patch('analysis.validators.confluence_verifier.calculate_confluence', return_value={"computed_score": 2, "blocking_issues": []}):
        result = await verify_confluence(mock_session, analysis, settings)
        assert result["verified"] is True
        assert analysis.confluence_score == 2

@pytest.mark.asyncio
async def test_verify_discrepancy(mock_session):
    analysis = AssetAnalysis(symbol="BTCUSD", decision="buy", confluence_score=5)
    factors = [
        {"category": "F1_D1_TREND_ALIGNED", "score": 1},
        {"category": "F2_H4_MOMENTUM_ALIGNED", "score": 1},
        {"category": "F3_KEY_LEVEL_BOUNCE", "score": 1},
    ]
    analysis.confluence_factors_json = json.dumps(factors)
    settings = {}
    with patch('analysis.validators.confluence_verifier.calculate_confluence', return_value={"computed_score": 1, "blocking_issues": []}):
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
    with patch('analysis.validators.confluence_verifier.calculate_confluence', return_value={"computed_score": 1, "blocking_issues": []}):
        result = await verify_confluence(mock_session, analysis, settings)
        assert result["verified"] is True

