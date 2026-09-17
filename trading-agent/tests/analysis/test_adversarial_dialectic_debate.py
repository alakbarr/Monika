import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from analysis.debate.bull_analyst import generate_bull_rebuttal
from analysis.debate.investment_judge import evaluate_debate


@pytest.mark.asyncio
async def test_generate_bull_rebuttal_success():
    mock_client = MagicMock()
    mock_client.default_temperature = 0.2
    mock_client.max_tokens = 4096
    
    mock_response = {
        "rebuttal_thesis": "Bear's liquidity sweep concern is mitigated by the 1.0850 H4 demand block holding above SL.",
        "rebuttal_strength": 8,
        "rebuttal_evidence": ["Demand zone buffer: 1.0850", "ATR_14: 0.0035 > SL buffer"],
        "conceded_points": ["Near-term 1.0920 resistance may stall initial momentum"]
    }
    mock_client.generate_content = AsyncMock(return_value=json.dumps(mock_response))
    
    symbol = "EURUSD"
    original_context = {"decision": "buy", "entry": 1.0875, "sl": 1.0830, "tp": 1.0960}
    fact_sheet = {"price": 1.0875, "atr": 0.0035}
    bull_claim = {"strength_score": 8, "evidence_cited": ["H4 bullish trend"]}
    bear_dissent = {"risk_severity": 7, "evidence_cited": ["Resistance at 1.0920"]}
    
    result = await generate_bull_rebuttal(
        mock_client, symbol, original_context, fact_sheet, bull_claim, bear_dissent
    )
    
    assert result["rebuttal_strength"] == 8
    assert len(result["rebuttal_evidence"]) >= 2
    assert "rebuttal_thesis" in result
    assert "conceded_points" in result
    assert not result.get("parse_error")


@pytest.mark.asyncio
async def test_generate_bull_rebuttal_fallback_on_error():
    mock_client = MagicMock()
    mock_client.default_temperature = 0.2
    mock_client.max_tokens = 4096
    mock_client.generate_content = AsyncMock(side_effect=Exception("API connection timeout"))
    
    symbol = "EURUSD"
    original_context = {"decision": "buy"}
    result = await generate_bull_rebuttal(
        mock_client, symbol, original_context, {}, {}, {"risk_severity": 8}
    )
    
    assert result["parse_error"] is True
    assert result["rebuttal_strength"] == 5
    assert len(result["rebuttal_evidence"]) >= 1


@pytest.mark.asyncio
async def test_evaluate_debate_with_strong_bull_rebuttal_mitigates_severity():
    mock_client = MagicMock()
    del mock_client.classify_json
    mock_client.max_tokens = 6144
    
    # Judge approves trade with adjusted risk
    mock_judge_response = {
        "final_decision": "buy",
        "reason": "Bull rebuttal proves demand zone buffer is sufficient despite bear overhead resistance.",
        "risk_multiplier": 0.75,
        "adjusted_entry": None,
        "adjusted_sl": None,
        "adjusted_tp": None
    }
    mock_client.generate_content = AsyncMock(return_value=json.dumps(mock_judge_response))
    
    symbol = "EURUSD"
    original_context = {"decision": "buy"}
    bull_claim = {"strength_score": 7, "evidence_cited": ["H4 trend"]}
    bear_dissent = {"risk_severity": 9, "evidence_cited": ["High risk level"]} # Severity 9 usually causes avoid
    bull_rebuttal = {"rebuttal_strength": 8, "rebuttal_evidence": ["Refuted with demand block"]} # Rebuttal strength 8 downgrades effective severity to 7
    
    verdict = await evaluate_debate(
        mock_client, symbol, original_context, bull_claim, bear_dissent, bull_rebuttal=bull_rebuttal
    )
    
    # Should not be forced to avoid because rebuttal mitigated severity
    assert verdict["final_decision"] == "buy"
    assert verdict["risk_multiplier"] == 0.75


@pytest.mark.asyncio
async def test_evaluate_debate_with_weak_rebuttal_enforces_avoid_on_high_severity():
    mock_client = MagicMock()
    del mock_client.classify_json
    mock_client.max_tokens = 6144
    
    # Model mistakenly returns buy with 0.20 risk multiplier despite severity 9
    mock_judge_response = {
        "final_decision": "buy",
        "reason": "Bear raised critical concern, bull cannot defend.",
        "risk_multiplier": 0.20,
        "adjusted_entry": None,
        "adjusted_sl": None,
        "adjusted_tp": None
    }
    mock_client.generate_content = AsyncMock(return_value=json.dumps(mock_judge_response))
    
    symbol = "EURUSD"
    original_context = {"decision": "buy"}
    bull_claim = {"strength_score": 5}
    bear_dissent = {"risk_severity": 9}
    bull_rebuttal = {"rebuttal_strength": 3} # Weak rebuttal, does not downgrade severity
    
    verdict = await evaluate_debate(
        mock_client, symbol, original_context, bull_claim, bear_dissent, bull_rebuttal=bull_rebuttal
    )
    
    # Effective severity remains 9, so risk <= 0.25 must be converted to avoid with multiplier 0.0
    assert verdict["final_decision"] == "avoid"
    assert verdict["risk_multiplier"] == 0.0
