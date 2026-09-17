"""
OpenRouterProvider — Provider untuk model OpenRouter via OpenAI-compatible API.
Mendukung routing model multi-vendor, tool calling, structured JSON outputs,
reasoning effort, prompt caching, dan Multi-Key Rotation (Free vs Paid Tier).
Base URL: https://openrouter.ai/api/v1
"""
import logging
import os
import time
import json
from typing import Optional, Dict, Any, ClassVar
from analysis.providers.openai_provider import OpenAIProvider
from utils.api.openrouter_rate_limiter import (
    OpenRouterRateLimiter,
    get_paid_key,
    get_free_keys,
    get_all_keys,
    is_free_tier_model,
)

logger = logging.getLogger("TradingAgent.OpenRouterProvider")

OPENROUTER_MODEL_ALIASES = {
    # --- Anthropic ---
    "claude-fable-5": "anthropic/claude-fable-5",
    "fable-5": "anthropic/claude-fable-5",
    "claude-opus-5": "anthropic/claude-opus-5",
    "opus-5": "anthropic/claude-opus-5",
    "claude-opus-4.8": "anthropic/claude-opus-4.8",
    "opus-4.8": "anthropic/claude-opus-4.8",
    "claude-opus-4.7": "anthropic/claude-opus-4.7",
    "opus-4.7": "anthropic/claude-opus-4.7",
    "claude-opus-4.6": "anthropic/claude-opus-4.6",
    "opus-4.6": "anthropic/claude-opus-4.6",
    "claude-opus-4.5": "anthropic/claude-opus-4.5",
    "opus-4.5": "anthropic/claude-opus-4.5",
    "claude-sonnet-5": "anthropic/claude-sonnet-5",
    "sonnet-5": "anthropic/claude-sonnet-5",
    "claude-sonnet-4.6": "anthropic/claude-sonnet-4.6",
    "claude-sonnet-4-6": "anthropic/claude-sonnet-4.6",
    "sonnet-4.6": "anthropic/claude-sonnet-4.6",
    "claude-sonnet-4.5": "anthropic/claude-sonnet-4.5",
    "claude-sonnet-4-5": "anthropic/claude-sonnet-4.5",
    "sonnet-4.5": "anthropic/claude-sonnet-4.5",
    "claude-haiku-4.5": "anthropic/claude-haiku-4.5-20251001",
    "claude-haiku-4-5": "anthropic/claude-haiku-4.5-20251001",
    "claude-haiku-4-5-20251001": "anthropic/claude-haiku-4.5-20251001",
    "haiku-4.5": "anthropic/claude-haiku-4.5-20251001",

    # --- DeepSeek ---
    "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
    "deepseek-v4-pro-0813": "deepseek/deepseek-v4-pro-0813",
    "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    "deepseek-v4-flash-0731": "deepseek/deepseek-v4-flash-0731",

    # --- GLM / Zhipu (z-ai) ---
    "glm-5.3": "z-ai/glm-5.3",
    "glm-5.2": "z-ai/glm-5.2",
    "glm-5.2:free": "z-ai/glm-5.2:free",
    "glm-5.1": "z-ai/glm-5.1",
    "glm-5": "z-ai/glm-5",
    "zhipu/glm-5.3": "z-ai/glm-5.3",
    "zhipu/glm-5.2": "z-ai/glm-5.2",
    "zhipu/glm-5.2:free": "z-ai/glm-5.2:free",
    "zhipu/glm-5.1": "z-ai/glm-5.1",
    "z-ai/glm-5.3": "z-ai/glm-5.3",
    "z-ai/glm-5.2": "z-ai/glm-5.2",
    "z-ai/glm-5.2:free": "z-ai/glm-5.2:free",
    "z-ai/glm-5.1": "z-ai/glm-5.1",
    "z-ai/glm-5": "z-ai/glm-5",

    # --- Google Pro/Preview (OpenRouter routing) ---
    "gemini-3.1-pro-preview": "google/gemini-3.1-pro-preview",
    "gemini-2.5-pro": "google/gemini-2.5-pro",
    "gemini-3.7-flash": "google/gemini-3.7-flash",
    "gemini-3.6-flash": "google/gemini-3.6-flash",
    "gemini-3.5-flash": "google/gemini-3.5-flash",
    "gemini-3.5-flash-lite": "google/gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite": "google/gemini-3.1-flash-lite",
    "gemini-3.0-flash-preview": "google/gemini-3.0-flash-preview",

    # --- Meta ---
    "muse-spark-1.2": "meta-llama/muse-spark-1.2",
    "meta/muse-spark-1.2": "meta-llama/muse-spark-1.2",

    # --- MiniMax ---
    "minimax-m3": "minimax/minimax-m3",
    "minimax/minimax-m3": "minimax/minimax-m3",
    "minimax-m3:free": "minimax/minimax-m3:free",
    "minimax/minimax-m3:free": "minimax/minimax-m3:free",

    # --- Moonshot ---
    "kimi-k3": "moonshot/kimi-k3",
    "moonshot/kimi-k3": "moonshot/kimi-k3",

    # --- OpenAI ---
    "gpt-5.6-sol": "openai/gpt-5.6-sol",
    "gpt-5.6-terra": "openai/gpt-5.6-terra",
    "gpt-5.6-luna": "openai/gpt-5.6-luna",
    "gpt-5.5": "openai/gpt-5.5",
    "gpt-5.4": "openai/gpt-5.4",
    "gpt-5.4-mini": "openai/gpt-5.4-mini",
    "gpt-5.4-nano": "openai/gpt-5.4-nano",
    "gpt-5.1": "openai/gpt-5.1",
    "gpt-5-mini": "openai/gpt-5.6-luna",

    # --- Qwen ---
    "qwen3.8-max": "qwen/qwen3.8-max",
    "qwen3.8-2.4t-a95b": "qwen/qwen3.8-2.4t-a95b",
    "qwen3.8-27b": "qwen/qwen3.8-27b",
    "qwen3.6-27b": "qwen/qwen3.6-27b",

    # --- XAI ---
    "grok-4.6": "x-ai/grok-4.6",
    "grok-4.5": "x-ai/grok-4.5",
    "grok-4.3": "x-ai/grok-4.3",

    # --- Xiaomi ---
    "mimo-v2.5-pro": "xiaomi/mimo-v2.5-pro",
    "mimo-v2.5": "xiaomi/mimo-v2.5",

    # --- Stealth / Ox Alpha ---
    "ox-alpha": "stealth/ox-alpha",
    "0x-alpha": "stealth/ox-alpha",
    "stealth/ox-alpha": "stealth/ox-alpha",

    # --- OpenRouter Free Tier Models ---
    # Google Gemma (Free)
    "gemma-4-31b-it:free": "google/gemma-4-31b-it:free",
    "gemma-4-31b:free": "google/gemma-4-31b-it:free",
    "google/gemma-4-31b-it:free": "google/gemma-4-31b-it:free",
    "gemma-4-26b-a4b-it:free": "google/gemma-4-26b-a4b-it:free",
    "gemma-4-26b:free": "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-26b-a4b-it:free": "google/gemma-4-26b-a4b-it:free",

    # NVIDIA Nemotron (Free)
    "nemotron-3-ultra:free": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nemotron-3-ultra-550b-a55b:free": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nemotron-3.5-lightning:free": "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3.5-lightning:free": "nvidia/nemotron-3.5-lightning:free",
    "nemotron-3-super:free": "nvidia/nemotron-3-super-120b-a12b:free",
    "nemotron-3-super-120b-a12b:free": "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-super-120b-a12b:free": "nvidia/nemotron-3-super-120b-a12b:free",
    "nemotron-3-nano:free": "nvidia/nemotron-3-nano-30b-a3b:free",
    "nemotron-3-nano-30b-a3b:free": "nvidia/nemotron-3-nano-30b-a3b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free": "nvidia/nemotron-3-nano-30b-a3b:free",
    "nemotron-3-nano-omni:free": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nemotron-3-nano-omni-30b-a3b-reasoning:free": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nemotron-nano-12b-vl:free": "nvidia/nemotron-nano-12b-v2-vl:free",
    "nemotron-nano-12b-v2-vl:free": "nvidia/nemotron-nano-12b-v2-vl:free",
    "nvidia/nemotron-nano-12b-v2-vl:free": "nvidia/nemotron-nano-12b-v2-vl:free",
    "nemotron-nano-9b:free": "nvidia/nemotron-nano-9b-v2:free",
    "nemotron-nano-9b-v2:free": "nvidia/nemotron-nano-9b-v2:free",
    "nvidia/nemotron-nano-9b-v2:free": "nvidia/nemotron-nano-9b-v2:free",
    "nemotron-3.5-safety:free": "nvidia/nemotron-3.5-content-safety:free",
    "nemotron-3.5-content-safety:free": "nvidia/nemotron-3.5-content-safety:free",
    "nvidia/nemotron-3.5-content-safety:free": "nvidia/nemotron-3.5-content-safety:free",

    # Cohere (Free)
    "north-mini-code:free": "cohere/north-mini-code:free",
    "cohere/north-mini-code:free": "cohere/north-mini-code:free",

    # Poolside (Free)
    "laguna-s-2.1:free": "poolside/laguna-s-2.1:free",
    "poolside/laguna-s-2.1:free": "poolside/laguna-s-2.1:free",
    "laguna-xs-2.1:free": "poolside/laguna-xs-2.1:free",
    "poolside/laguna-xs-2.1:free": "poolside/laguna-xs-2.1:free",

    # Thinking Machines (Free)
    "inkling:free": "thinkingmachines/inkling:free",
    "thinkingmachines/inkling:free": "thinkingmachines/inkling:free",
    "inkling-small:free": "thinkingmachines/inkling-small:free",
    "thinkingmachines/inkling-small:free": "thinkingmachines/inkling-small:free",

    # Dots Studio (Free)
    "dots-3-note:free": "dots-studio/dots-3-note-preview:free",
    "dots-3-note-preview:free": "dots-studio/dots-3-note-preview:free",
    "dots-studio/dots-3-note-preview:free": "dots-studio/dots-3-note-preview:free",

    # Liquid AI (Free)
    "lfm-2.5-2.6b:free": "liquid/lfm-2.5-2.6b:free",
    "liquid/lfm-2.5-2.6b:free": "liquid/lfm-2.5-2.6b:free",

    # OpenRouter Auto Router (Free)
    "openrouter/free": "openrouter/free",
    "openrouter-free": "openrouter/free",
}

_openrouter_limiter = OpenRouterRateLimiter()


class OpenRouterProvider(OpenAIProvider):
    """
    Provider untuk OpenRouter API (https://openrouter.ai/api/v1).
    Mendukung routing model multi-vendor, tool calling, structured JSON outputs,
    reasoning effort, prompt caching, dan Multi-Key Rotation (Free vs Paid Tier).
    """
    _model_key_cooldowns: ClassVar[dict[tuple[str, str], float]] = {}
    _key_cooldowns: ClassVar[dict[str, float]] = {}
    _key_index: ClassVar[int] = 0
    _client_pool: ClassVar[dict[str, Any]] = {}

    def __init__(self, model: str, max_tokens: int = 2048, max_tool_turns: int = 15,
                 thinking_level: str = "none", api_key: Optional[str] = None,
                 settings: Optional[dict] = None, temperature: float = 0.0, **kwargs):
        resolved_model = OPENROUTER_MODEL_ALIASES.get(model, model)
        self.raw_model_name = model
        self.is_free = is_free_tier_model(self.raw_model_name) or is_free_tier_model(resolved_model)

        # Dynamic key extraction
        if api_key:
            self._paid_key = api_key
            self._free_keys = [api_key]
            self._all_keys = [api_key]
            initial_key = api_key
        else:
            self._paid_key = get_paid_key()
            self._free_keys = get_free_keys()
            self._all_keys = get_all_keys()
            if self.is_free:
                initial_key = self._all_keys[0] if self._all_keys else "dummy_key"
            else:
                initial_key = self._paid_key or (self._all_keys[0] if self._all_keys else "dummy_key")

        super().__init__(model=resolved_model, max_tokens=max_tokens, api_key=initial_key,
                         settings=settings, temperature=temperature, **kwargs)
        self.provider_name = "openrouter"
        self.model = resolved_model
        self.max_tool_turns = max_tool_turns
        self.thinking_level = thinking_level
        self.client = self._get_client_for_key(initial_key)

    def _get_client_for_key(self, api_key: str):
        """Reuses cached AsyncOpenAI client instance per API key."""
        if not api_key:
            return None
        if api_key not in self.__class__._client_pool:
            try:
                from openai import AsyncOpenAI
                timeout_sec = float((self.settings or {}).get("llm", {}).get("providers", {}).get("openrouter", {}).get("timeout_seconds", 120.0))
                self.__class__._client_pool[api_key] = AsyncOpenAI(
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1",
                    timeout=timeout_sec,
                    default_headers={
                        "HTTP-Referer": "https://monika.local",
                        "X-Title": "Monika MT5 Trading Agent",
                        "X-Session-ID": "tradeagent_live_session",
                    }
                )
            except ImportError:
                logger.warning("OpenAI package not installed. Run `pip install openai`.")
                return None
        return self.__class__._client_pool[api_key]

    def _is_key_in_cooldown(self, api_key: str) -> bool:
        """Memeriksa apakah api_key sedang dalam status cooldown untuk model ini atau secara global."""
        now = time.time()
        # 1. Global key-level cooldown
        if self.__class__._key_cooldowns.get(api_key, 0) > now:
            return True
        # 2. Model-specific cooldown (resolved model name)
        if self.__class__._model_key_cooldowns.get((api_key, self.model), 0) > now:
            return True
        # 3. Model-specific cooldown (raw model alias)
        if getattr(self, "raw_model_name", None) and self.__class__._model_key_cooldowns.get((api_key, self.raw_model_name), 0) > now:
            return True
        return False

    def _get_api_key(self) -> Optional[str]:
        """
        Mengambil API key valid:
        - Jika model gratis: berputar melintasi seluruh key (free keys + paid key) dengan cooldown filter per-model.
        - Jika model berbayar: HANYA menggunakan paid key dengan cooldown filter per-model.
        """
        if not self.is_free:
            # Model berbayar HANYA boleh memakai paid key
            paid_key = self._paid_key or self.api_key
            if not paid_key:
                logger.error(f"[OpenRouter] Paid OpenRouter model '{self.model}' requested but no paid API key configured.")
                return None
            if self._is_key_in_cooldown(paid_key):
                exp = max(
                    self.__class__._key_cooldowns.get(paid_key, 0),
                    self.__class__._model_key_cooldowns.get((paid_key, self.model), 0),
                    self.__class__._model_key_cooldowns.get((paid_key, getattr(self, "raw_model_name", self.model)), 0)
                )
                logger.warning(f"[OpenRouter] Paid OpenRouter key for model '{self.model}' is currently in cooldown until {exp:.0f}.")
                return None
            return paid_key

        # Model gratis boleh memakai seluruh kunci
        keys_pool = self._all_keys
        if not keys_pool:
            return self.api_key if self.api_key else None

        for _ in range(len(keys_pool)):
            key = keys_pool[self.__class__._key_index % len(keys_pool)]
            self.__class__._key_index += 1
            if not self._is_key_in_cooldown(key):
                return key

        logger.warning(f"[OpenRouter] All {len(keys_pool)} OpenRouter keys for free model '{self.model}' are in cooldown.")
        return None

    def _apply_reasoning_params(self, kwargs: dict) -> None:
        """
        OpenRouter reasoning parameters format.
        Mengonfigurasi objek reasoning: {"effort": "low"|"medium"|"high"} secara aman
        dan menerapkan dynamic adaptive floor pada max_tokens.
        """
        if self.thinking_level and str(self.thinking_level).lower() != "none":
            lvl = str(self.thinking_level).lower()
            effort_map = {
                "low": "low",
                "medium": "medium",
                "high": "high",
                "xhigh": "high",
                "extended": "high",
                "max": "high",
            }
            effort = effort_map.get(lvl, "medium")
            extra = kwargs.setdefault("extra_body", {})
            if isinstance(extra, dict):
                extra["reasoning"] = {
                    "effort": effort
                }
            
            # Calibrated reasoning token floor based on task role requirements
            floor_map = {
                "minimal": 1024,
                "low": 2048,
                "medium": 4096,
                "high": 8192,
                "xhigh": 16384,
                "extended": 16384,
                "max": 32768,
            }
            min_floor = floor_map.get(lvl, 2048)
            current_max = kwargs.get("max_tokens")
            if getattr(self, "is_free", False) and lvl in ("high", "xhigh", "extended", "max"):
                kwargs["max_tokens"] = 65536
            elif not current_max:
                kwargs["max_tokens"] = min_floor
            else:
                kwargs["max_tokens"] = max(current_max, min_floor)

    @classmethod
    def reset_cooldowns(cls, api_key: Optional[str] = None, model: Optional[str] = None) -> int:
        """Mereset status cooldown untuk seluruh atau kombinasi API key dan model tertentu."""
        cleared = 0
        if api_key and model:
            if (api_key, model) in cls._model_key_cooldowns:
                del cls._model_key_cooldowns[(api_key, model)]
                cleared += 1
            logger.info(f"[OpenRouter] Cooldown reset for key ({api_key[:8]}...) and model ({model}).")
            return cleared

        if api_key and not model:
            if api_key in cls._key_cooldowns:
                del cls._key_cooldowns[api_key]
                cleared += 1
            to_delete = [k for k in cls._model_key_cooldowns if k[0] == api_key]
            for k in to_delete:
                del cls._model_key_cooldowns[k]
                cleared += 1
            logger.info(f"[OpenRouter] Cooldown reset for key ({api_key[:8]}...) across all models ({cleared} entries).")
            return cleared

        if model and not api_key:
            to_delete = [k for k in cls._model_key_cooldowns if k[1] == model]
            for k in to_delete:
                del cls._model_key_cooldowns[k]
                cleared += 1
            logger.info(f"[OpenRouter] Cooldown reset for model ({model}) across all keys ({cleared} entries).")
            return cleared

        cleared = len(cls._key_cooldowns) + len(cls._model_key_cooldowns)
        cls._key_cooldowns.clear()
        cls._model_key_cooldowns.clear()
        cls._key_index = 0
        logger.info(f"[OpenRouter] All OpenRouter key cooldowns cleared ({cleared} entries freed).")
        return cleared

    @classmethod
    def get_cooldown_status(cls) -> dict[str, float]:
        """Mengembalikan sisa detik cooldown aktif per key dan per model."""
        now = time.time()
        status: dict[str, float] = {}
        for k, exp in cls._key_cooldowns.items():
            if exp > now:
                status[f"{k[:8]}...:*"] = max(0.0, exp - now)
        for (k, m), exp in cls._model_key_cooldowns.items():
            if exp > now:
                status[f"{k[:8]}...:{m}"] = max(0.0, exp - now)
        return status

    @classmethod
    def _handle_rate_limit_error(cls, api_key: str, error: Exception, method_name: str, model: Optional[str] = None) -> bool:
        """
        Klasifikasi presisi rate limit OpenRouter per-model & per-key:
        - Upstream shared pool / temporary model congestion / 502 / 503 / 529:
          60s cooldown ke SELURUH key untuk model ini. Return False (fail-fast, do NOT rotate keys).
        - RPD (24h daily quota):
          24h cooldown khusus (api_key, model) atau global key. Return True (izinkan rotasi ke key lain).
        - RPM / Burst / Generic 429:
          65s (atau retry hint) cooldown khusus (api_key, model). Return True (izinkan rotasi ke key lain).
        - 402 Insufficient credits:
          1h cooldown khusus (api_key, model). Return True jika free model, False jika paid.
        """
        err_str = str(error).lower()
        is_upstream = (
            "upstream" in err_str or
            "temporarily rate-limited" in err_str or
            "shared_pool" in err_str or
            "provider returned error" in err_str or
            "temporarily overloaded" in err_str or
            "502" in err_str or
            "503" in err_str or
            "529" in err_str or
            "bad gateway" in err_str or
            "service unavailable" in err_str or
            "no available model provider" in err_str
        )
        is_rpd = not is_upstream and any(k in err_str for k in [
            "daily limit", "requests per day", "daily quota",
            "free tier daily limit", "daily request limit",
            "exceeded your daily", "day limit reached"
        ])
        is_402 = "402" in err_str or "insufficient credits" in err_str or "credit" in err_str

        model_tag = f"model: {model}, " if model else ""
        key_tag = f"key: {api_key[:8]}..." if api_key else "key: unknown"

        if is_rpd:
            cooldown_sec = 86400.0
            if model:
                cls._model_key_cooldowns[(api_key, model)] = time.time() + cooldown_sec
            else:
                cls._key_cooldowns[api_key] = time.time() + cooldown_sec
            logger.error(f"[OpenRouter] Daily quota (RPD) exhausted in {method_name} ({model_tag}{key_tag}). Cooldown 24h.")
            return True
        elif is_402:
            cooldown_sec = 3600.0
            if model:
                cls._model_key_cooldowns[(api_key, model)] = time.time() + cooldown_sec
            else:
                cls._key_cooldowns[api_key] = time.time() + cooldown_sec
            logger.warning(f"[OpenRouter] Insufficient credits (402) in {method_name} ({model_tag}{key_tag}). Cooldown 1h.")
            return is_free_tier_model(model or "")
        elif is_upstream:
            cooldown_sec = 60.0
            all_known_keys = get_all_keys()
            if api_key and api_key not in all_known_keys:
                all_known_keys.append(api_key)
            if not all_known_keys:
                all_known_keys = [api_key] if api_key else []

            if model:
                # Terapkan cooldown ke SEMUA API key untuk model ini secara serentak
                for k in all_known_keys:
                    if k:
                        cls._model_key_cooldowns[(k, model)] = time.time() + cooldown_sec
            else:
                for k in all_known_keys:
                    if k:
                        cls._key_cooldowns[k] = time.time() + cooldown_sec

            logger.warning(f"[OpenRouter] Upstream provider temporarily congested/unavailable in {method_name} ({model_tag}{key_tag}). Model cooldown {cooldown_sec:.0f}s. Fail-fast to fallback.")
            return False  # Do NOT rotate keys for upstream server errors
        else:
            cooldown_sec = 65.0
            import re
            m = re.search(r"try again in ([\d\.]+)s", err_str) or re.search(r"retry after (\d+)", err_str)
            if m:
                try:
                    cooldown_sec = float(m.group(1)) + 5.0
                except (ValueError, TypeError):
                    cooldown_sec = 65.0
            if model:
                cls._model_key_cooldowns[(api_key, model)] = time.time() + cooldown_sec
            else:
                cls._key_cooldowns[api_key] = time.time() + cooldown_sec
            logger.warning(f"[OpenRouter] Rate limit hit in {method_name} ({model_tag}{key_tag}). Cooldown {cooldown_sec:.0f}s.")
            return True

    async def generate(self, prompt: str, system: Optional[Any] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[str]:
        attempts = max(1, len(self._all_keys)) if self.is_free else 1
        for attempt in range(attempts):
            api_key = self._get_api_key()
            if not api_key:
                return None
            if not await _openrouter_limiter.try_acquire(self.model, api_key=api_key):
                logger.warning(f"[OpenRouter] Rate limiter reject for key {api_key[:8]}..., trying next key")
                continue
            self.client = self._get_client_for_key(api_key)
            if not self.client:
                return None

            try:
                return await super().generate(prompt, system, temperature, max_tokens=max_tokens, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str or "502" in err_str or "503" in err_str or "529" in err_str or "bad gateway" in err_str or "service unavailable" in err_str or "provider returned error" in err_str:
                    should_rotate = self._handle_rate_limit_error(api_key, e, "generate", self.model)
                    if self.is_free and should_rotate:
                        continue
                    return None
                if "402" in err_str or "insufficient credits" in err_str:
                    if self.is_free:
                        should_rotate = self._handle_rate_limit_error(api_key, e, "generate", self.model)
                        if should_rotate:
                            continue
                    else:
                        logger.warning(f"[OpenRouter] 402 billing error on paid model '{self.model}'. Fail-fast to fallback.")
                    return None
                raise
        return None

    async def generate_content(self, system_prompt: str = "", user_message: str = "", response_schema: Optional[dict] = None,
                               temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[str]:
        attempts = max(1, len(self._all_keys)) if self.is_free else 1
        for attempt in range(attempts):
            api_key = self._get_api_key()
            if not api_key:
                return ""
            if not await _openrouter_limiter.try_acquire(self.model, api_key=api_key):
                logger.warning(f"[OpenRouter] Rate limiter reject for key {api_key[:8]}..., trying next key")
                continue
            self.client = self._get_client_for_key(api_key)
            if not self.client:
                return ""

            try:
                return await super().generate_content(system_prompt, user_message, response_schema, temperature, max_tokens)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str or "502" in err_str or "503" in err_str or "529" in err_str or "bad gateway" in err_str or "service unavailable" in err_str or "provider returned error" in err_str:
                    should_rotate = self._handle_rate_limit_error(api_key, e, "generate_content", self.model)
                    if self.is_free and should_rotate:
                        continue
                    return ""
                if "402" in err_str or "insufficient credits" in err_str:
                    if self.is_free:
                        should_rotate = self._handle_rate_limit_error(api_key, e, "generate_content", self.model)
                        if should_rotate:
                            continue
                    else:
                        logger.warning(f"[OpenRouter] 402 billing error in generate_content on paid model '{self.model}'. Fail-fast to fallback.")
                    return ""
                raise
        return ""

    async def classify_json(self, prompt: str, system_prompt: Optional[str] = None, schema: Optional[dict] = None,
                            temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[dict]:
        attempts = max(1, len(self._all_keys)) if self.is_free else 1
        for attempt in range(attempts):
            api_key = self._get_api_key()
            if not api_key:
                return None
            if not await _openrouter_limiter.try_acquire(self.model, api_key=api_key):
                logger.warning(f"[OpenRouter] Rate limiter reject for key {api_key[:8]}..., trying next key")
                continue
            self.client = self._get_client_for_key(api_key)
            if not self.client:
                return None

            try:
                return await super().classify_json(prompt, system_prompt, schema, temperature, max_tokens=max_tokens, **kwargs)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str or "502" in err_str or "503" in err_str or "529" in err_str or "bad gateway" in err_str or "service unavailable" in err_str or "provider returned error" in err_str:
                    should_rotate = self._handle_rate_limit_error(api_key, e, "classify_json", self.model)
                    if self.is_free and should_rotate:
                        continue
                    return None
                if "402" in err_str or "insufficient credits" in err_str:
                    if self.is_free:
                        should_rotate = self._handle_rate_limit_error(api_key, e, "classify_json", self.model)
                        if should_rotate:
                            continue
                    return None
                raise
        return None

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any):
        attempts = max(1, len(self._all_keys)) if self.is_free else 1
        for attempt in range(attempts):
            api_key = self._get_api_key()
            if not api_key:
                raise RuntimeError(f"[OpenRouter] No valid API key available for model '{self.model}'")
            if not await _openrouter_limiter.try_acquire(self.model, api_key=api_key):
                logger.warning(f"[OpenRouter] Rate limiter reject for key {api_key[:8]}..., trying next key")
                continue
            self.client = self._get_client_for_key(api_key)
            if not self.client:
                continue

            try:
                return await super().run_tool_agent(messages, tools, system_prompt)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str or "502" in err_str or "503" in err_str or "529" in err_str or "bad gateway" in err_str or "service unavailable" in err_str or "provider returned error" in err_str:
                    should_rotate = self._handle_rate_limit_error(api_key, e, "run_tool_agent", self.model)
                    if self.is_free and should_rotate:
                        continue
                    raise
                if "402" in err_str or "insufficient credits" in err_str:
                    if self.is_free:
                        should_rotate = self._handle_rate_limit_error(api_key, e, "run_tool_agent", self.model)
                        if should_rotate:
                            continue
                    raise
                raise
        raise RuntimeError(f"[OpenRouter] All API keys failed or rate-limited for model '{self.model}'")
