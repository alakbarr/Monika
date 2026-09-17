import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.providers.anthropic_provider import AnthropicProvider
from analysis.providers.gemini_provider import GeminiProvider
from analysis.providers.base_provider import MockBlock, MockResponse

@pytest.mark.asyncio
@patch('anthropic.AsyncAnthropic')
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
@patch('analysis.providers.gemini_provider.fetch_with_retry')
@patch('analysis.providers.gemini_provider.GeminiRateLimiter')
async def test_gemini_provider_generate(mock_limiter, mock_fetch):
    mock_limiter_instance = AsyncMock()
    mock_limiter_instance.try_acquire.return_value = True
    mock_limiter.return_value = mock_limiter_instance
    
    mock_fetch.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Gemini reply"}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}
    }
    
    with patch.dict('os.environ', {'GEMINI_API_KEY': 'test_key'}):
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
    from utils.api.http_retry import RateLimitError
    GeminiProvider._key_cooldowns.clear()

    # 1. Gemini QuotaFailure with 'Queries per minute' -> cooldown 65s
    err_rpm = RateLimitError("HTTP 429", '{"error": {"message": "Resource has been exhausted", "details": [{"violations": [{"description": "Quota exceeded for quota metric \'Queries\' and limit \'Queries per minute\'"}]}]}}')
    GeminiProvider._handle_rate_limit_error("gemini-key-1", err_rpm, "generate")
    cd1 = GeminiProvider._key_cooldowns.get("gemini-key-1", 0) - time.time()
    assert 60.0 <= cd1 <= 66.0, f"Expected ~65s cooldown, got {cd1}"

    # 2. Gemini Generic RESOURCE_EXHAUSTED / Server overload -> cooldown 65s (bukan 24h)
    err_generic = RateLimitError("HTTP 429", '{"error": {"code": 429, "message": "Resource has been exhausted (e.g. check quota).", "status": "RESOURCE_EXHAUSTED"}}')
    GeminiProvider._handle_rate_limit_error("gemini-key-2", err_generic, "generate")
    cd2 = GeminiProvider._key_cooldowns.get("gemini-key-2", 0) - time.time()
    assert 60.0 <= cd2 <= 66.0, f"Expected ~65s cooldown, got {cd2}"

    # 3. Gemini Explicit RPD ('GenerateContent requests per day') -> cooldown 24h (86400s)
    err_rpd = RateLimitError("HTTP 429", '{"error": {"details": [{"violations": [{"description": "Quota exceeded for quota metric \'GenerateContent requests per day per project\'"}]}]}}')
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
    from analysis.providers.gemini_provider import _check_gemini_block

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

    with patch.object(provider, 'run_tool_agent', side_effect=err_402):
        session = MagicMock()
        res = await provider.run_agent(session, "sys", "user", tools=[], stage_name="test_stage")
        assert res["success"] is False
        assert res.get("is_billing_error") is True

    # Mock 400 BadRequestError -> is_billing_error must be False
    resp_400 = httpx.Response(400, request=req)
    err_400 = APIStatusError(message="invalid prompt format 400", response=resp_400, body=None)

    with patch.object(provider, 'run_tool_agent', side_effect=err_400):
        session = MagicMock()
        res_400 = await provider.run_agent(session, "sys", "user", tools=[], stage_name="test_stage")
        assert res_400["success"] is False
        assert res_400.get("is_billing_error") is False


@pytest.mark.asyncio
@patch('analysis.providers.gemini_provider.fetch_with_retry')
@patch('analysis.providers.gemini_provider.GeminiRateLimiter')
async def test_gemini_token_allocation_with_thinking(mock_limiter, mock_fetch):
    """Memverifikasi bahwa maxOutputTokens disetel ke 65536 dan thinkingLevel dimetakan ke enum resmi Gemini 3."""
    mock_limiter_instance = AsyncMock()
    mock_limiter_instance.try_acquire.return_value = True
    mock_limiter.return_value = mock_limiter_instance

    mock_fetch.return_value = {
        "candidates": [{"content": {"parts": [{"text": "response"}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50}
    }

    with patch.dict('os.environ', {'GEMINI_API_KEY': 'test_key'}):
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


@pytest.mark.asyncio
@patch('analysis.providers.gemini_provider.fetch_with_retry')
@patch('analysis.providers.gemini_provider.GeminiRateLimiter')
async def test_gemini_run_tool_agent_max_tokens_stop_reason(mock_limiter, mock_fetch):
    """Memverifikasi bahwa run_tool_agent menghasilkan stop_reason='max_tokens' saat finishReason='MAX_TOKENS'."""
    mock_limiter_instance = AsyncMock()
    mock_limiter_instance.try_acquire.return_value = True
    mock_limiter.return_value = mock_limiter_instance

    mock_fetch.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "Truncated text..."}]},
            "finishReason": "MAX_TOKENS"
        }],
        "usageMetadata": {"promptTokenCount": 500, "candidatesTokenCount": 2048}
    }

    with patch.dict('os.environ', {'GEMINI_API_KEY': 'test_key'}):
        provider = GeminiProvider(model="gemini-3.5-flash-lite", max_tokens=8192)
        resp = await provider.run_tool_agent(messages=[{"role": "user", "content": "hi"}], tools=[], system_prompt="sys")
        assert resp.stop_reason == "max_tokens"
        assert len(resp.content) == 1
        assert resp.content[0].text == "Truncated text..."


@pytest.mark.asyncio
@patch('analysis.providers.anthropic_provider.ClaudeRateLimiter.acquire_session_slot')
async def test_anthropic_thinking_and_64k_tokens(mock_limiter):
    """Memverifikasi bahwa AnthropicProvider menyetel max_tokens 64000 dan thinking config yang tepat."""
    from analysis.providers.anthropic_provider import AnthropicProvider
    mock_limiter.return_value = True

    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test_anthropic_key'}):
        provider = AnthropicProvider(model="claude-3-7-sonnet-20250219", thinking_level="high")
        provider._save_token_usage = AsyncMock()
        provider.client = AsyncMock()
        
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="Claude analysis")]
        mock_resp.usage = MagicMock(input_tokens=100, output_tokens=50, cache_read_input_tokens=0, cache_creation_input_tokens=0)
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
    from analysis.providers.groq_provider import GroqProvider
    from analysis.providers.openrouter_provider import OpenRouterProvider
    
    # 1. GroqProvider reasoning params
    groq_provider = GroqProvider(model="qwen/qwen3.8-27b", thinking_level="high", settings={"llm": {"providers": {"groq": {}}}})
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
@patch('analysis.providers.gemini_provider.fetch_with_retry')
@patch('analysis.providers.gemini_provider.GeminiRateLimiter')
async def test_gemini_auto_recovery_on_max_tokens(mock_limiter, mock_fetch):
    """Memverifikasi bahwa GeminiProvider melakukan auto-recovery saat MAX_TOKENS dengan thoughts > 10000."""
    mock_limiter_instance = AsyncMock()
    mock_limiter_instance.try_acquire.return_value = True
    mock_limiter.return_value = mock_limiter_instance

    # Response 1: Truncated MAX_TOKENS with high thoughts (runaway)
    resp_truncated = {
        "candidates": [{
            "content": {"parts": [{"text": '{"partial":'}]},
            "finishReason": "MAX_TOKENS"
        }],
        "usageMetadata": {"promptTokenCount": 2000, "candidatesTokenCount": 2500, "thoughtsTokenCount": 62900}
    }
    # Response 2: Recovered with MINIMAL thinking
    resp_recovered = {
        "candidates": [{
            "content": {"parts": [{"text": '{"directional_bias":"BEARISH","confidence":"HIGH"}'}]},
            "finishReason": "STOP"
        }],
        "usageMetadata": {"promptTokenCount": 2000, "candidatesTokenCount": 350, "thoughtsTokenCount": 100}
    }

    mock_fetch.side_effect = [resp_truncated, resp_recovered]

    with patch.dict('os.environ', {'GEMINI_API_KEY': 'test_key'}):
        provider = GeminiProvider(model="gemini-3.1-flash-lite", thinking_level="high", settings={})
        provider._save_token_usage = AsyncMock()

        res = await provider.generate("Analyze macro setup")
        assert res == '{"directional_bias":"BEARISH","confidence":"HIGH"}'
        assert mock_fetch.call_count == 2


@pytest.mark.asyncio
@patch('anthropic.AsyncAnthropic')
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

    mock_session = AsyncMock()
    provider = AnthropicProvider(model="claude-3-5-sonnet", settings={"llm": {"providers": {"anthropic": {"streaming": {"enabled": False}}}}})
    provider._save_token_usage = AsyncMock()
    provider._log_tool_call = AsyncMock()

    with patch('analysis.providers.anthropic_provider.ToolExecutor') as mock_executor_cls:
        mock_executor = AsyncMock()
        mock_executor.execute = AsyncMock(return_value={"bars": [1, 2, 3]})
        mock_executor_cls.return_value = mock_executor

        result = await provider.run_agent(
            session=mock_session,
            system_prompt="You are a trading agent.",
            user_message="Analyze H4 price",
            tools=[{"name": "get_price_history", "description": "Fetches price", "input_schema": {}}],
            stage_name="test_stage"
        )

        # Tool executor hanya dipanggil 1 kali karena turn 2 terdeteksi identik via hashlib MD5 dan disupresi
        assert mock_executor.execute.call_count == 1
        assert result["success"] is True

