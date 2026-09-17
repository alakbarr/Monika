import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from analysis.debate.aggressive_risk_llm import analyze_risk_aggressive_llm
from analysis.debate.conservative_risk_llm import analyze_risk_conservative_llm
from analysis.debate.neutral_risk_llm import analyze_risk_neutral_llm
from analysis.debate.portfolio_manager import make_portfolio_decision


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.generate_content = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_aggressive_risk_llm_success_json_str(mock_client):
    mock_payload = {
        "risk_profile_assessment": "Setup is solid, no structural flaw",
        "recommended_multiplier": 1.25,
        "veto_trade": False
    }
    mock_client.generate_content.return_value = json.dumps(mock_payload)
    
    result = await analyze_risk_aggressive_llm(mock_client, "EURUSD", {"confluence_score": 9})
    assert isinstance(result, dict)
    assert result["veto_trade"] is False
    assert result["recommended_multiplier"] == 1.25
    assert "solid" in result["risk_profile_assessment"]


@pytest.mark.asyncio
async def test_aggressive_risk_llm_success_dict(mock_client):
    mock_payload = {
        "risk_profile_assessment": "Confluence too low (<5)",
        "recommended_multiplier": 0.0,
        "veto_trade": True
    }
    mock_client.generate_content.return_value = mock_payload
    
    result = await analyze_risk_aggressive_llm(mock_client, "BTCUSD", {"confluence_score": 3})
    assert isinstance(result, dict)
    assert result["veto_trade"] is True
    assert result["recommended_multiplier"] == 0.0


@pytest.mark.asyncio
async def test_aggressive_risk_llm_empty_response_fallback(mock_client):
    mock_client.generate_content.return_value = None
    
    result = await analyze_risk_aggressive_llm(mock_client, "GBPUSD", {})
    assert isinstance(result, dict)
    assert result["veto_trade"] is False
    assert result["recommended_multiplier"] == 1.0
    assert result["risk_profile_assessment"] == "Fallback error"


@pytest.mark.asyncio
async def test_aggressive_risk_llm_invalid_format_fallback(mock_client):
    mock_client.generate_content.return_value = "invalid { not json"
    
    result = await analyze_risk_aggressive_llm(mock_client, "GBPUSD", {})
    assert isinstance(result, dict)
    assert result["veto_trade"] is False
    assert result["recommended_multiplier"] == 1.0
    assert result["risk_profile_assessment"] == "Fallback error"


@pytest.mark.asyncio
async def test_conservative_risk_llm_success(mock_client):
    mock_payload = {
        "risk_profile_assessment": "Rule 1 triggered: daily_pnl_pct <= -1.5%",
        "recommended_multiplier": 0.0,
        "veto_trade": True
    }
    mock_client.generate_content.return_value = json.dumps(mock_payload)
    
    result = await analyze_risk_conservative_llm(mock_client, "XAUUSD", {"actual_risk_state": {"daily_pnl_pct": -2.0}})
    assert isinstance(result, dict)
    assert result["veto_trade"] is True
    assert result["recommended_multiplier"] == 0.0


@pytest.mark.asyncio
async def test_conservative_risk_llm_fallback_on_exception(mock_client):
    mock_client.generate_content.side_effect = RuntimeError("API timeout")
    
    result = await analyze_risk_conservative_llm(mock_client, "XAUUSD", {})
    assert isinstance(result, dict)
    assert result["veto_trade"] is False
    assert result["recommended_multiplier"] == 0.5
    assert result["risk_profile_assessment"] == "Fallback error"


@pytest.mark.asyncio
async def test_neutral_risk_llm_success(mock_client):
    mock_payload = {
        "risk_profile_assessment": "Multiplier: 1.0 - 0.15*1 = 0.85",
        "recommended_multiplier": 0.85,
        "veto_trade": False
    }
    mock_client.generate_content.return_value = json.dumps(mock_payload)
    
    result = await analyze_risk_neutral_llm(mock_client, "USDJPY", {})
    assert isinstance(result, dict)
    assert result["veto_trade"] is False
    assert result["recommended_multiplier"] == 0.85


@pytest.mark.asyncio
async def test_neutral_risk_llm_empty_fallback(mock_client):
    mock_client.generate_content.return_value = ""
    
    result = await analyze_risk_neutral_llm(mock_client, "USDJPY", {})
    assert isinstance(result, dict)
    assert result["veto_trade"] is False
    assert result["recommended_multiplier"] == 1.0
    assert result["risk_profile_assessment"] == "Fallback error"


@pytest.mark.asyncio
async def test_portfolio_manager_success(mock_client):
    mock_payload = {
        "approval": True,
        "recommended_risk_multiplier": 0.8,
        "reason": "Portfolio state healthy, all criteria satisfied"
    }
    mock_client.generate_content.return_value = json.dumps(mock_payload)
    
    result = await make_portfolio_decision(mock_client, "EURUSD", {}, {"portfolio_heat_pct": 1.5})
    assert isinstance(result, dict)
    assert result["approval"] is True
    assert result["recommended_risk_multiplier"] == 0.8
    assert "healthy" in result["reason"]


@pytest.mark.asyncio
async def test_portfolio_manager_rejection(mock_client):
    mock_payload = {
        "approval": False,
        "recommended_risk_multiplier": 0.0,
        "reason": "Portfolio heat exceeds 4% limit"
    }
    mock_client.generate_content.return_value = mock_payload
    
    result = await make_portfolio_decision(mock_client, "EURUSD", {}, {"portfolio_heat_pct": 4.5})
    assert isinstance(result, dict)
    assert result["approval"] is False
    assert result["recommended_risk_multiplier"] == 0.0


@pytest.mark.asyncio
async def test_portfolio_manager_empty_response_fallback(mock_client):
    mock_client.generate_content.return_value = None
    
    result = await make_portfolio_decision(mock_client, "EURUSD", {}, {})
    assert isinstance(result, dict)
    assert result["approval"] is True
    assert result["recommended_risk_multiplier"] == 0.5
    assert result.get("parse_error") is True
    assert "Fallback - Parse Error" in result["reason"]


@pytest.mark.asyncio
async def test_portfolio_manager_invalid_json_fallback(mock_client):
    mock_client.generate_content.return_value = "Non-json string content"
    
    result = await make_portfolio_decision(mock_client, "EURUSD", {}, {})
    assert isinstance(result, dict)
    assert result["approval"] is True
    assert result["recommended_risk_multiplier"] == 0.5
    assert result.get("parse_error") is True
