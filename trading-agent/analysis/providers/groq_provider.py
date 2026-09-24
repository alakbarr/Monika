"""
GroqProvider — Provider untuk model Groq via OpenAI-compatible API.
Mewarisi semua logika dari OpenAIProvider karena Groq API 100% kompatibel.
"""
import logging
import os
import time
from typing import Optional, ClassVar, Any
from analysis.providers.openai_provider import OpenAIProvider
from utils.api.groq_rate_limiter import GroqRateLimiter, get_api_keys

logger = logging.getLogger(__name__)

# NOTE: These aliases map settings.yaml names to Groq API model IDs.
# Validated at startup via run_startup_checks() in main.py.
# If Groq changes model IDs, update here and re-verify.
GROQ_MODEL_ALIASES = {
    # Active production models on Groq
    "groq-gpt-oss-120b":   "openai/gpt-oss-120b",
    "groq-gpt-oss-20b":    "openai/gpt-oss-20b",
    "groq-qwen3.8-27b":    "qwen/qwen3.8-27b",
    "qwen3.8-27b":         "qwen/qwen3.8-27b",
    # Backward compatibility / decommissioned model redirects (prevent 404s)
    "groq-compound":       "qwen/qwen3.8-27b",
    "groq-compound-mini":  "qwen/qwen3.8-27b",
    "groq/compound":       "qwen/qwen3.8-27b",
    "groq/compound-mini":  "qwen/qwen3.8-27b",
    "groq-qwen3.6-27b":    "qwen/qwen3.8-27b",
    "qwen3.6-27b":         "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b":    "qwen/qwen3.8-27b",
}

_groq_limiter = GroqRateLimiter()

class GroqProvider(OpenAIProvider):
    """
    Provider untuk model Groq.
    Menggunakan OpenAI library karena Groq API kompatibel dengan OpenAI.
    Base URL: https://api.groq.com/openai/v1
    """
    _key_cooldowns: ClassVar[dict[str, float]] = {}
    _key_index: ClassVar[int] = 0
    _client_pool: ClassVar[dict[str, Any]] = {}
    
    def __init__(self, model: str, max_tokens: int = 2048,
                 api_key: Optional[str] = None, settings: Optional[dict] = None,
                 temperature: float = 0.0, max_tool_turns: int = 15,
                 thinking_level: str = "none", **kwargs):
        actual_model = GROQ_MODEL_ALIASES.get(model, model)
        self._api_keys = [api_key] if api_key else get_api_keys()
        initial_key = self._api_keys[0] if self._api_keys else None
        super().__init__(actual_model, max_tokens=max_tokens, api_key=initial_key or "dummy",
                         settings=settings, temperature=temperature,
                         max_tool_turns=max_tool_turns, thinking_level=thinking_level, **kwargs)
        # ==============================================================================
        # ARCHITECTURAL INVARIANT (DO NOT OVERWRITE OR REMOVE):
        # Do NOT confuse context_window (input history) with max_completion_tokens (output tokens).
        # Models like groq/compound have a 128,000 token context window, but their
        # maximum completion token ceiling is strictly 8,192 tokens.
        # Forcing self.max_tokens = 32000 causes immediate HTTP 400 Bad Request errors on Groq.
        # We respect caller's smaller requests and safely clamp against model capabilities.
        # ==============================================================================
        model_ceiling = getattr(self.capabilities, "max_output_tokens", 8192) or 8192
        self.max_tokens = min(self.max_tokens, model_ceiling)
        self.provider_name = "groq"
        self.client = self._get_client_for_key(initial_key) if initial_key else None
        
    def _get_api_key(self) -> Optional[str]:
        if not self._api_keys:
            return None
        now = time.time()
        for _ in range(len(self._api_keys)):
            key = self._api_keys[self.__class__._key_index % len(self._api_keys)]
            self.__class__._key_index += 1
            if self.__class__._key_cooldowns.get(key, 0) < now:
                return key
        return None
        
    def _get_client_for_key(self, api_key: Optional[str]):
        """Mengambil atau membuat AsyncOpenAI client instance per API key (pooled)."""
        if not api_key:
            return None
        if api_key not in self.__class__._client_pool:
            try:
                from openai import AsyncOpenAI
                timeout = float((self.settings or {}).get('llm', {}).get('providers', {}).get('groq', {}).get('timeout_seconds', 120.0))
                self.__class__._client_pool[api_key] = AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=timeout,
                    max_retries=2
                )
            except ImportError:
                logger.warning("OpenAI package not installed for Groq.")
                return None
        return self.__class__._client_pool[api_key]

    def _make_client(self, api_key: str):
        return self._get_client_for_key(api_key)

    @classmethod
    def _is_transient_error(cls, err_str: str) -> bool:
        return any(k in err_str for k in [
            "429", "rate limit", "498", "502", "503", "529",
            "bad gateway", "service unavailable", "flex_tier",
            "capacity", "overloaded", "temporarily unavailable"
        ])

    @classmethod
    def _handle_rate_limit_error(cls, api_key: str, error: Exception, method_name: str = "generate") -> None:
        """
        Klasifikasi presisi rate limit & error Groq API:
        - Server Overload / 498 Flex Tier / 502 / 503 (30s): Transient capacity issue, coba key lain.
        - RPD/TPD (24h): Hanya jika pesan memuat requests per day / tokens per day / daily limit.
        - RPM / TPM / Burst (parse wait time or default 65s): Default untuk seluruh HTTP 429.
        """
        err_str = str(error).lower()
        is_server_error = any(k in err_str for k in [
            "498", "502", "503", "529", "bad gateway", "service unavailable",
            "flex_tier", "capacity", "overloaded", "temporarily unavailable"
        ])
        is_rpd = not is_server_error and any(k in err_str for k in [
            "requests per day", "rpd", "tokens per day", "tpd",
            "daily limit", "daily quota", "exceeded your daily"
        ])
        if is_server_error:
            cls._key_cooldowns[api_key] = time.time() + 30.0
            logger.warning(f"Groq key server/capacity overload in {method_name} ({api_key[:8]}...). Cooldown 30s, trying next key.")
        elif is_rpd:
            cls._key_cooldowns[api_key] = time.time() + 86400
            logger.error(f"Groq key RPD exhausted in {method_name} ({api_key[:8]}...). Cooldown 24h, trying next key.")
        else:
            cooldown_sec = 65.0
            import re
            m = re.search(r"try again in ([\d\.]+)s", err_str) or re.search(r"retry after (\d+)", err_str)
            if m:
                try:
                    cooldown_sec = float(m.group(1)) + 2.0
                except (ValueError, TypeError):
                    cooldown_sec = 65.0
            cls._key_cooldowns[api_key] = time.time() + cooldown_sec
            logger.warning(f"Groq key RPM/TPM hit in {method_name} ({api_key[:8]}...). Cooldown {cooldown_sec:.1f}s, trying next key.")

    async def generate(self, prompt: str, system: Optional[Any] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[str]:
        if not self._api_keys:
            logger.error("No Groq API key available.")
            return None
        for attempt in range(max(1, len(self._api_keys))):
            api_key = self._get_api_key()
            if not api_key:
                logger.error("No Groq API key available.")
                return None
            if not await _groq_limiter.try_acquire(self.model, api_key=api_key):
                logger.warning(f"Groq rate limit for key {api_key[:8]}..., trying next key")
                continue
                
            self.client = self._get_client_for_key(api_key)
            if not self.client:
                return None
                
            try:
                return await super().generate(prompt, system, temperature, max_tokens=max_tokens, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if self._is_transient_error(err_str):
                    self._handle_rate_limit_error(api_key, e, "generate")
                    continue
                raise
        return None

    async def classify_json(self, prompt: str, system_prompt: Optional[str]=None, schema: Optional[dict]=None, temperature: Optional[float]=None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[dict]:
        if not self._api_keys:
            logger.error('No Groq API key available.')
            return None
        for attempt in range(max(1, len(self._api_keys))):
            api_key = self._get_api_key()
            if not api_key:
                logger.error('No Groq API key available.')
                return None
            if not await _groq_limiter.try_acquire(self.model, api_key=api_key):
                logger.warning(f'Groq rate limit for key {api_key[:8]}..., trying next key')
                continue
            self.client = self._get_client_for_key(api_key)
            if not self.client:
                return None
            try:
                return await super().classify_json(prompt, system_prompt, schema, temperature, max_tokens=max_tokens, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if self._is_transient_error(err_str):
                    self._handle_rate_limit_error(api_key, e, "classify_json")
                    continue
                raise
        return None

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: str):
        if not self._api_keys:
            raise RuntimeError("Groq API key not configured (GROQ_API_KEYS missing in environment)")
        for attempt in range(max(1, len(self._api_keys))):
            api_key = self._get_api_key()
            if not api_key:
                raise RuntimeError("No Groq API key available.")
            if not await _groq_limiter.try_acquire(self.model, api_key=api_key):
                logger.warning(f"Groq rate limit for key {api_key[:8]}..., trying next key")
                continue
            self.client = self._get_client_for_key(api_key)
            if not self.client:
                continue
            try:
                return await super().run_tool_agent(messages, tools, system_prompt)
            except Exception as e:
                err_str = str(e).lower()
                if self._is_transient_error(err_str):
                    self._handle_rate_limit_error(api_key, e, "run_tool_agent")
                    continue
                raise
        raise RuntimeError(f"Groq all API keys failed or rate-limited for {self.model}")
