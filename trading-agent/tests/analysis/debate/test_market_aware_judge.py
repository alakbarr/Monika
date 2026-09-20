import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from analysis.debate.investment_judge import evaluate_debate, resolve_regime_weights, REGIME_WEIGHT_MATRIX


def test_resolve_regime_weights_trending():
    weights = resolve_regime_weights({"market_regime": "trending_bull", "vix": 16.5})
    assert weights["detected_regime"] == "trending"
    assert weights["trend_thesis_weight"] == 0.65
    assert weights["counter_thesis_weight"] == 0.35
    assert weights["volatility_penalty"] == 0.0


def test_resolve_regime_weights_ranging():
    weights = resolve_regime_weights({"regime": "ranging_chop", "vix": 18.0})
    assert weights["detected_regime"] == "ranging"
    assert weights["trend_thesis_weight"] == 0.50
    assert weights["counter_thesis_weight"] == 0.50
    assert weights["volatility_penalty"] == 0.10


def test_resolve_regime_weights_volatile_via_vix():
    weights = resolve_regime_weights({"market_regime": "trending", "vix": 28.5})
    # VIX >= 25 elevates to volatile
    assert weights["detected_regime"] == "volatile"
    assert weights["trend_thesis_weight"] == 0.30
    assert weights["counter_thesis_weight"] == 0.70
    assert weights["volatility_penalty"] == 0.20


@pytest.mark.asyncio
async def test_evaluate_debate_in_volatile_regime_rejects_on_moderate_bear_severity():
    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(return_value={
        "final_decision": "buy",
        "reason": "Technical breakout has momentum",
        "risk_multiplier": 0.60,
        "adjusted_entry": None,
        "adjusted_sl": None,
        "adjusted_tp": None
    })
    
    # In volatile regime, bear_severity 7 triggers avoid veto
    verdict = await evaluate_debate(
        mock_client,
        symbol="XAUUSD",
        original_context={"decision": "buy", "market_regime": "volatile_shock", "vix": 31.0},
        bull_claim={"strength_score": 7},
        bear_dissent={"risk_severity": 7, "evidence_cited": ["VIX spike above 30"]},
        bull_rebuttal=None
    )
    
    assert verdict["final_decision"] == "avoid"
    assert verdict["risk_multiplier"] == 0.0
    assert verdict["regime_weights_used"]["detected_regime"] == "volatile"


@pytest.mark.asyncio
async def test_evaluate_debate_in_volatile_regime_applies_volatility_penalty():
    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(return_value={
        "final_decision": "buy",
        "reason": "Strong low-volatility counter trend or safe setup",
        "risk_multiplier": 0.80,
        "adjusted_entry": None,
        "adjusted_sl": None,
        "adjusted_tp": None
    })
    
    # Bear severity 4 (low) does not trigger veto, but volatility penalty (0.20) is deducted
    verdict = await evaluate_debate(
        mock_client,
        symbol="EURUSD",
        original_context={"decision": "buy", "volatility_regime": "volatile", "vix": 26.0},
        bull_claim={"strength_score": 8},
        bear_dissent={"risk_severity": 4},
        bull_rebuttal=None
    )
    
    assert verdict["final_decision"] == "buy"
    # 0.80 - 0.20 = 0.60
    assert abs(verdict["risk_multiplier"] - 0.60) < 1e-4
    assert verdict["regime_weights_used"]["detected_regime"] == "volatile"


@pytest.mark.asyncio
async def test_evaluate_debate_fallback_preserves_regime_weights():
    mock_client = MagicMock()
    mock_client.classify_json = AsyncMock(side_effect=RuntimeError("LLM API timeout"))
    
    verdict = await evaluate_debate(
        mock_client,
        symbol="GBPUSD",
        original_context={"decision": "sell", "market_regime": "trending"},
        bull_claim={"strength_score": 6},
        bear_dissent={"risk_severity": 5}
    )
    
    assert verdict["parse_error"] is True
    assert verdict["final_decision"] == "avoid"
    assert verdict["fail_closed_triggered"] is True
    assert verdict["regime_weights_used"]["detected_regime"] == "trending"


@pytest.mark.asyncio
async def test_evaluate_debate_generate_content_empty_response_fallback():
    mock_client = MagicMock(spec=["generate_content"])
    mock_client.generate_content = AsyncMock(return_value="")

    verdict = await evaluate_debate(
        mock_client,
        symbol="XAUUSD",
        original_context={"decision": "buy", "market_regime": "ranging"},
        bull_claim={"strength_score": 6},
        bear_dissent={"risk_severity": 4},
    )

    assert verdict["parse_error"] is True
    assert verdict["final_decision"] == "avoid"
    assert verdict["fail_closed_triggered"] is True
    assert "Empty or invalid response" in verdict["reason"]


@pytest.mark.asyncio
async def test_evaluate_debate_generate_content_success():
    mock_client = MagicMock(spec=["generate_content"])
    json_body = json.dumps({
        "final_decision": "buy",
        "reason": "Clear market structure with positive risk-reward",
        "risk_multiplier": 0.85,
    })
    mock_client.generate_content = AsyncMock(return_value=f"```json\n{json_body}\n```")

    verdict = await evaluate_debate(
        mock_client,
        symbol="EURUSD",
        original_context={"decision": "buy", "market_regime": "trending"},
        bull_claim={"strength_score": 8},
        bear_dissent={"risk_severity": 3},
    )

    assert verdict.get("parse_error") is not True
    assert verdict["final_decision"] == "buy"
    assert verdict["risk_multiplier"] == 0.85


@pytest.mark.asyncio
async def test_evaluate_debate_client_without_methods_fallback():
    # Client with neither classify_json nor generate_content
    class EmptyClient:
        pass

    verdict = await evaluate_debate(
        EmptyClient(),
        symbol="BTCUSD",
        original_context={"decision": "sell", "market_regime": "ranging"},
        bull_claim={"strength_score": 5},
        bear_dissent={"risk_severity": 6},
    )

    assert verdict["parse_error"] is True
    assert verdict["final_decision"] == "avoid"
    assert verdict["fail_closed_triggered"] is True
    assert "Empty or invalid response" in verdict["reason"]

