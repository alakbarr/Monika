import pytest
import json
from unittest.mock import AsyncMock, patch
from analysis.providers.groq_provider import GroqProvider, GROQ_MODEL_ALIASES
from analysis.providers.openai_provider import OpenAIProvider

@pytest.mark.asyncio
async def test_groq_provider_model_alias_resolution():
    """Model alias harus di-resolve ke Groq model ID aktual."""
    with patch.dict('os.environ', {'GROQ_API_KEYS': 'test-key'}):
        provider = GroqProvider(model="groq-compound")
        assert provider.model == "groq/compound"

@pytest.mark.asyncio
async def test_groq_provider_reads_multi_keys():
    """Provider harus baca GROQ_API_KEYS plural, bukan GROQ_API_KEY."""
    with patch.dict('os.environ', {'GROQ_API_KEYS': 'key1,key2,key3'}, clear=True):
        from utils.api.groq_rate_limiter import get_api_keys
        keys = get_api_keys()
        assert keys == ['key1', 'key2', 'key3']

def test_groq_key_rotation_round_robin():
    """Round-robin pilih key berbeda tiap call."""
    with patch.dict('os.environ', {'GROQ_API_KEYS': 'key-a,key-b,key-c'}, clear=True):
        provider = GroqProvider(model="groq-compound")
        assert len(provider._api_keys) == 3
        k1 = provider._get_api_key()
        k2 = provider._get_api_key()
        k3 = provider._get_api_key()
        assert len({k1, k2, k3}) == 3  # Semua 3 key berbeda

@pytest.mark.asyncio
async def test_groq_key_cooldown_skips_to_next():
    """Key yang cooldown harus di-skip, pakai key berikutnya."""
    import time
    with patch.dict('os.environ', {'GROQ_API_KEYS': 'bad-key,good-key'}, clear=True):
        provider = GroqProvider(model="groq-compound")
        GroqProvider._key_cooldowns['bad-key'] = time.time() + 9999
        chosen = provider._get_api_key()
        assert chosen == 'good-key'

@pytest.mark.asyncio
async def test_groq_generate_rotates_on_429():
    """Jika key pertama 429, generate() retry dengan key berikutnya."""
    with patch.dict('os.environ', {'GROQ_API_KEYS': 'key-a,key-b'}, clear=True):
        provider = GroqProvider(model="groq-compound")
    GroqProvider._key_cooldowns.clear()
    GroqProvider._key_index = 0

    call_count = 0
    async def mock_super_generate(prompt, system=None, temperature=None, max_tokens=None, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("429 rate limit per minute")
        return "success"
    
    with patch('analysis.providers.groq_provider._groq_limiter') as mock_limiter:
        mock_limiter.try_acquire = AsyncMock(return_value=True)
        with patch.object(OpenAIProvider, 'generate', side_effect=mock_super_generate):
            result = await provider.generate("test")
    
    assert result == "success"
    assert call_count == 2

@pytest.mark.asyncio
async def test_groq_provider_generate():
    """GroqProvider.generate() harus bisa memanggil API."""
    provider = GroqProvider(model="groq-compound", api_key="test-key")
    
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock()]
    mock_response.choices[0].message.content = "Hello from Groq"
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    
    with patch('analysis.providers.groq_provider._groq_limiter') as mock_limiter:
        mock_limiter.try_acquire = AsyncMock(return_value=True)
        with patch.object(OpenAIProvider, 'generate', return_value="Hello from Groq"):
            result = await provider.generate("Say hello")
    
    assert result == "Hello from Groq"

@pytest.mark.asyncio
async def test_groq_rate_limit_blocks_call():
    """Ketika rate limit tercapai, generate() harus return None."""
    provider = GroqProvider(model="groq-compound", api_key="test-key")
    
    with patch('analysis.providers.groq_provider._groq_limiter') as mock_limiter:
        mock_limiter.try_acquire = AsyncMock(return_value=False)
        result = await provider.generate("Say hello")
    
    assert result is None

def test_all_groq_aliases_defined():
    """Semua model Groq harus terdefinisi di GROQ_MODEL_ALIASES."""
    expected = {
        "groq-compound", "groq-compound-mini",
        "groq-gpt-oss-120b", "groq-gpt-oss-20b",
        "groq-qwen3.6-27b", "groq-qwen3.8-27b",
        "qwen3.6-27b", "qwen3.8-27b"
    }
    assert expected == set(GROQ_MODEL_ALIASES.keys())
    assert GROQ_MODEL_ALIASES["groq-qwen3.6-27b"] == "qwen/qwen3.6-27b"
    assert GROQ_MODEL_ALIASES["groq-qwen3.8-27b"] == "qwen/qwen3.8-27b"


def test_groq_qwen_quotas():
    """Memverifikasi kuota spesifik untuk qwen3.6-27b dan qwen3.8-27b."""
    from utils.api.groq_rate_limiter import GROQ_QUOTA, _num_keys
    q36 = GROQ_QUOTA.get("qwen/qwen3.6-27b")
    q38 = GROQ_QUOTA.get("qwen/qwen3.8-27b")
    assert q36 is not None
    assert q38 is not None
    assert q36["rpm"] == 30 * _num_keys
    assert q36["rpd"] == 1000 * _num_keys
    assert q36["tpm"] == 8000 * _num_keys
    assert q36["tpd"] == 200000 * _num_keys

    assert q38["rpm"] == 30 * _num_keys
    assert q38["rpd"] == 1000 * _num_keys
    assert q38["tpm"] == 8000 * _num_keys
    assert q38["tpd"] == 2000000 * _num_keys


def test_groq_handle_rate_limit_classification():
    """Memverifikasi presisi klasifikasi rate limit Groq (RPM/TPM vs Wait time vs RPD vs Server Overload)."""
    import time
    GroqProvider._key_cooldowns.clear()

    # 1. Groq RPM error format with retry wait time
    err_rpm = Exception("Rate limit reached for model `llama-3.1-8b-instant` on requests per minute (RPM): Limit 30, Used 30, Requested 1. Please try again in 1.969s.")
    GroqProvider._handle_rate_limit_error("groq-key-1", err_rpm, "generate")
    cd1 = GroqProvider._key_cooldowns.get("groq-key-1", 0) - time.time()
    assert 3.0 <= cd1 <= 5.0, f"Expected ~4.0s cooldown, got {cd1}"

    # 2. Groq RPD error format
    err_rpd = Exception("Rate limit reached for model `llama-3.1-8b-instant` on requests per day (RPD): Limit 14400, Used 14400. Please try again in 12h30m.")
    GroqProvider._handle_rate_limit_error("groq-key-2", err_rpd, "generate")
    cd2 = GroqProvider._key_cooldowns.get("groq-key-2", 0) - time.time()
    assert 86390.0 <= cd2 <= 86405.0, f"Expected ~86400s cooldown, got {cd2}"

    # 3. Groq 498 Flex Tier / 503 Server Overload -> 30s cooldown
    err_503 = Exception("Error code: 503 - Service Unavailable: capacity exceeded on flex tier (498)")
    GroqProvider._handle_rate_limit_error("groq-key-3", err_503, "generate")
    cd3 = GroqProvider._key_cooldowns.get("groq-key-3", 0) - time.time()
    assert 25.0 <= cd3 <= 32.0, f"Expected ~30s cooldown, got {cd3}"

    GroqProvider._key_cooldowns.clear()


@pytest.mark.asyncio
async def test_groq_client_pooling():
    """Client AsyncOpenAI harus di-reuse dari _client_pool per API key."""
    GroqProvider._client_pool.clear()
    provider = GroqProvider(model="groq-compound", api_key="key-pool-1")
    c1 = provider._get_client_for_key("key-pool-1")
    c2 = provider._get_client_for_key("key-pool-1")
    assert c1 is not None
    assert c1 is c2
    assert "key-pool-1" in GroqProvider._client_pool


@pytest.mark.asyncio
async def test_groq_run_agent_no_keys():
    """Jika tidak ada API key yang dikonfigurasi, run_agent harus mengembalikan pesan error jelas."""
    with patch('analysis.providers.groq_provider.get_api_keys', return_value=[]):
        provider = GroqProvider(model="groq-compound", api_key=None)
        res = await provider.run_agent(
            session=AsyncMock(),
            system_prompt="sys",
            user_message="user",
            tools=[],
            stage_name="stage1_fundamental"
        )
        assert res["success"] is False
        assert "Groq API key not configured" in res["error"]


@pytest.mark.asyncio
async def test_groq_run_agent_success():
    """run_agent pada GroqProvider harus menginisialisasi client dan memanggil agent loop dengan sukses."""
    with patch.dict('os.environ', {'GROQ_API_KEYS': 'test-groq-key'}, clear=True):
        provider = GroqProvider(model="qwen3.8-27b", api_key="test-groq-key")
        assert provider.client is not None

        mock_session = AsyncMock()
        mock_result = {
            "success": True,
            "final_text": "Fundamental brief done",
            "tool_calls_made": 1,
            "turns": 2,
            "input_tokens": 100,
            "output_tokens": 50,
            "thinking_tokens": 0
        }

        with patch.object(OpenAIProvider, 'run_agent', return_value=mock_result) as mock_super_run:
            res = await provider.run_agent(
                session=mock_session,
                system_prompt="sys",
                user_message="user",
                tools=[],
                stage_name="stage1_fundamental"
            )
            assert res["success"] is True
            assert res["final_text"] == "Fundamental brief done"
            assert provider.max_tokens == 2048
            mock_super_run.assert_awaited_once()


def test_groq_compound_token_clamping():
    """groq/compound harus di-clamp ke ceiling 8192 jika caller meminta > 8192."""
    provider = GroqProvider(model="groq-compound", max_tokens=32000, api_key="test-key")
    assert provider.max_tokens == 8192


def test_groq_respects_small_max_tokens():
    """Caller dengan token kecil (misal ping 10 tokens atau default 2048) TIDAK boleh dinaikkan paksa."""
    provider_ping = GroqProvider(model="groq-compound", max_tokens=10, api_key="test-key")
    assert provider_ping.max_tokens == 10

    kwargs = {"max_tokens": 10}
    provider_ping._apply_reasoning_params(kwargs)
    assert kwargs.get("max_completion_tokens") == 10

    provider_default = GroqProvider(model="groq-compound", api_key="test-key")
    assert provider_default.max_tokens == 2048


@pytest.mark.asyncio
async def test_openai_provider_auto_heals_on_token_limit_400():
    """Saat Groq/OpenAI mengembalikan error 400 tentang max_completion_tokens, provider harus auto-heal dan retry."""
    provider = OpenAIProvider(model="groq/compound", max_tokens=32000, api_key="test-key")

    call_count = 0
    async def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            err_msg = (
                "`max_completion_tokens` must be less than or equal to `8192`, "
                "the maximum value for `max_completion_tokens` is less than the `context_window` for this model"
            )
            from openai import BadRequestError
            from httpx import Response, Request
            req = Request("POST", "https://api.groq.com/openai/v1/chat/completions")
            resp = Response(400, request=req, json={"error": {"message": err_msg, "type": "invalid_request_error", "param": "max_completion_tokens"}})
            raise BadRequestError(message=err_msg, response=resp, body={"error": {"message": err_msg}})
        
        # Second call should succeed with healed kwargs
        assert kwargs.get("max_completion_tokens") == 8192
        mock_resp = AsyncMock()
        mock_resp.choices = [AsyncMock()]
        mock_resp.choices[0].message.content = "recovered successfully"
        mock_resp.usage.prompt_tokens = 10
        mock_resp.usage.completion_tokens = 20
        return mock_resp

    provider.client.chat.completions.create = AsyncMock(side_effect=mock_create)
    resp = await provider._call_chat_completions_with_recovery(
        messages=[{"role": "user", "content": "ping"}],
        max_completion_tokens=32000
    )
    assert resp.choices[0].message.content == "recovered successfully"
    assert call_count == 2



