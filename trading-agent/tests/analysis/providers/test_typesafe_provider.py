"""
Unit tests for TypeSafeProvider and Jev System One decision engine.
Tests schema translation, choice/score/noul answers, confidence gating, and provider failover.
"""

import pytest
import unittest.mock as mock
from analysis.providers.typesafe_provider import TypeSafeProvider
from utils.typesafe.jev_primitives import (
    schema_to_jev_questions,
    parse_jev_response_to_dict,
    build_news_classification_questions,
    build_prescreen_questions,
    build_shadow_check_questions,
    build_adjudication_questions,
    build_realtime_news_questions,
)
from typesafe_sdk import SystemOneResponse, ChoiceAnswer, NoulAnswer, ScoreAnswer
from typesafe_sdk._core.response_types import Usage


@pytest.fixture
def dummy_provider():
    return TypeSafeProvider(
        model="jev-latest",
        api_key="mock_key",
        confidence_threshold=0.70
    )


def test_provider_initialization(dummy_provider):
    assert dummy_provider.model == "jev-latest"
    assert dummy_provider.provider_name == "typesafe"
    assert dummy_provider.confidence_threshold == 0.70
    assert dummy_provider.capabilities.supports_tool_choice is False
    assert dummy_provider.capabilities.supports_structured_output is True


@pytest.mark.asyncio
async def test_generate_raises_not_implemented(dummy_provider):
    with pytest.raises(NotImplementedError):
        await dummy_provider.generate("Say hello")


@pytest.mark.asyncio
async def test_run_chat_loop_raises_not_implemented(dummy_provider):
    with pytest.raises(NotImplementedError):
        await dummy_provider.run_chat_loop("sys", [], "user", [])


@pytest.mark.asyncio
async def test_run_tool_agent_raises_not_implemented(dummy_provider):
    with pytest.raises(NotImplementedError):
        await dummy_provider.run_tool_agent([], [], "sys")


def test_schema_to_jev_questions_conversion():
    schema = {
        "type": "object",
        "properties": {
            "is_valid": {"type": "boolean", "description": "Is signal valid?"},
            "impact": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"], "description": "Market impact"},
            "rating": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Opportunity score"},
            "direction": {"type": "string", "enum": ["YES", "NO"], "description": "Should buy?"},
        }
    }
    questions = schema_to_jev_questions(schema)
    assert "is_valid" in questions
    assert "impact" in questions
    assert "rating" in questions
    assert "direction" in questions


def test_currency_bias_expansion_and_reassembly():
    schema = {
        "type": "object",
        "properties": {
            "currency_bias": {"type": "object", "description": "Macro currency bias"}
        }
    }
    questions = schema_to_jev_questions(schema)
    assert "bias_USD" in questions
    assert "bias_EUR" in questions
    assert "bias_JPY" in questions

    mock_resp = SystemOneResponse(
        model="jev-1.13.0",
        usage=Usage(input_tokens=100, output_tokens=0),
        answers={
            "bias_USD": ChoiceAnswer(choice="bullish", confidence=0.85, probabilities={"bullish": 0.85, "bearish": 0.15}),
            "bias_EUR": ChoiceAnswer(choice="bearish", confidence=0.80, probabilities={"bearish": 0.80, "bullish": 0.20}),
            "bias_GBP": ChoiceAnswer(choice="neutral", confidence=0.75, probabilities={"neutral": 0.75}),
            "bias_JPY": ChoiceAnswer(choice="bullish", confidence=0.90, probabilities={"bullish": 0.90}),
            "bias_AUD": ChoiceAnswer(choice="neutral", confidence=0.70, probabilities={"neutral": 0.70}),
            "bias_XAU": ChoiceAnswer(choice="neutral", confidence=0.70, probabilities={"neutral": 0.70}),
        }
    )
    result = parse_jev_response_to_dict(mock_resp, schema=schema)
    assert "currency_bias" in result
    assert result["currency_bias"]["USD"] == "bullish"
    assert result["currency_bias"]["EUR"] == "bearish"
    assert result["currency_bias"]["JPY"] == "bullish"
    assert result["_confidence"] == 0.70


@pytest.mark.asyncio
async def test_classify_json_with_mocked_client(dummy_provider):
    mock_client = mock.AsyncMock()
    mock_resp = SystemOneResponse(
        model="jev-1.13.0",
        usage=Usage(input_tokens=150, output_tokens=0),
        answers={
            "action": ChoiceAnswer(choice="BUY", confidence=0.88, probabilities={"BUY": 0.88, "SELL": 0.12}),
            "is_risky": NoulAnswer(noul=0.15)
        }
    )
    mock_client.system_one.return_value = mock_resp
    dummy_provider._client = mock_client

    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["BUY", "SELL"]},
            "is_risky": {"type": "boolean"}
        }
    }

    result = await dummy_provider.classify_json(prompt="Market is strong", schema=schema)
    assert result is not None
    assert result["action"] == "BUY"
    assert result["is_risky"] is False  # 0.15 < 0.50 -> False
    assert result["_is_high_confidence"] is True
    assert result["_jev_model"] == "jev-1.13.0"


@pytest.mark.asyncio
async def test_classify_json_low_confidence_rejection(dummy_provider):
    mock_client = mock.AsyncMock()
    mock_resp = SystemOneResponse(
        model="jev-1.13.0",
        usage=Usage(input_tokens=150, output_tokens=0),
        answers={
            "action": ChoiceAnswer(choice="BUY", confidence=0.40, probabilities={"BUY": 0.55, "SELL": 0.45})
        }
    )
    mock_client.system_one.return_value = mock_resp
    dummy_provider._client = mock_client

    schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["BUY", "SELL"]}
        }
    }

    # Reject low confidence when requested -> triggers fallback to next model
    result = await dummy_provider.classify_json(
        prompt="Ambiguous market",
        schema=schema,
        min_confidence=0.70,
        reject_low_confidence=True
    )
    assert result is None


def test_question_builders():
    news_q = build_news_classification_questions()
    assert "impact" in news_q
    assert "urgency_score" in news_q
    assert "is_fresh_catalyst" in news_q
    assert "is_deescalation" in news_q

    prescreen_q = build_prescreen_questions("XAUUSD")
    assert "decision" in prescreen_q
    assert "opportunity_score" in prescreen_q

    shadow_q = build_shadow_check_questions()
    assert "is_internally_consistent" in shadow_q
    assert "has_data_hallucination" in shadow_q

    adjudication_q = build_adjudication_questions()
    assert "verdict_valid" in adjudication_q
    assert "direction_conviction" in adjudication_q

    realtime_q = build_realtime_news_questions(["XAUUSD", "EURUSD"])
    assert "market_sentiment" in realtime_q
    assert "threatens_positions" in realtime_q
    assert "requires_circuit_breaker" in realtime_q
