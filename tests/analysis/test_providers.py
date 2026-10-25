import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from tests.conftest import create_mock_async_session
from monika.infrastructure.providers.anthropic_provider import AnthropicProvider
from monika.infrastructure.providers.gemini_provider import GeminiProvider
from monika.infrastructure.providers.base_provider import MockBlock, MockResponse


@pytest.mark.asyncio
@patch("anthropic.AsyncAnthropic")
async def test_anthropic_provider_generate(mock_anthropic):
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Test reply")]
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 5
    mock_client.messages.create.return_value = mock_response
    mock_anthropic.return_value = mock_client

    provider = AnthropicProvider(model="claude-test")
    provider._save_token_usage = AsyncMock()

    result = await provider.generate("hello", "sys")
    assert result == "Test reply"
    mock_client.messages.create.assert_called_once()


@pytest.mark.asyncio
@patch("monika.infrastructure.providers.gemini_provider.fetch_with_retry")
@patch("monika.infrastructure.providers.gemini_provider.GeminiRateLimiter")
async def test_gemini_provider_generate(mock_limiter, mock_fetch):
    mock_limiter_instance = AsyncMock()
    mock_limiter_instance.try_acquire.return_value = True
    mock_limiter.return_value = mock_limiter_instance

    mock_fetch.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Gemini reply"}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"}):
        provider = GeminiProvider(model="gemini-test")
        provider._save_token_usage = AsyncMock()

        result = await provider.generate("hello", "sys")
        assert result == "Gemini reply"
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_mock_block_and_response():
    block = MockBlock(type="text", text="hello")
    assert block.type == "text"
    assert block.text == "hello"

    resp = MockResponse(content=[block], stop_reason="end_turn", input_tokens=10, output_tokens=20)
    assert resp.stop_reason == "end_turn"
    assert resp.input_tokens == 10
    assert resp.usage.input_tokens == 10


def test_gemini_handle_rate_limit_classification():
    """Memverifikasi presisi klasifikasi rate limit Gemini (RPM/TPM/Generic vs RPD vs dynamic Retry-After)."""
    import time
    from monika.infrastructure.api.http_retry import RateLimitError

    GeminiProvider._key_cooldowns.clear()

    # 1. Gemini QuotaFailure with 'Queries per minute' -> cooldown 65s
    err_rpm = RateLimitError(
        "HTTP 429",
        '{"error": {"message": "Resource has been exhausted", "details": [{"violations": [{"description": "Quota exceeded for quota metric \'Queries\' and limit \'Queries per minute\'"}]}]}}',
    )
    GeminiProvider._handle_rate_limit_error("gemini-key-1", err_rpm, "generate")
    cd1 = GeminiProvider._key_cooldowns.get("gemini-key-1", 0) - time.time()
    assert 60.0 <= cd1 <= 66.0, f"Expected ~65s cooldown, got {cd1}"

    # 2. Gemini Generic RESOURCE_EXHAUSTED / Server overload -> cooldown 65s (bukan 24h)
    err_generic = RateLimitError(
        "HTTP 429",
        '{"error": {"code": 429, "message": "Resource has been exhausted (e.g. check quota).", "status": "RESOURCE_EXHAUSTED"}}',
    )
    GeminiProvider._handle_rate_limit_error("gemini-key-2", err_generic, "generate")
    cd2 = GeminiProvider._key_cooldowns.get("gemini-key-2", 0) - time.time()
    assert 60.0 <= cd2 <= 66.0, f"Expected ~65s cooldown, got {cd2}"

    # 3. Gemini Explicit RPD ('GenerateContent requests per day') -> cooldown 24h (86400s)
    err_rpd = RateLimitError(
        "HTTP 429",
        '{"error": {"details": [{"violations": [{"description": "Quota exceeded for quota metric \'GenerateContent requests per day per project\'"}]}]}}',
    )
    GeminiProvider._handle_rate_limit_error("gemini-key-3", err_rpd, "generate")
    cd3 = GeminiProvider._key_cooldowns.get("gemini-key-3", 0) - time.time()
    assert 86390.0 <= cd3 <= 86405.0, f"Expected ~86400s cooldown, got {cd3}"

    # 4. Gemini with dynamic retry_after attribute -> cooldown retry_after + 2.0s
    err_dynamic = RateLimitError("HTTP 429", "Rate limited", retry_after=15.0)
    GeminiProvider._handle_rate_limit_error("gemini-key-4", err_dynamic, "generate")
    cd4 = GeminiProvider._key_cooldowns.get("gemini-key-4", 0) - time.time()
    assert 16.0 <= cd4 <= 18.0, f"Expected ~17s cooldown, got {cd4}"

    GeminiProvider._key_cooldowns.clear()


def test_gemini_block_detection():
    """Memverifikasi deteksi safety block dan blockReason pada respons Gemini."""
    from monika.infrastructure.providers.gemini_provider import _check_gemini_block

    # 1. Normal response -> None
    normal_data = {"candidates": [{"content": {"parts": [{"text": "Hello"}]}, "finishReason": "STOP"}]}
    assert _check_gemini_block(normal_data) is None

    # 2. Prompt-level block
    blocked_prompt = {"promptFeedback": {"blockReason": "SAFETY"}}
    assert _check_gemini_block(blocked_prompt) == "prompt_blocked:SAFETY"

    # 3. Empty candidates
    empty_candidates = {"candidates": []}
    assert _check_gemini_block(empty_candidates) == "empty_candidates"

    # 4. Candidate-level block (RECITATION / SAFETY)
    recitation = {"candidates": [{"content": {}, "finishReason": "RECITATION"}]}
    assert _check_gemini_block(recitation) == "candidate_blocked:RECITATION"


@pytest.mark.asyncio
async def test_anthropic_billing_error_classification():
    """Memverifikasi bahwa status code 402 dikenali sebagai billing error, tapi 400 TIDAK."""
    import httpx
    from anthropic import APIStatusError

    provider = AnthropicProvider(model="claude-test")

    # Mock 402 APIStatusError
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    resp_402 = httpx.Response(402, request=req)
    err_402 = APIStatusError(message="billing error", response=resp_402, body=None)

    with patch.object(provider, "run_tool_agent", side_effect=err_402):
        session = MagicMock()
        res = await provider.run_agent(session, "sys", "user", tools=[], stage_name="test_stage")
        assert res["success"] is False
        assert res.get("is_billing_error") is True

    # Mock 400 BadRequestError -> is_billing_error must be False
    resp_400 = httpx.Response(400, request=req)
    err_400 = APIStatusError(message="invalid prompt format 400", response=resp_400, body=None)

    with patch.object(provider, "run_tool_agent", side_effect=err_400):
        session = MagicMock()
        res_400 = await provider.run_agent(session, "sys", "user", tools=[], stage_name="test_stage")
        assert res_400["success"] is False
        assert res_400.get("is_billing_error") is False


@pytest.mark.asyncio
@patch("monika.infrastructure.providers.gemini_provider.fetch_with_retry")
@patch("monika.infrastructure.providers.gemini_provider.GeminiRateLimiter")
async def test_gemini_token_allocation_with_thinking(mock_limiter, mock_fetch):
    """Memverifikasi bahwa maxOutputTokens disetel ke 65536 dan thinkingLevel dimetakan ke enum resmi Gemini 3."""
    mock_limiter_instance = AsyncMock()
    mock_limiter_instance.try_acquire.return_value = True
    mock_limiter.return_value = mock_limiter_instance

    mock_fetch.return_value = {
        "candidates": [{"content": {"parts": [{"text": "response"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
    }

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"}):
        # 1. Thinking high -> maxOutputTokens=65536 & thinkingLevel="HIGH"
        provider_high = GeminiProvider(model="gemini-3.5-flash-lite", thinking_level="high")
        provider_high._save_token_usage = AsyncMock()
        await provider_high.generate("test prompt")

        call_payload = mock_fetch.call_args[1]["json"]
        assert call_payload["generationConfig"]["maxOutputTokens"] == 65536
        assert call_payload["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "HIGH"

        # 2. Thinking low -> maxOutputTokens=65536 & thinkingLevel="LOW"
        mock_fetch.reset_mock()
        provider_low = GeminiProvider(model="gemini-3.5-flash-lite", thinking_level="low")
        provider_low._save_token_usage = AsyncMock()
        await provider_low.generate("test prompt")

        call_payload_low = mock_fetch.call_args[1]["json"]
        assert call_payload_low["generationConfig"]["maxOutputTokens"] == 65536
        assert call_payload_low["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "LOW"

        # 3. Thinking minimal/none -> maxOutputTokens=65536 & thinkingLevel="MINIMAL"
        mock_fetch.reset_mock()
        provider_none = GeminiProvider(model="gemini-3.5-flash-lite", thinking_level="none")
        provider_none._save_token_usage = AsyncMock()
        await provider_none.generate("test prompt")

        call_payload_none = mock_fetch.call_args[1]["json"]
        assert call_payload_none["generationConfig"]["maxOutputTokens"] == 65536
        assert call_payload_none["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "MINIMAL"

        # 4. gemini-3.8-flash with thinking_level="none" omits thinkingConfig to prevent HTTP 400
        provider_38 = GeminiProvider(model="gemini-3.8-flash", thinking_level="none")
        assert provider_38._build_thinking_config() is None


@pytest.mark.asyncio
@patch("monika.infrastructure.providers.gemini_provider.fetch_with_retry")
@patch("monika.infrastructure.providers.gemini_provider.GeminiRateLimiter")
async def test_gemini_run_tool_agent_max_tokens_stop_reason(mock_limiter, mock_fetch):
    """Memverifikasi bahwa run_tool_agent menghasilkan stop_reason='max_tokens' saat finishReason='MAX_TOKENS'."""
    mock_limiter_instance = AsyncMock()
    mock_limiter_instance.try_acquire.return_value = True
    mock_limiter.return_value = mock_limiter_instance

    mock_fetch.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Truncated text..."}]}, "finishReason": "MAX_TOKENS"}],
        "usageMetadata": {"promptTokenCount": 500, "candidatesTokenCount": 2048},
    }

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"}):
        provider = GeminiProvider(model="gemini-3.5-flash-lite", max_tokens=8192)
        resp = await provider.run_tool_agent(
            messages=[{"role": "user", "content": "hi"}], tools=[], system_prompt="sys"
        )
        assert resp.stop_reason == "max_tokens"
        assert len(resp.content) == 1
        assert resp.content[0].text == "Truncated text..."


@pytest.mark.asyncio
@patch("monika.infrastructure.providers.anthropic_provider.ClaudeRateLimiter.acquire_session_slot")
async def test_anthropic_thinking_and_64k_tokens(mock_limiter):
    """Memverifikasi bahwa AnthropicProvider menyetel max_tokens 64000 dan thinking config yang tepat."""
    from monika.infrastructure.providers.anthropic_provider import AnthropicProvider

    mock_limiter.return_value = True

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test_anthropic_key"}):
        provider = AnthropicProvider(model="claude-3-7-sonnet-20250219", thinking_level="high")
        provider._save_token_usage = AsyncMock()
        provider.client = AsyncMock()

        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="Claude analysis")]
        mock_resp.usage = MagicMock(
            input_tokens=100, output_tokens=50, cache_read_input_tokens=0, cache_creation_input_tokens=0
        )
        provider.client.messages.create = AsyncMock(return_value=mock_resp)

        res = await provider.generate("Analyze macro setup")
        assert res == "Claude analysis"

        call_kwargs = provider.client.messages.create.call_args[1]
        # Contract: max_tokens = max(safe_max, budget+4000) with safe_max = min(max(eff, budget+4096), 64000)
        assert 14000 <= call_kwargs["max_tokens"] <= 64000
        assert call_kwargs["temperature"] == 1.0
        assert call_kwargs["thinking"]["type"] == "enabled"
        assert call_kwargs["thinking"]["budget_tokens"] == 10000


@pytest.mark.asyncio
async def test_groq_and_openrouter_token_floors():
    """Memverifikasi token ceiling untuk Groq (32768) dan OpenRouter floor (65536)."""
    from monika.infrastructure.providers.groq_provider import GroqProvider
    from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider

    # 1. GroqProvider reasoning params
    groq_provider = GroqProvider(
        model="qwen/qwen3.8-27b", thinking_level="high", settings={"llm": {"providers": {"groq": {}}}}
    )
    kwargs = {"max_tokens": 12000}
    groq_provider._apply_reasoning_params(kwargs)
    assert "max_completion_tokens" in kwargs
    assert kwargs["max_completion_tokens"] == 32768  # Raised from 8192 to 32768

    # 2. OpenRouterProvider reasoning params
    openrouter_provider = OpenRouterProvider(model="glm-5.2:free", thinking_level="high", api_key="dummy_key")
    or_kwargs = {"max_tokens": 2048}
    openrouter_provider._apply_reasoning_params(or_kwargs)
    assert or_kwargs["max_tokens"] == 65536
    assert or_kwargs["extra_body"]["reasoning"]["effort"] == "high"


@pytest.mark.asyncio
@patch("monika.infrastructure.providers.gemini_provider.fetch_with_retry")
@patch("monika.infrastructure.providers.gemini_provider.GeminiRateLimiter")
async def test_gemini_auto_recovery_on_max_tokens(mock_limiter, mock_fetch):
    """Memverifikasi bahwa GeminiProvider melakukan auto-recovery saat MAX_TOKENS dengan thoughts > 10000."""
    mock_limiter_instance = AsyncMock()
    mock_limiter_instance.try_acquire.return_value = True
    mock_limiter.return_value = mock_limiter_instance

    # Response 1: Truncated MAX_TOKENS with high thoughts (runaway)
    resp_truncated = {
        "candidates": [{"content": {"parts": [{"text": '{"partial":'}]}, "finishReason": "MAX_TOKENS"}],
        "usageMetadata": {"promptTokenCount": 2000, "candidatesTokenCount": 2500, "thoughtsTokenCount": 62900},
    }
    # Response 2: Recovered with MINIMAL thinking
    resp_recovered = {
        "candidates": [
            {
                "content": {"parts": [{"text": '{"directional_bias":"BEARISH","confidence":"HIGH"}'}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 2000, "candidatesTokenCount": 350, "thoughtsTokenCount": 100},
    }

    mock_fetch.side_effect = [resp_truncated, resp_recovered]

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test_key"}):
        provider = GeminiProvider(model="gemini-3.1-flash-lite", thinking_level="high", settings={})
        provider._save_token_usage = AsyncMock()

        res = await provider.generate("Analyze macro setup")
        assert res == '{"directional_bias":"BEARISH","confidence":"HIGH"}'
        assert mock_fetch.call_count == 2


@pytest.mark.asyncio
@patch("anthropic.AsyncAnthropic")
async def test_anthropic_run_tool_agent_anti_oscillation_hashlib(mock_anthropic):
    """Memverifikasi anti-oscillation tool hashing di AnthropicProvider berjalan mulus tanpa NameError pada hashlib."""
    mock_client = AsyncMock()
    mock_anthropic.return_value = mock_client

    # Simulasikan response turn 1: tool call get_price_history
    tool_block_1 = MagicMock()
    tool_block_1.type = "tool_use"
    tool_block_1.id = "call_1"
    tool_block_1.name = "get_price_history"
    tool_block_1.input = {"timeframe": "H4"}

    resp_1 = MagicMock()
    resp_1.content = [tool_block_1]
    resp_1.stop_reason = "tool_use"
    resp_1.usage.input_tokens = 50
    resp_1.usage.output_tokens = 20

    # Simulasikan response turn 2: repeated call tool yang sama persis
    tool_block_2 = MagicMock()
    tool_block_2.type = "tool_use"
    tool_block_2.id = "call_2"
    tool_block_2.name = "get_price_history"
    tool_block_2.input = {"timeframe": "H4"}

    resp_2 = MagicMock()
    resp_2.content = [tool_block_2]
    resp_2.stop_reason = "tool_use"
    resp_2.usage.input_tokens = 60
    resp_2.usage.output_tokens = 20

    # Turn 3: final answer
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "Completed analysis"

    resp_3 = MagicMock()
    resp_3.content = [text_block]
    resp_3.stop_reason = "end_turn"
    resp_3.usage.input_tokens = 70
    resp_3.usage.output_tokens = 30

    mock_client.messages.create.side_effect = [resp_1, resp_2, resp_3]

    mock_session = create_mock_async_session()
    provider = AnthropicProvider(
        model="claude-3-5-sonnet", settings={"llm": {"providers": {"anthropic": {"streaming": {"enabled": False}}}}}
    )
    provider._save_token_usage = AsyncMock()
    provider._log_tool_call = AsyncMock()

    with patch("monika.infrastructure.providers.anthropic_provider.ToolExecutor") as mock_executor_cls:
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value={"bars": [1, 2, 3]})
        mock_executor_cls.return_value = mock_executor

        result = await provider.run_agent(
            session=mock_session,
            system_prompt="You are a trading agent.",
            user_message="Analyze H4 price",
            tools=[{"name": "get_price_history", "description": "Fetches price", "input_schema": {}}],
            stage_name="test_stage",
        )

        # Tool executor hanya dipanggil 1 kali karena turn 2 terdeteksi identik via hashlib MD5 dan disupresi
        assert mock_executor.execute.call_count == 1
        assert result["success"] is True


def test_format_api_error_summary():
    """Memverifikasi pembersihan format error API menjadi single-line yang rapi."""
    from monika.infrastructure.api.http_retry import format_api_error_summary

    # 1. Google Gemini 503 High Demand JSON
    gemini_body = json.dumps(
        {
            "error": {
                "code": 503,
                "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.",
                "status": "UNAVAILABLE",
            }
        }
    )
    res_gemini = format_api_error_summary(503, gemini_body)
    assert (
        res_gemini
        == "HTTP 503 (UNAVAILABLE): This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later."
    )

    # 2. OpenAI / Groq standard JSON
    openai_body = json.dumps(
        {"error": {"message": "Rate limit reached for requests", "type": "requests", "code": "rate_limit_exceeded"}}
    )
    res_openai = format_api_error_summary(429, openai_body)
    assert res_openai == "HTTP 429 (requests): Rate limit reached for requests"

    # 3. HTML / Cloudflare error body
    html_body = "<html><body><h1>503 Service Temporarily Unavailable</h1><p>nginx/1.18.0</p></body></html>"
    res_html = format_api_error_summary(503, html_body)
    assert "503 Service Temporarily Unavailable" in res_html
    assert "<html>" not in res_html


def test_gemini_503_high_demand_transient_handling():
    """Memverifikasi penanganan elegan HTTP 503 High Demand pada GeminiProvider."""
    import time
    from monika.infrastructure.api.http_retry import APIStatusError
    from monika.infrastructure.providers.provider_failover_classifier import classify_error, FailoverReason

    GeminiProvider._key_cooldowns.clear()

    # 1. Error instance dengan body 503 UNAVAILABLE
    gemini_503_body = json.dumps(
        {
            "error": {
                "code": 503,
                "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.",
                "status": "UNAVAILABLE",
            }
        }
    )
    err_503 = APIStatusError(status=503, body=gemini_503_body)

    # 2. Deteksi transient error
    assert GeminiProvider._is_transient_error(err_503) is True

    # 3. Cooldown handler menetapkan cooldown ~30s untuk overload
    GeminiProvider._handle_rate_limit_error("AIzaSyTestKey123", err_503, "generate")
    cd = GeminiProvider._key_cooldowns.get("AIzaSyTestKey123", 0) - time.time()
    assert 25.0 <= cd <= 31.0, f"Expected ~30s cooldown for 503 overload, got {cd}"

    # 4. Error classifier mengklasifikasikan sebagai MODEL_OVERLOADED
    reason, detail = classify_error(err_503)
    assert reason == FailoverReason.MODEL_OVERLOADED
    assert "overloaded" in detail.lower() or "high demand" in detail.lower()

    GeminiProvider._key_cooldowns.clear()


@pytest.mark.asyncio
async def test_gemini_generate_rotates_key_on_503():
    """Memverifikasi bahwa saat attempt 1 gagal HTTP 503, generate otomatis mencoba key berikutnya yang sehat."""
    from monika.infrastructure.api.http_retry import APIStatusError

    gemini_503_body = json.dumps(
        {
            "error": {
                "code": 503,
                "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.",
                "status": "UNAVAILABLE",
            }
        }
    )

    with patch.dict("os.environ", {"GEMINI_API_KEYS": "key_alpha,key_beta"}):
        GeminiProvider._key_cooldowns.clear()
        GeminiProvider._key_index = 0
        provider = GeminiProvider(
            model="gemini-3.8-flash", settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}}
        )
        provider._save_token_usage = AsyncMock()

        # Attempt 1 (key_alpha) raises APIStatusError 503, Attempt 2 (key_beta) succeeds
        mock_success_res = MagicMock()
        mock_success_res.text = "Analysis complete from healthy key"
        mock_success_res.finish_reason = "STOP"
        mock_success_res.usage = {"promptTokenCount": 100, "candidatesTokenCount": 50}

        calls = []

        async def mock_stream_req(url, payload, headers, config, parser, model_name):
            key = headers.get("x-goog-api-key")
            calls.append(key)
            if key == "key_alpha":
                raise APIStatusError(status=503, body=gemini_503_body)
            return mock_success_res

        with (
            patch("monika.infrastructure.providers.gemini_provider.streaming_request", side_effect=mock_stream_req),
            patch("monika.infrastructure.providers.gemini_provider.get_session") as mock_db_sess,
            patch("monika.infrastructure.providers.gemini_provider.GeminiRateLimiter") as mock_rl,
        ):
            mock_rl.return_value.try_acquire = AsyncMock(return_value=True)

            result = await provider.generate("Analyze gold market")
            assert result == "Analysis complete from healthy key"
            assert "key_alpha" in calls
            assert "key_beta" in calls
            # key_alpha harus masuk cooldown
            assert "key_alpha" in GeminiProvider._key_cooldowns


def test_gemini_stream_parser_schema_sanitizer_and_blocks():
    """Cover _gemini_stream_parser, _sanitize_schema_for_gemini, and _check_gemini_block edge cases."""
    from monika.infrastructure.llm.rate_limiting.streaming import StreamResult
    from monika.infrastructure.providers.gemini_provider import (
        _check_gemini_block,
        _gemini_stream_parser,
        _sanitize_schema_for_gemini,
    )

    res = StreamResult()
    bad_input = getattr(str, "nonexistent", "not_a_dict")
    assert _gemini_stream_parser(bad_input, res) is False

    chunk = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"thought": True, "text": "thinking step"},
                        {"text": "final answer"},
                        {"functionCall": {"name": "my_tool", "args": {"x": 1}}, "thoughtSignature": "sig_123"},
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 8},
    }
    assert _gemini_stream_parser(chunk, res) is True
    assert res.thinking_text == "thinking step"
    assert res.text == "final answer"
    assert res.tool_calls[0]["name"] == "my_tool"
    assert res.usage["promptTokenCount"] == 12

    assert _check_gemini_block("not_a_dict") == "invalid_response_format"

    # Schema sanitizer branches
    assert _sanitize_schema_for_gemini(bad_input) == "not_a_dict"
    with patch("monika.infrastructure.providers.schema_normalizer.inline_json_refs", return_value="non_dict"):
        assert _sanitize_schema_for_gemini({"type": "object"}) == "non_dict"

    complex_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "additionalProperties": False,
        "allOf": [
            {"properties": {"a": {"type": ["integer", "null"]}}, "required": ["a"]},
            {"properties": {"b": {"type": "string", "enum": [1, 2]}}, "required": ["b"]},
        ],
        "nested_one": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "nested_multi": {"oneOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]},
        "enum_first": {"enum": ["x", "y"], "type": "string"},
        "type_first_enum": {"type": "integer", "enum": [10, 20]},
        "list_field": [{"type": "boolean"}, "raw_str"],
        "scalar_field": 42,
    }
    san = _sanitize_schema_for_gemini(complex_schema)
    assert san["type"] == "OBJECT"
    assert san["properties"]["a"]["nullable"] is True
    assert san["nested_one"]["nullable"] is True
    assert san["nested_multi"]["nullable"] is True
    assert "Accepted types" in san["nested_multi"]["description"]


def test_gemini_keys_thinking_and_rate_limit_edges():
    """Cover key management, cooldowns, antigravity bridge, thinking budget, and rate limit edge cases."""
    import time
    from monika.infrastructure.llm.rate_limiting.http_retry import RateLimitError

    GeminiProvider._key_cooldowns.clear()

    # 1. Init with no keys at all & antigravity bridge failure
    with (
        patch.dict("os.environ", {}, clear=True),
        patch("monika.core.security.credential_vault.vault.get_secret", return_value=None),
        patch(
            "monika.infrastructure.auth.antigravity_bridge.resolve_antigravity_access_token",
            side_effect=RuntimeError("no bridge"),
        ),
    ):
        p_empty = GeminiProvider(model="gemini-1.5-flash", free_api_keys=[])
        assert p_empty._build_thinking_config() is None
        assert p_empty._is_paid_key(None) is False

    # 2. Init with ya29 api_key & set_api_key
    p_ya = GeminiProvider(model="gemini-2.5-flash", api_key="ya29.init_token", free_api_keys=["free1"])
    assert p_ya.paid_api_key == "ya29.init_token"
    assert p_ya._is_paid_key("ya29.init_token") is True
    p_ya.set_api_key("AIzaFreeKey")
    assert p_ya.api_key == "AIzaFreeKey"
    p_ya.set_api_key("ya29.updated_token")
    assert p_ya.paid_api_key == "ya29.updated_token"
    p_ya.paid_api_key = "paid_fixed"
    assert p_ya._is_paid_key("paid_fixed") is True
    assert p_ya._is_paid_key("unknown_key") is False

    # 3. _build_thinking_config for 2.5 (off vs on) and 3.5 (on)
    assert p_ya._build_thinking_config() == {"thinkingBudget": 0}
    p_ya.set_thinking_budget(0)
    assert p_ya.thinking_budget == 0
    p_ya.set_thinking_budget(16000)
    assert p_ya.resolved_thinking_level == "HIGH"
    assert p_ya._build_thinking_config()["thinkingBudget"] >= 8192
    p_ya.set_thinking_budget(5000)
    assert p_ya.resolved_thinking_level == "MEDIUM"
    p_ya.set_thinking_budget(1024)
    assert p_ya.resolved_thinking_level == "LOW"
    with patch(
        "monika.infrastructure.llm.adaptive_thinking.QuantizedThinkingAllocator.quantize",
        side_effect=RuntimeError("quantize err"),
    ):
        p_ya.set_thinking_budget(5000)
        assert p_ya.thinking_budget == 4096

    # 4. _get_api_key branches (paid model, sticky reuse, sticky self.api_key, non-sticky fallbacks)
    p_paid = GeminiProvider(model="gemini-4-argon", free_api_keys=["f1"], api_key="explicit_k")
    p_paid.paid_api_key = "paid_k"
    with patch(
        "monika.infrastructure.auth.antigravity_bridge.resolve_antigravity_access_token",
        return_value="ya29.bridge_paid",
    ):
        assert p_paid._get_api_key() == "ya29.bridge_paid"

    with patch(
        "monika.infrastructure.auth.antigravity_bridge.resolve_antigravity_access_token",
        side_effect=RuntimeError("bridge down"),
    ):
        p_paid.paid_api_key = "paid_k"
        assert p_paid._get_api_key() == "paid_k"
        # Put paid_k in cooldown -> falls back to free/sticky
        GeminiProvider._key_cooldowns["paid_k"] = time.time() + 100
        assert p_paid._get_api_key(sticky=False) in ("f1", "f2")
        k1 = p_paid._get_api_key(sticky=True)
        assert k1 in ("f1", "f2")
        # Second sticky call returns pinned _sticky_session_key directly
        assert p_paid._get_api_key(sticky=True) == k1

    # Sticky when free_api_keys is empty -> pins self.api_key
    p_single = GeminiProvider(model="gemini-3.5-flash", free_api_keys=[], api_key="single_k")
    assert p_single._get_api_key(sticky=False) == "single_k"
    assert p_single._get_api_key(sticky=True) == "single_k"

    # Non-sticky when self.api_key is in cooldown -> tries antigravity free pool, then earliest free, then paid
    GeminiProvider._key_cooldowns["single_k"] = time.time() + 100
    with patch(
        "monika.infrastructure.auth.antigravity_bridge.resolve_antigravity_access_token",
        return_value="ya29.free_pool",
    ):
        assert p_single._get_api_key(sticky=False) == "ya29.free_pool"

    with patch(
        "monika.infrastructure.auth.antigravity_bridge.resolve_antigravity_access_token",
        side_effect=RuntimeError("no free pool"),
    ):
        p_single.paid_api_key = "backup_paid"
        assert p_single._get_api_key(sticky=False) == "backup_paid"
        GeminiProvider._key_cooldowns["backup_paid"] = time.time() + 100
        assert p_single._get_api_key(sticky=False) == "single_k"

        p_all_cool = GeminiProvider(model="gemini-3.5-flash", free_api_keys=["c1", "c2"])
        GeminiProvider._key_cooldowns["c1"] = time.time() + 200
        GeminiProvider._key_cooldowns["c2"] = time.time() + 50
        assert p_all_cool._get_api_key(sticky=False) == "c2"

    # 5. _is_transient_error and _handle_rate_limit_error with ya29 RPD, regex retry-after, and invalid float regex
    assert GeminiProvider._is_transient_error(RateLimitError("429", "limit")) is True
    assert GeminiProvider._is_transient_error(RuntimeError("service temporarily unavailable")) is True

    with patch(
        "monika.infrastructure.auth.antigravity_bridge.mark_antigravity_account_cooldown",
        side_effect=RuntimeError("mark err"),
    ):
        GeminiProvider._handle_rate_limit_error("ya29.rpd_tok", RuntimeError("exceeded your daily quota"), "gen")
        GeminiProvider._handle_rate_limit_error("ya29.rpm_tok", RuntimeError("try again in 12.5s"), "gen")
        GeminiProvider._handle_rate_limit_error("ya29.bad_num", RuntimeError("try again in ...s"), "gen")

    GeminiProvider._key_cooldowns.clear()


@pytest.mark.asyncio
async def test_gemini_generate_and_classify_json_full_branches():
    """Cover all streaming, recovery, timeout fallback, rate limit, and classify_json branches in GeminiProvider."""
    from monika.infrastructure.llm.rate_limiting.http_retry import RateLimitError
    from monika.infrastructure.llm.rate_limiting.streaming import StreamResult, StreamTimeoutError

    GeminiProvider._key_cooldowns.clear()

    with (
        patch("monika.infrastructure.providers.gemini_provider.get_session"),
        patch("monika.infrastructure.providers.gemini_provider.GeminiRateLimiter") as mock_rl,
    ):
        # 1. Quota exhausted -> returns None
        mock_rl.return_value.try_acquire = AsyncMock(return_value=False)
        p = GeminiProvider(model="gemini-2.5-flash", thinking_level="medium", free_api_keys=["k1"])
        assert await p.generate("hi", system=("sys_static", "sys_dyn"), max_tokens=1000) is None
        p_none_t = GeminiProvider(model="gemini-2.5-flash", thinking_level="none", free_api_keys=["k1"])
        assert await p_none_t.generate("hi", max_tokens=1000) is None

        # 2. No API key available -> returns None
        mock_rl.return_value.try_acquire = AsyncMock(return_value=True)
        with patch.object(p, "_get_api_key", return_value=None):
            assert await p.generate("hi", system_prompt="sys", max_tokens=None) is None

        # 3. Streaming MAX_TOKENS with auto-recovery success (and failure), plus MINIMAL partial return
        p_stream = GeminiProvider(
            model="gemini-2.5-flash",
            thinking_level="high",
            free_api_keys=["ya29.k1", "k2"],
            settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}},
        )
        p_stream._save_token_usage = AsyncMock()

        trunc_res = StreamResult(
            text="partial",
            finish_reason="MAX_TOKENS",
            usage={"promptTokenCount": 10, "candidatesTokenCount": 20, "thoughtsTokenCount": 500},
        )
        rec_res = StreamResult(
            text="recovered full text",
            finish_reason="STOP",
            usage={"promptTokenCount": 10, "candidatesTokenCount": 50},
        )
        with patch(
            "monika.infrastructure.providers.gemini_provider.streaming_request",
            new_callable=AsyncMock,
            side_effect=[trunc_res, rec_res],
        ):
            out = await p_stream.generate(
                "prompt", max_tokens=500, response_schema={"type": "object", "properties": {"a": {"type": "string"}}}
            )
            assert out == "recovered full text"

        # Recovery raises exception -> falls back to returning partial stream_res.text
        p_low = GeminiProvider(
            model="gemini-3.5-flash",
            thinking_level="low",
            free_api_keys=["k1"],
            settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}},
        )
        p_low._save_token_usage = AsyncMock()
        with patch(
            "monika.infrastructure.providers.gemini_provider.streaming_request",
            new_callable=AsyncMock,
            side_effect=[trunc_res, RuntimeError("rec err")],
        ):
            out2 = await p_low.generate("prompt", max_tokens=500)
            assert out2 == "partial"

        # MINIMAL thinking with MAX_TOKENS and outp > 0 -> returns partial directly
        p_min = GeminiProvider(
            model="gemini-3.5-flash",
            thinking_level="none",
            free_api_keys=["k1"],
            settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}},
        )
        p_min._save_token_usage = AsyncMock()
        with patch(
            "monika.infrastructure.providers.gemini_provider.streaming_request",
            new_callable=AsyncMock,
            return_value=trunc_res,
        ):
            assert await p_min.generate("prompt") == "partial"

        # 4. StreamTimeoutError: non-streaming fallback succeeds, and when fallback fails across attempts then raises
        with (
            patch(
                "monika.infrastructure.providers.gemini_provider.streaming_request",
                new_callable=AsyncMock,
                side_effect=StreamTimeoutError("idle timeout"),
            ),
            patch(
                "monika.infrastructure.providers.gemini_provider.fetch_with_retry",
                new_callable=AsyncMock,
                return_value={"candidates": [{"content": {"parts": [{"text": "fallback ok"}]}}]},
            ),
        ):
            assert await p_min.generate("prompt") == "fallback ok"

        p_two = GeminiProvider(
            model="gemini-3.5-flash",
            free_api_keys=["k1", "k2"],
            settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}},
        )
        with (
            patch(
                "monika.infrastructure.providers.gemini_provider.streaming_request",
                new_callable=AsyncMock,
                side_effect=StreamTimeoutError("timeout"),
            ),
            patch(
                "monika.infrastructure.providers.gemini_provider.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=RuntimeError("fb fail"),
            ),
        ):
            with pytest.raises(StreamTimeoutError):
                await p_two.generate("prompt")

        # 5. Non-streaming: blocked response, MAX_TOKENS recovery exception, RateLimitError, non-transient error
        p_non = GeminiProvider(
            model="gemini-2.5-flash",
            thinking_level="high",
            free_api_keys=["k1", "k2", "k3", "k4"],
            settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": False}}}}},
        )
        p_non._save_token_usage = AsyncMock()
        blocked_resp = {"candidates": []}
        max_tok_resp = {
            "candidates": [{"content": {"parts": [{"text": "after_rec_fail"}]}, "finishReason": "MAX_TOKENS"}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 5},
        }
        with patch(
            "monika.infrastructure.providers.gemini_provider.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[
                blocked_resp,
                RateLimitError("429", "limit"),
                RuntimeError("400 bad request"),
                max_tok_resp,
                RuntimeError("rec failed"),
            ],
        ):
            assert await p_non.generate("prompt") == "after_rec_fail"

        # All attempts fail -> returns None
        with patch(
            "monika.infrastructure.providers.gemini_provider.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=RuntimeError("400 fatal"),
        ):
            assert await p_non.generate("prompt") is None

        # 6. classify_json branches (None, valid JSON, unparseable JSON)
        with patch.object(p_non, "generate", new_callable=AsyncMock, return_value=None):
            assert await p_non.classify_json("prompt") is None
        with patch.object(p_non, "generate", new_callable=AsyncMock, return_value='{"decision": "buy"}'):
            assert await p_non.classify_json("prompt", schema={"type": "object"}) == {"decision": "buy"}
        with patch.object(p_non, "generate", new_callable=AsyncMock, return_value="not valid json at all"):
            assert await p_non.classify_json("prompt") is None


@pytest.mark.asyncio
async def test_gemini_run_tool_agent_and_chat_loop_full_branches():
    """Cover all message conversion, streaming/non-streaming, error, and run_chat_loop branches in GeminiProvider."""
    from monika.infrastructure.llm.rate_limiting.http_retry import RateLimitError
    from monika.infrastructure.llm.rate_limiting.streaming import StreamResult, StreamTimeoutError

    GeminiProvider._key_cooldowns.clear()

    with (
        patch("monika.infrastructure.providers.gemini_provider.get_session"),
        patch("monika.infrastructure.providers.gemini_provider.GeminiRateLimiter") as mock_rl,
    ):
        # 1. Quota exhausted raises Exception
        mock_rl.return_value.try_acquire = AsyncMock(return_value=False)
        p = GeminiProvider(model="gemini-3.5-flash", thinking_level="medium", free_api_keys=["k1"])
        with pytest.raises(Exception, match="quota exhausted"):
            await p.run_tool_agent([{"role": "user", "content": "hi"}], [], "sys")

        mock_rl.return_value.try_acquire = AsyncMock(return_value=True)

        # 2. Message conversion (OpenAI tool_calls & tool role, Anthropic tool_use & tool_result with native signature, dynamic_note injection)
        messages_complex = [
            {
                "role": "assistant",
                "content": "Let me call tools",
                "tool_calls": [
                    {"id": "c1", "function": {"name": "t1", "arguments": '{"a": 1}'}},
                    {"id": "c2", "function": {"name": "t2", "arguments": "{bad_json"}},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": '{"res": 1}'},
            {"role": "tool", "tool_call_id": "c2", "content": "raw_string_res"},
            {"role": "tool", "tool_call_id": "c2", "content": 12345},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "native_gemini_sig", "name": "t3", "input": {"k": "v"}},
                    {"type": "tool_use", "id": "call_synth", "name": "t4", "input": {}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "native_gemini_sig", "content": "plain_str"},
                    {"type": "tool_result", "tool_use_id": "call_synth", "content": 999},
                    {"type": "text", "text": "user follow up"},
                ],
            },
        ]
        tools_spec = [{"name": "t1", "description": "desc", "input_schema": {"type": "object"}}]

        # Streaming success with MAX_TOKENS, text, and tool_calls
        p_stream = GeminiProvider(
            model="gemini-3.5-flash",
            thinking_level="high",
            free_api_keys=["ya29.tok"],
            settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}},
        )
        stream_out = StreamResult(
            text="stream reply",
            finish_reason="MAX_TOKENS",
            tool_calls=[{"name": "t1", "args": {"a": 1}, "thoughtSignature": "native_sig"}],
            usage={"promptTokenCount": 20, "candidatesTokenCount": 10, "thoughtsTokenCount": 5},
        )
        with patch(
            "monika.infrastructure.providers.gemini_provider.streaming_request",
            new_callable=AsyncMock,
            return_value=stream_out,
        ):
            resp = await p_stream.run_tool_agent(messages_complex, tools_spec, ("static_sys", "dyn_note"))
            assert resp.stop_reason == "tool_use"
            assert resp.is_paid is True

        # Dynamic note injection when no user text part exists + streaming failure when _get_api_key returns None
        p_low = GeminiProvider(
            model="gemini-3.5-flash",
            thinking_level="low",
            free_api_keys=["k1"],
            settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}},
        )
        with patch.object(p_low, "_get_api_key", return_value=None):
            with pytest.raises(Exception, match="streaming request failed"):
                await p_low.run_tool_agent(
                    [{"role": "tool", "tool_call_id": "c1", "content": "{}"}], [], ("static", "dyn")
                )

        # StreamTimeoutError in run_tool_agent: non-streaming fallback succeeds, and when it fails across attempts
        with (
            patch(
                "monika.infrastructure.providers.gemini_provider.streaming_request",
                new_callable=AsyncMock,
                side_effect=StreamTimeoutError("timeout"),
            ),
            patch(
                "monika.infrastructure.providers.gemini_provider.fetch_with_retry",
                new_callable=AsyncMock,
                return_value={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "thought text", "thought": True, "thoughtSignature": "ts_1"},
                                    {"functionCall": {"name": "t1", "args": {}}, "thoughtSignature": "ts_2"},
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
            ),
        ):
            resp_fb = await p_low.run_tool_agent([{"role": "user", "content": "hi"}], [], "sys")
            assert resp_fb.stop_reason == "tool_use"
            assert any(b.type == "thinking" for b in resp_fb.content)

        p_two = GeminiProvider(
            model="gemini-3.5-flash",
            thinking_level="medium",
            free_api_keys=["k1", "k2"],
            settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": True}}}}},
        )
        with (
            patch(
                "monika.infrastructure.providers.gemini_provider.streaming_request",
                new_callable=AsyncMock,
                side_effect=StreamTimeoutError("timeout"),
            ),
            patch(
                "monika.infrastructure.providers.gemini_provider.fetch_with_retry",
                new_callable=AsyncMock,
                side_effect=RuntimeError("fb err"),
            ),
        ):
            with pytest.raises(StreamTimeoutError):
                await p_two.run_tool_agent([{"role": "user", "content": "hi"}], [], "sys")

        # Non-streaming run_tool_agent: blocked, None data, RateLimitError, transient error, non-transient error, empty candidates
        p_non = GeminiProvider(
            model="gemini-3.5-flash",
            free_api_keys=["k1", "k2", "k3", "k4", "k5"],
            settings={"llm": {"providers": {"gemini": {"streaming": {"enabled": False}}}}},
        )
        with patch(
            "monika.infrastructure.providers.gemini_provider.fetch_with_retry",
            new_callable=AsyncMock,
            side_effect=[
                {"candidates": []},
                None,
                RateLimitError("429", "limit"),
                RuntimeError("503 service unavailable"),
                RuntimeError("400 bad request"),
            ],
        ):
            with pytest.raises(Exception, match="Gemini API request failed"):
                await p_non.run_tool_agent([{"role": "user", "content": "hi"}], [], "sys")

        with (
            patch(
                "monika.infrastructure.providers.gemini_provider.fetch_with_retry",
                new_callable=AsyncMock,
                return_value={"candidates": []},
            ),
            patch("monika.infrastructure.providers.gemini_provider._check_gemini_block", return_value=None),
        ):
            with pytest.raises(Exception, match="empty candidates"):
                await p_non.run_tool_agent([{"role": "user", "content": "hi"}], [], "sys")

        # 3. run_chat_loop: error handling, anti-oscillation, propose_action, custom & default tool_executor, max_tokens stop
        with patch.object(p_non, "run_tool_agent", new_callable=AsyncMock, side_effect=RuntimeError("chat err")):
            err_chat = await p_non.run_chat_loop("sys", [{"role": "user", "content": "old"}], "new", [])
            assert err_chat["success"] is False

        # Turn 1: tool_use (with un-json-serializable key fallback & normal tool), Turn 2: repeated tool + propose_action, Turn 3: end_turn
        b_tool1 = MockBlock(type="tool_use", name="get_price", input={"sym": "EURUSD"}, id="id1")
        b_text1 = MockBlock(type="text", text="Checking...")
        r_turn1 = MockResponse(content=[b_text1, b_tool1], stop_reason="tool_use", input_tokens=10, output_tokens=5)
        r_turn1.is_paid = True

        b_tool_repeat = MockBlock(type="tool_use", name="get_price", input={"sym": "EURUSD"}, id="id2")
        b_propose = MockBlock(type="tool_use", name="propose_action", input={"action": "buy"}, id="id3")
        b_other = MockBlock(type="tool_use", name="other_tool", input={1: "val"}, id="id4")
        r_turn2 = MockResponse(
            content=[b_tool_repeat, b_propose, b_other], stop_reason="tool_use", input_tokens=15, output_tokens=10
        )

        r_turn3 = MockResponse(
            content=[MockBlock(type="text", text="All done")], stop_reason="end_turn", input_tokens=20, output_tokens=10
        )

        p_non._save_token_usage = AsyncMock()
        mock_exec = AsyncMock()
        mock_exec.execute = AsyncMock(return_value={"price": 1.10})

        with patch.object(p_non, "run_tool_agent", new_callable=AsyncMock, side_effect=[r_turn1, r_turn2, r_turn3]):
            chat_ok = await p_non.run_chat_loop("sys", [], "go", [], tool_executor=mock_exec)
            assert chat_ok["success"] is True
            assert chat_ok["reply"] == "All done"
            assert chat_ok["proposed_action"] == {"action": "buy"}

        # Default ToolExecutor import branch + stop_reason != "tool_use" (e.g. "max_tokens")
        r_max_tok = MockResponse(
            content=[MockBlock(type="text", text="partial")], stop_reason="max_tokens", input_tokens=5, output_tokens=5
        )
        with (
            patch.object(p_non, "run_tool_agent", new_callable=AsyncMock, side_effect=[r_turn1, r_max_tok]),
            patch("monika.application.analysis.tools.tool_executor.ToolExecutor") as mock_te_cls,
            patch("json.dumps", side_effect=[TypeError("unserializable"), "{}", "{}", "{}"]),
        ):
            mock_te_cls.return_value.execute = AsyncMock(return_value={"ok": 1})
            chat_def = await p_non.run_chat_loop("sys", [], "go", [], tool_executor=None)
            assert chat_def["success"] is True
