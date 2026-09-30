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


@pytest.mark.asyncio
async def test_typesafe_provider_system_one_passthrough(dummy_provider):
    mock_client = mock.AsyncMock()
    mock_resp = mock.MagicMock()
    mock_client.system_one.return_value = mock_resp
    dummy_provider._client = mock_client

    res = await dummy_provider.system_one(state={"test": 1}, questions={"q": 1}, timeout=10.0)
    assert res is mock_resp
    mock_client.system_one.assert_awaited_once_with(
        state={"test": 1},
        questions={"q": 1},
        model="jev-latest",
        timeout=10.0
    )


@pytest.mark.asyncio
async def test_typesafe_provider_classify_json_rejects_array_schema(dummy_provider):
    mock_client = mock.AsyncMock()
    dummy_provider._client = mock_client

    array_schema = {
        "type": "array",
        "items": {"type": "object", "properties": {"impact": {"type": "string"}}}
    }
    result = await dummy_provider.classify_json(prompt="Batch of news", schema=array_schema)
    assert result is None
    mock_client.system_one.assert_not_called()


@pytest.mark.asyncio
async def test_classify_news_batch_with_jev_supports_fallback_wrapper():
    from utils.typesafe.jev_primitives import classify_news_batch_with_jev
    from datetime import datetime, timezone

    class MockItem:
        def __init__(self, id, title, summary):
            self.id = id
            self.title = title
            self.summary = summary
            self.fetched_at = datetime.now(timezone.utc)

    class MockAnswer:
        def __init__(self, choice, conf=0.9):
            self.choice = choice
            self.confidence = conf
            self.noul = 0.8

    class MockResp:
        answers = {
            "impact": MockAnswer("HIGH", 0.95),
            "surprise_magnitude": MockAnswer("large", 0.90),
            "is_fresh_catalyst": MockAnswer("yes", 0.85),
            "is_deescalation": MockAnswer("no", 0.1),
            "is_risk_off": MockAnswer("yes", 0.8),
            "is_risk_on": MockAnswer("no", 0.1),
            "key_asset_classes": MockAnswer("forex", 0.9),
        }

    class MockRawClient:
        async def system_one(self, state, questions, timeout=15.0):
            return MockResp()

    # Emulate FallbackClientWrapper
    class MockFallbackWrapper:
        def _get_client(self, slot_name="primary"):
            return MockRawClient()

    wrapper = MockFallbackWrapper()
    items = [MockItem(101, "US CPI soars 4.5% vs 3.2% exp", "Inflation surprised high")]
    res = await classify_news_batch_with_jev(
        client=wrapper,
        batch=items,
        now_utc=datetime.now(timezone.utc)
    )
    assert res is not None
    assert len(res) == 1
    assert res[0]["news_id"] == 101
    assert res[0]["impact"] == "HIGH"
    assert res[0]["_is_jev"] is True
    assert "4.5% vs 3.2% exp" in res[0]["key_data_point"]


@pytest.mark.asyncio
async def test_jev_option_c_asset_bias_and_sentiments():
    """Verify Option C dynamic probing extracts directional biases, CB stance, and inflation tags."""
    from utils.typesafe.jev_primitives import classify_news_batch_with_jev
    from datetime import datetime, timezone

    class MockItem:
        def __init__(self, id, title, summary):
            self.id = id
            self.title = title
            self.summary = summary
            self.fetched_at = datetime.now(timezone.utc)

    class MockAnswer:
        def __init__(self, choice, conf=0.9):
            self.choice = choice
            self.confidence = conf
            self.noul = 0.85

    class MockResp:
        def __init__(self, answers):
            self.answers = answers

    class MockClient:
        async def system_one(self, state, questions, timeout=15.0):
            title = state.get("title", "")
            answers = {
                "impact": MockAnswer("HIGH", 0.92),
                "surprise_magnitude": MockAnswer("large", 0.90),
                "cb_stance": MockAnswer("hawkish", 0.88),
                "inflation_impact": MockAnswer("inflationary", 0.85),
                "is_geopolitical_risk": MockAnswer("no", 0.1),
                "is_fresh_catalyst": MockAnswer("yes", 0.88),
                "is_deescalation": MockAnswer("no", 0.1),
                "is_risk_off": MockAnswer("yes", 0.80),
                "is_risk_on": MockAnswer("no", 0.1),
                "key_asset_classes": MockAnswer("forex", 0.90),
            }
            # Dynamic asset bias answers if asked
            for q in questions:
                if q.startswith("bias_"):
                    asset = q.replace("bias_", "")
                    if asset == "USD":
                        answers[q] = MockAnswer("bullish", 0.90)
                    elif asset == "EUR":
                        answers[q] = MockAnswer("bearish", 0.85)
                    elif asset in ("XAU", "XTI", "BTC"):
                        answers[q] = MockAnswer("bullish", 0.80)
            return MockResp(answers)

    client = MockClient()
    items = [
        MockItem(1, "US CPI prints actual 3.8% vs forecast 3.1% (EUR/USD plunges)", "Strong dollar, ECB lags"),
        MockItem(2, "Gold and Bitcoin rally as oil supplies tighten", "WTI crude jumps, XAU surges, BTC hits high"),
    ]

    res = await classify_news_batch_with_jev(
        client=client,
        batch=items,
        now_utc=datetime.now(timezone.utc)
    )

    assert res is not None
    assert len(res) == 2

    # Item 1: USD + EUR directional biases, HAWKISH, INFLATIONARY, verbatim data point
    item1 = res[0]
    assert "USD" in item1["currencies"]
    assert "EUR" in item1["currencies"]
    assert "BULLISH_USD" in item1["sentiments"]
    assert "BEARISH_EUR" in item1["sentiments"]
    assert "HAWKISH" in item1["sentiments"]
    assert "INFLATIONARY" in item1["sentiments"]
    assert item1["key_data_point"] == "actual 3.8% vs forecast 3.1%"
    assert "TypeSafe Jev System One" in item1["reasoning"]

    # Item 2: Commodities (XAU, XTI) and Crypto (BTC)
    item2 = res[1]
    assert any(c in item2["currencies"] for c in ("XAU", "XTI", "BTC"))
    assert any(s in item2["sentiments"] for s in ("BULLISH_XAU", "BULLISH_XTI", "BULLISH_BTC"))


@pytest.mark.asyncio
async def test_jev_option_c_data_point_empty_on_none_surprise():
    """Verify key_data_point remains empty when surprise_magnitude is none."""
    from utils.typesafe.jev_primitives import classify_news_batch_with_jev
    from datetime import datetime, timezone

    class MockItem:
        def __init__(self, id, title, summary):
            self.id = id
            self.title = title
            self.summary = summary
            self.fetched_at = datetime.now(timezone.utc)

    class MockAnswer:
        def __init__(self, choice, conf=0.9):
            self.choice = choice
            self.confidence = conf
            self.noul = 0.2

    class MockResp:
        answers = {
            "impact": MockAnswer("MEDIUM", 0.85),
            "surprise_magnitude": MockAnswer("none", 0.90),
            "cb_stance": MockAnswer("none", 0.80),
            "inflation_impact": MockAnswer("none", 0.80),
            "is_fresh_catalyst": MockAnswer("no", 0.1),
            "is_deescalation": MockAnswer("no", 0.1),
            "is_risk_off": MockAnswer("no", 0.1),
            "is_risk_on": MockAnswer("no", 0.1),
            "key_asset_classes": MockAnswer("none", 0.9),
        }

    class MockClient:
        async def system_one(self, state, questions, timeout=15.0):
            return MockResp()

    items = [MockItem(10, "Fed Powell speaks on economic outlook at 2:00 PM vs earlier timing", "General speech")]
    res = await classify_news_batch_with_jev(
        client=MockClient(),
        batch=items,
        now_utc=datetime.now(timezone.utc)
    )

    assert res is not None
    assert len(res) == 1
    # surprise_magnitude is none -> key_data_point must be empty string
    assert res[0]["key_data_point"] == ""


@pytest.mark.asyncio
async def test_jev_option_c_partial_gather_triage():
    """Verify non-blocking partial gather: items with low confidence are omitted for Gemini micro-retry."""
    from utils.typesafe.jev_primitives import classify_news_batch_with_jev
    from datetime import datetime, timezone

    class MockItem:
        def __init__(self, id, title, summary):
            self.id = id
            self.title = title
            self.summary = summary
            self.fetched_at = datetime.now(timezone.utc)

    class MockAnswer:
        def __init__(self, choice, conf=0.9):
            self.choice = choice
            self.confidence = conf
            self.noul = 0.5

    class MockResp:
        def __init__(self, impact, conf):
            self.answers = {
                "impact": MockAnswer(impact, conf),
                "surprise_magnitude": MockAnswer("none", 0.90),
                "is_fresh_catalyst": MockAnswer("no", 0.1),
                "is_deescalation": MockAnswer("no", 0.1),
                "is_risk_off": MockAnswer("no", 0.1),
                "is_risk_on": MockAnswer("no", 0.1),
                "key_asset_classes": MockAnswer("forex", 0.9),
            }

    class MockClient:
        async def system_one(self, state, questions, timeout=15.0):
            title = state.get("title", "")
            if "Item 1" in title:
                return MockResp("HIGH", 0.90)   # Confident
            elif "Item 2" in title:
                return MockResp("MEDIUM", 0.40) # Low confidence (below 0.60 threshold)
            else:
                return MockResp("LOW", 0.85)    # Confident

    batch = [
        MockItem(1, "Item 1: Major Policy Shift", "High confidence"),
        MockItem(2, "Item 2: Ambiguous Rumor on Central Bank", "Low confidence"),
        MockItem(3, "Item 3: Routine Statistical Update", "High confidence"),
    ]

    res = await classify_news_batch_with_jev(
        client=MockClient(),
        batch=batch,
        now_utc=datetime.now(timezone.utc),
        min_confidence=0.60
    )

    assert res is not None
    # Exactly 2 items returned; Item 2 is omitted so micro-retry escalates it to Gemini Flash Lite!
    assert len(res) == 2
    assert [r["news_id"] for r in res] == [1, 3]
    assert res[0]["impact"] == "HIGH"
    assert res[1]["impact"] == "LOW"


@pytest.mark.asyncio
async def test_jev_option_c_all_fail_returns_none():
    """Verify that if all items fail or fall below min_confidence, returns None to trigger full LLM fallback."""
    from utils.typesafe.jev_primitives import classify_news_batch_with_jev
    from datetime import datetime, timezone

    class MockItem:
        def __init__(self, id, title):
            self.id = id
            self.title = title
            self.summary = ""
            self.fetched_at = datetime.now(timezone.utc)

    class MockClient:
        async def system_one(self, state, questions, timeout=15.0):
            raise ConnectionError("Jev API unreachable")

    batch = [MockItem(1, "Item A"), MockItem(2, "Item B")]
    res = await classify_news_batch_with_jev(
        client=MockClient(),
        batch=batch,
        now_utc=datetime.now(timezone.utc),
        min_confidence=0.60
    )

    assert res is None


def test_jev_questions_to_schema_synthesis():
    """Verify that jev_questions_to_schema synthesizes valid JSON Schema from Jev primitives."""
    from utils.typesafe.jev_primitives import (
        jev_questions_to_schema,
        build_risk_gate_conservative_questions,
        build_risk_gate_aggressive_questions,
        build_pattern_context_questions,
        build_confluence_gate_questions,
        build_session_timing_questions,
        build_debate_evaluator_questions,
    )
    from typesafe_sdk import Choice, Score, Noul

    custom_q = {
        "is_active": Noul(instructions="Is active?"),
        "severity": Choice(instructions="Select severity", criteria={"LOW": "Low", "HIGH": "High"}),
        "urgency_score": Score(instructions="Rate urgency", criteria=["1", "2", "3", "4", "5"]),
    }
    schema = jev_questions_to_schema(custom_q)
    assert schema["type"] == "object"
    assert "properties" in schema
    assert schema["properties"]["is_active"]["type"] == "boolean"
    assert schema["properties"]["severity"]["type"] == "string"
    assert schema["properties"]["severity"]["enum"] == ["LOW", "HIGH"]
    assert schema["properties"]["urgency_score"]["type"] == "integer"
    assert schema["properties"]["urgency_score"]["minimum"] == 1
    assert schema["properties"]["urgency_score"]["maximum"] == 5

    # Test with new question builders
    builders = [
        build_risk_gate_conservative_questions("EURUSD", "BUY"),
        build_risk_gate_aggressive_questions("EURUSD", "BUY"),
        build_pattern_context_questions("EURUSD", "2024-01-01"),
        build_confluence_gate_questions("EURUSD", "TREND"),
        build_session_timing_questions("LONDON", 45),
        build_debate_evaluator_questions(),
    ]
    for b in builders:
        s = jev_questions_to_schema(b)
        assert s["type"] == "object"
        assert len(s["properties"]) >= 3
        assert s["required"] == list(b.keys())


@pytest.mark.asyncio
async def test_conservative_and_aggressive_risk_llm_jev_mapping():
    """Verify that conservative and aggressive risk LLM helpers correctly map Jev outputs."""
    from analysis.debate.conservative_risk_llm import analyze_risk_conservative_llm
    from analysis.debate.aggressive_risk_llm import analyze_risk_aggressive_llm

    class MockJevClient:
        def __init__(self, mock_return):
            self.mock_return = mock_return

        async def generate_content(self, **kwargs):
            import json
            return json.dumps(self.mock_return)

    # 1. Conservative normal approval
    mock_cons = MockJevClient({
        "_jev_model": "jev-latest",
        "veto_trade": False,
        "risk_level": "LOW",
        "recommended_multiplier_bucket": "STANDARD"
    })
    res_c = await analyze_risk_conservative_llm(mock_cons, "EURUSD", {"direction": "BUY"})
    assert res_c["veto_trade"] is False
    assert res_c["recommended_multiplier"] == 0.7
    assert "Jev Conservative Evaluation" in res_c["risk_profile_assessment"]

    # 2. Conservative critical veto
    mock_cons_veto = MockJevClient({
        "_jev_model": "jev-latest",
        "veto_trade": False,
        "risk_level": "CRITICAL",
        "recommended_multiplier_bucket": "STANDARD"
    })
    res_c_veto = await analyze_risk_conservative_llm(mock_cons_veto, "EURUSD", {"direction": "BUY"})
    assert res_c_veto["veto_trade"] is True
    assert res_c_veto["recommended_multiplier"] == 0.0

    # 3. Aggressive normal approval
    mock_agg = MockJevClient({
        "_jev_model": "jev-latest",
        "veto_trade": False,
        "reward_asymmetry": 3,
        "recommended_multiplier_bucket": "AGGRESSIVE"
    })
    res_a = await analyze_risk_aggressive_llm(mock_agg, "EURUSD", {"direction": "BUY"})
    assert res_a["veto_trade"] is False
    assert res_a["recommended_multiplier"] == 1.5
    assert "Jev Aggressive Evaluation" in res_a["risk_profile_assessment"]

    # 4. Aggressive structural veto
    mock_agg_veto = MockJevClient({
        "_jev_model": "jev-latest",
        "veto_trade": True,
        "reward_asymmetry": 1,
        "recommended_multiplier_bucket": "ZERO"
    })
    res_a_veto = await analyze_risk_aggressive_llm(mock_agg_veto, "EURUSD", {"direction": "BUY"})
    assert res_a_veto["veto_trade"] is True
    assert res_a_veto["recommended_multiplier"] == 0.0


@pytest.mark.asyncio
async def test_context_verifier_jev_mapping():
    """Verify that PatternContextVerifier correctly processes Jev System One responses."""
    from indicators.pattern_similarity.context_verifier import PatternContextVerifier, ContextVerdict
    from indicators.pattern_similarity.models import PatternMatch, MarketContext
    from datetime import datetime, timezone

    verifier = PatternContextVerifier()

    class MockContextClient:
        async def classify_json(self, **kwargs):
            assert "jev_questions" in kwargs
            return {
                "_jev_model": "jev-latest",
                "relevance": "high",
                "is_macro_driver_similar": True,
                "adjustment_level": "full_weight"
            }

    match = PatternMatch(
        start_index=0,
        end_index=10,
        start_time=1672531200.0,
        end_time=1672617600.0,
        similarity=0.88,
        context_score=0.85,
        context_label="MODERATE"
    )
    current_context = MarketContext(
        vix_level=18.5,
        vix_category="normal",
        dxy_trend="bullish",
        market_regime="trend",
        rate_cycle="pause",
        asset_trend="above_ema200"
    )

    verdict = await verifier._verify_single_match(
        match=match,
        timeframe="H1",
        symbol="EURUSD",
        current_context=current_context,
        session=None,
        llm_client=MockContextClient(),
        web_search_enabled=False
    )

    assert isinstance(verdict, ContextVerdict)
    assert verdict.relevance == "high"
    assert verdict.adjustment_factor == 1.0
    assert "Jev System One macro comparability" in verdict.reason


@pytest.mark.asyncio
async def test_fallback_wrapper_jev_adaptation():
    """Verify FallbackClientWrapper synthesizes schema and normalizes metadata for generative fallbacks."""
    from analysis.providers.llm_factory import FallbackClientWrapper, LLMFactory
    from typesafe_sdk import Noul, Choice

    captured_kwargs = {}

    class MockGenerativeClient:
        provider_name = "gemini"
        model = "gemini-3.5-flash-lite"

        async def classify_json(self, prompt, **kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            return {"decision": True, "verdict": "APPROVE"}

    factory = LLMFactory(settings={})
    mock_gen_client = MockGenerativeClient()
    factory._create_client_instance = mock.MagicMock(return_value=mock_gen_client)
    wrapper = FallbackClientWrapper(
        factory=factory,
        primary="gemini-3.5-flash-lite",
        fallbacks=[],
        role_config={},
        task_role="test_jev_fallback"
    )

    jev_q = {
        "decision": Noul(instructions="Approve?"),
        "verdict": Choice(instructions="Verdict", criteria={"APPROVE": "Approve", "REJECT": "Reject"})
    }

    res = await wrapper.classify_json(
        prompt="Evaluate setup",
        jev_questions=jev_q
    )

    # 1. Verify schema was automatically synthesized from jev_questions
    assert "schema" in captured_kwargs
    schema = captured_kwargs["schema"]
    assert schema["type"] == "object"
    assert "decision" in schema["properties"]
    assert "verdict" in schema["properties"]
    assert schema["properties"]["decision"]["type"] == "boolean"

    # 2. Verify fallback metadata was normalized onto result dict
    assert res is not None
    assert res["decision"] is True
    assert res["_is_fallback"] is True
    assert res["_confidence"] == 0.85
    assert res["_is_high_confidence"] is True


def test_openrouter_kev_and_jev_provider_initialization(monkeypatch):
    """Test direct initialization of Kev and OpenRouter Jev."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "typesafe_secret_123")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter_secret_456")

    # 1. Direct Jev (Default)
    direct_jev = TypeSafeProvider(model="jev-latest")
    assert direct_jev.model == "jev-latest"
    assert direct_jev.base_url == "https://api.typesafe.ai"
    assert direct_jev.api_key == "typesafe_secret_123"

    # 2. OpenRouter Kev with full name
    kev_full = TypeSafeProvider(model="jaredpalmer/kev-4b")
    assert kev_full.model == "jaredpalmer/kev-4b"
    assert kev_full.base_url == "https://openrouter.ai/api"
    assert kev_full.api_key == "openrouter_secret_456"

    # 3. OpenRouter Kev with alias 'kev-4b'
    kev_alias = TypeSafeProvider(model="kev-4b")
    assert kev_alias.model == "jaredpalmer/kev-4b"
    assert kev_alias.base_url == "https://openrouter.ai/api"
    assert kev_alias.api_key == "openrouter_secret_456"

    # 4. OpenRouter Kev with prefix 'openrouter/jaredpalmer/kev-4b'
    kev_prefixed = TypeSafeProvider(model="openrouter/jaredpalmer/kev-4b")
    assert kev_prefixed.model == "jaredpalmer/kev-4b"
    assert kev_prefixed.base_url == "https://openrouter.ai/api"
    assert kev_prefixed.api_key == "openrouter_secret_456"

    # 5. OpenRouter Jev
    or_jev = TypeSafeProvider(model="openrouter/typesafe/jev-latest")
    assert or_jev.model == "typesafe/jev-latest"
    assert or_jev.base_url == "https://openrouter.ai/api"
    assert or_jev.api_key == "openrouter_secret_456"


def test_llm_factory_and_registry_openrouter_routing(monkeypatch):
    """Test LLMFactory and ProviderRegistry properly route Kev and OpenRouter Jev to typesafe provider."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "typesafe_secret_123")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter_secret_456")

    from analysis.providers.llm_factory import LLMFactory

    settings = {
        "model_catalog": {
            "jev-latest": {"provider": "typesafe"},
            "jaredpalmer/kev-4b": {"provider": "typesafe"},
            "openrouter/typesafe/jev-latest": {"provider": "typesafe"},
        }
    }
    factory = LLMFactory(settings=settings)

    # 1. Provider resolution check
    assert factory._resolve_provider("jev-latest") == "typesafe"
    assert factory._resolve_provider("jaredpalmer/kev-4b") == "typesafe"
    assert factory._resolve_provider("kev-4b") == "typesafe"
    assert factory._resolve_provider("openrouter/typesafe/jev-latest") == "typesafe"

    # 2. Client instantiation check
    client_jev = factory._create_client_instance("jev-latest", role_config={})
    assert isinstance(client_jev, TypeSafeProvider)
    assert client_jev.model == "jev-latest"
    assert client_jev.base_url == "https://api.typesafe.ai"
    assert client_jev.api_key == "typesafe_secret_123"

    client_kev = factory._create_client_instance("jaredpalmer/kev-4b", role_config={})
    assert isinstance(client_kev, TypeSafeProvider)
    assert client_kev.model == "jaredpalmer/kev-4b"
    assert client_kev.base_url == "https://openrouter.ai/api"
    assert client_kev.api_key == "openrouter_secret_456"

    client_or_jev = factory._create_client_instance("openrouter/typesafe/jev-latest", role_config={})
    assert isinstance(client_or_jev, TypeSafeProvider)
    assert client_or_jev.model == "typesafe/jev-latest"
    assert client_or_jev.base_url == "https://openrouter.ai/api"
    assert client_or_jev.api_key == "openrouter_secret_456"


@pytest.mark.asyncio
async def test_fallback_wrapper_skips_typesafe_on_array_schema():
    """Verify FallbackClientWrapper skips TypeSafe models when classify_json receives an array schema."""
    from analysis.providers.llm_factory import LLMFactory, FallbackClientWrapper

    settings = {
        "model_catalog": {
            "jev-latest": {"provider": "typesafe"},
            "jaredpalmer/kev-4b": {"provider": "typesafe"},
            "gemini-3.5-flash-lite": {"provider": "gemini"},
        }
    }
    factory = LLMFactory(settings=settings)

    mock_jev = mock.AsyncMock()
    mock_kev = mock.AsyncMock()
    mock_gemini = mock.AsyncMock()
    mock_gemini.classify_json.return_value = [{"index": 1, "impact": "HIGH"}]

    def mock_create(model, role_config, slot_name="primary", task_role=None):
        if model == "jev-latest":
            return mock_jev
        elif model == "jaredpalmer/kev-4b":
            return mock_kev
        elif model == "gemini-3.5-flash-lite":
            return mock_gemini
        return None

    factory._create_client_instance = mock_create

    wrapper = FallbackClientWrapper(
        primary="jev-latest",
        fallbacks=["jaredpalmer/kev-4b", "gemini-3.5-flash-lite"],
        role_config={},
        factory=factory,
        task_role="news_classification"
    )

    array_schema = {
        "type": "array",
        "items": {"type": "object", "properties": {"impact": {"type": "string"}}}
    }

    result = await wrapper.classify_json(prompt="Batch of news", schema=array_schema)

    # 1. Jev and Kev should be skipped upfront without calling classify_json
    mock_jev.classify_json.assert_not_called()
    mock_kev.classify_json.assert_not_called()

    # 2. Gemini should be invoked directly
    mock_gemini.classify_json.assert_awaited_once()
    assert result == [{"index": 1, "impact": "HIGH"}]






