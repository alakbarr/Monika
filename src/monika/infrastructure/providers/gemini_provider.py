import asyncio
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, ClassVar, Literal, Optional

from dotenv import load_dotenv

from monika.infrastructure.llm.rate_limiting.gemini_rate_limiter import GeminiRateLimiter
from monika.infrastructure.llm.rate_limiting.http_retry import (
    APIStatusError,
    RateLimitError,
    fetch_with_retry,
    format_api_error_summary,
)
from monika.infrastructure.llm.rate_limiting.streaming import (
    StreamConfig,
    StreamResult,
    StreamSafetyTimeoutError,
    StreamTimeoutError,
    streaming_request,
)
from monika.core.security.log_redactor import mask_credential
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import TokenUsageLog
from monika.infrastructure.providers.base_provider import BaseLLMClient, MockBlock, MockResponse, _flatten_system_prompt

load_dotenv()
logger = logging.getLogger("TradingAgent.GeminiProvider")


def _gemini_stream_parser(chunk: dict, result: StreamResult) -> bool:
    if not isinstance(chunk, dict):
        return False
    candidates = chunk.get("candidates", [])
    if candidates:
        cand = candidates[0]
        content = cand.get("content", {})
        parts = content.get("parts", [])
        for part in parts:
            if part.get("thought") is True:
                result.thinking_text += part.get("text", "")
                ts = part.get("thoughtSignature") or part.get("thought_signature")
                if ts and not getattr(result, "thought_signature", None):
                    setattr(result, "thought_signature", ts)
            elif "text" in part:
                result.text += part.get("text", "")
            elif "functionCall" in part:
                fc = part["functionCall"]
                ts = part.get("thoughtSignature") or part.get("thought_signature") or fc.get("id")
                result.tool_calls.append(
                    {"name": fc.get("name", ""), "args": fc.get("args", {}), "thoughtSignature": ts}
                )
        finish = cand.get("finishReason", "")
        if finish:
            result.finish_reason = finish

    if "usageMetadata" in chunk:
        result.usage = chunk["usageMetadata"]

    return bool(result.finish_reason)


def _sanitize_schema_for_gemini(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return schema

    from monika.infrastructure.providers.schema_normalizer import inline_json_refs

    schema = inline_json_refs(schema)
    if not isinstance(schema, dict):
        return schema

    sanitized = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "$schema"):
            continue
        if k == "allOf" and isinstance(v, list):
            merged_properties = {}
            merged_required = set()
            for item in v:
                if isinstance(item, dict):
                    s_item = _sanitize_schema_for_gemini(item)
                    merged_properties.update(s_item.get("properties", {}))
                    merged_required.update(s_item.get("required", []))
            sanitized["type"] = "OBJECT"
            if merged_properties:
                sanitized["properties"] = merged_properties
            if merged_required:
                sanitized["required"] = sorted(merged_required)
            continue
        if k in ("anyOf", "oneOf") and isinstance(v, list):
            non_null_items = [
                item for item in v if isinstance(item, dict) and str(item.get("type", "")).lower() != "null"
            ]
            has_null = any(isinstance(item, dict) and str(item.get("type", "")).lower() == "null" for item in v)
            if len(non_null_items) == 1:
                inner = _sanitize_schema_for_gemini(non_null_items[0])
                for ik, iv in inner.items():
                    sanitized[ik] = iv
                if has_null:
                    sanitized["nullable"] = True
                continue
            elif len(non_null_items) > 1:
                sanitized["type"] = "STRING"
                types_str = ", ".join(str(it.get("type", "object")) for it in non_null_items)
                sanitized["description"] = (schema.get("description", "") + f" (Accepted types: {types_str})").strip()
                if has_null:
                    sanitized["nullable"] = True
                continue
        if k == "type" and isinstance(v, list):
            valid_types = [t for t in v if t != "null"]
            sanitized[k] = valid_types[0].upper() if valid_types else "STRING"
            if "null" in v:
                sanitized["nullable"] = True
            continue
        if k == "type" and isinstance(v, str):
            if "enum" in schema:
                sanitized[k] = "STRING"
            else:
                sanitized[k] = v.upper()
            continue
        if k == "enum" and isinstance(v, list):
            sanitized[k] = [str(x) for x in v]
            if "type" in sanitized:
                sanitized["type"] = "STRING"
            continue

        if isinstance(v, dict):
            sanitized[k] = _sanitize_schema_for_gemini(v)
        elif isinstance(v, list):
            sanitized[k] = [_sanitize_schema_for_gemini(item) if isinstance(item, dict) else item for item in v]
        else:
            sanitized[k] = v

    return sanitized


GEMINI_MODEL_ALIASES = {
    # Safe Gemini 3.x & 4.x Models (Active)
    "gemini-4-argon": "gemini-4-argon",
    "gemini-4": "gemini-4-argon",
    "gemini-3.5-flash": "gemini-3.5-flash",
    "gemini-3.6-flash": "gemini-3.6-flash",
    "gemini-3.7-flash": "gemini-3.7-flash",
    "gemini-3.8-flash": "gemini-3.8-flash",
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview": "gemini-3.1-pro-preview",
    "gemini-3.1-pro": "gemini-3.1-pro-preview",
    "gemini-pro": "gemini-3.1-pro-preview",
    "gemini-2.5-pro": "gemini-3.1-pro-preview",
    "gemini-1.5-pro": "gemini-3.1-pro-preview",
    "gemini-3-pro": "gemini-3.1-pro-preview",
    # Live & Audio Models
    "gemini-3.8-live": "gemini-3.8-live",
    "gemini-3.8-live-extended-thinking": "gemini-3.8-live-extended-thinking",
    "gemini-3.5-transcribe-live": "gemini-3.5-transcribe-live",
    "gemini-3-flash-live": "gemini-3-flash-live",
}

GEMINI_THINKING_LEVEL_MAP = {
    "none": "MINIMAL",
    "minimal": "MINIMAL",
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
    "xhigh": "HIGH",
    "max": "HIGH",
}


def _check_gemini_block(data: Any) -> Optional[str]:
    """Return block reason if response was blocked or empty, None if OK."""
    if not isinstance(data, dict):
        return "invalid_response_format"

    pf = data.get("promptFeedback", {})
    block_reason = pf.get("blockReason")
    if block_reason:
        return f"prompt_blocked:{block_reason}"

    candidates = data.get("candidates", [])
    if not candidates:
        return "empty_candidates"

    finish = candidates[0].get("finishReason", "")
    if finish in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "MALICIOUS"):
        return f"candidate_blocked:{finish}"

    return None


class GeminiProvider(BaseLLMClient):
    """
    Klien async untuk Gemini API.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    _key_cooldowns: dict[str, float] = {}
    _key_index: ClassVar[int] = 0

    def __init__(
        self,
        model: str,
        max_tokens: int = 65536,
        max_tool_turns: int = 15,
        thinking_level: str = "none",
        settings: Optional[dict] = None,
        temperature: float = 0.0,
        **kwargs,
    ):
        super().__init__(model, max_tokens, max_tool_turns, thinking_level, settings, temperature, **kwargs)
        self.provider_name = "gemini"
        self.resolved_model = GEMINI_MODEL_ALIASES.get(model, model)
        self.thinking_level = thinking_level or "none"
        self.resolved_thinking_level = GEMINI_THINKING_LEVEL_MAP.get(str(self.thinking_level).lower(), "MINIMAL")
        self.gemini_tier = kwargs.get("gemini_tier") or kwargs.get("tier")
        if not self.gemini_tier:
            if "pro" in self.model.lower() or "argon" in self.model.lower() or "ultra" in self.model.lower():
                self.gemini_tier = "paid"
            else:
                self.gemini_tier = "free"

        from monika.core.security.credential_vault import vault

        passed_free_keys = kwargs.get("free_api_keys")
        if passed_free_keys is not None:
            self.free_api_keys = list(passed_free_keys)
        else:
            api_keys_raw = vault.get_secret("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEYS", "")
            self.free_api_keys = [k.strip() for k in api_keys_raw.split(",") if k.strip()]
        cfg_api_key = (self.settings or {}).get("llm", {}).get("providers", {}).get("gemini", {}).get("api_key", "")
        paid_key = vault.get_secret("GEMINI_PAID_API_KEY") or os.getenv("GEMINI_PAID_API_KEY")
        if not paid_key:
            paid_key = vault.get_secret("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY", cfg_api_key)
        if not paid_key:
            try:
                from monika.infrastructure.auth.antigravity_bridge import resolve_antigravity_access_token

                paid_key = resolve_antigravity_access_token()
            except Exception:
                pass
        self.paid_api_key = paid_key
        self.api_key: Optional[str] = kwargs.get("api_key") or cfg_api_key or None
        if self.api_key and self.api_key.startswith("ya29."):
            self.paid_api_key = self.api_key

        if not self.free_api_keys and not self.paid_api_key and not self.api_key:
            logger.warning("No Gemini API keys set — Gemini tasks will be skipped")

        self._thinking_budgets = {
            "none": 0,
            "minimal": 0,
            "low": 1024,
            "medium": 2048,
            "high": 8192,
            "xhigh": 16384,
            "max": 32768,
        }
        self.thinking_budget = self._thinking_budgets.get(str(self.thinking_level).lower(), 0)

    def set_api_key(self, api_key: str) -> None:
        """Update active API key on this GeminiProvider instance."""
        super().set_api_key(api_key)
        self.api_key = api_key
        if api_key.startswith("ya29."):
            self.paid_api_key = api_key

    def _is_paid_key(self, api_key: Optional[str]) -> bool:
        """Menentukan apakah API key yang digunakan adalah GEMINI_PAID_API_KEY (berbayar)."""
        if not api_key:
            return False
        if api_key.startswith("ya29."):
            return True
        if self.paid_api_key and api_key == self.paid_api_key:
            return api_key not in self.free_api_keys
        return False

    @classmethod
    def rotate_api_key(cls) -> None:
        """Rotates active key index to the next free API key, called ONLY on 429/503 quota errors."""
        cls._key_index += 1

    def _get_api_key(self, sticky: bool = False) -> Optional[str]:
        now = time.time()
        is_paid_request = self.gemini_tier == "paid"

        if is_paid_request:
            # Check global budget circuit breaker
            try:
                from monika.core.analytics.cost_tracker import CostTracker

                if CostTracker.is_budget_paused_cached():
                    logger.warning(
                        f"[GeminiProvider] Global AI Budget is paused. Rejecting paid Gemini model/tier for '{self.model}'."
                    )
                    return None
            except Exception:
                pass

            try:
                from monika.infrastructure.auth.antigravity_bridge import resolve_antigravity_access_token

                token = resolve_antigravity_access_token(tier="paid", model=self.model)
                if token:
                    self.paid_api_key = token
                    return token
            except Exception:
                pass
            if self.paid_api_key and (
                self.paid_api_key not in self.__class__._key_cooldowns
                or self.__class__._key_cooldowns[self.paid_api_key] <= now
            ):
                return self.paid_api_key
            logger.warning(
                f"Model {self.model} called but GEMINI_PAID_API_KEY is empty or cooling down. Fallback to free key."
            )

        # 1. Sticky session mode (preserves per-key KV cache across turns)
        if sticky or getattr(self, "_sticky_session_key", None):
            sticky_key = getattr(self, "_sticky_session_key", None)
            if (
                sticky_key
                and (
                    sticky_key not in self.__class__._key_cooldowns or self.__class__._key_cooldowns[sticky_key] <= now
                )
                and (
                    not self.free_api_keys
                    or sticky_key == self.free_api_keys[GeminiProvider._key_index % len(self.free_api_keys)]
                )
            ):
                return sticky_key

            # Pick candidate key at GeminiProvider._key_index (or next available non-cooling) and pin it
            if self.free_api_keys:
                for offset in range(len(self.free_api_keys)):
                    candidate = self.free_api_keys[(GeminiProvider._key_index + offset) % len(self.free_api_keys)]
                    if (
                        candidate not in self.__class__._key_cooldowns
                        or self.__class__._key_cooldowns[candidate] <= now
                    ):
                        GeminiProvider._key_index = (GeminiProvider._key_index + offset) % len(self.free_api_keys)
                        self._sticky_session_key = candidate
                        return candidate

            if self.api_key and (
                self.api_key not in self.__class__._key_cooldowns or self.__class__._key_cooldowns[self.api_key] <= now
            ):
                self._sticky_session_key = self.api_key
                return self.api_key

        # 2. Round-robin mode (default outside pinned sessions, skipping cooldowns)
        if self.free_api_keys:
            for _ in range(len(self.free_api_keys)):
                key = self.free_api_keys[GeminiProvider._key_index % len(self.free_api_keys)]
                GeminiProvider._key_index += 1
                if key not in self.__class__._key_cooldowns or self.__class__._key_cooldowns[key] <= now:
                    return key

        # 3. Check explicit self.api_key if provided and not in active cooldown
        if self.api_key and (
            self.api_key not in self.__class__._key_cooldowns or self.__class__._key_cooldowns[self.api_key] <= now
        ):
            return self.api_key

        # 3. Rotate through Antigravity Free Accounts Pool (9 free accounts)
        try:
            from monika.infrastructure.auth.antigravity_bridge import resolve_antigravity_access_token

            pool_token = resolve_antigravity_access_token(tier="free", model=self.model)
            if pool_token:
                return pool_token
        except Exception:
            pass

        # 4. If all free keys are in cooldown, pick the one that expires earliest
        if self.free_api_keys:
            earliest_key = min(self.free_api_keys, key=lambda k: self.__class__._key_cooldowns.get(k, 0))
            return earliest_key

        # 5. Fallback to paid key if available
        if self.paid_api_key and (
            self.paid_api_key not in self.__class__._key_cooldowns
            or self.__class__._key_cooldowns[self.paid_api_key] <= now
        ):
            return self.paid_api_key

        return self.api_key or self.paid_api_key

    @classmethod
    def _is_transient_error(cls, error: Any) -> bool:
        """Menentukan apakah error merupakan error sementara (overload / rate limit / 5xx / 429) yang layak di-cooldown & retry/failover."""
        if isinstance(error, RateLimitError):
            return True
        status = getattr(error, "status", None) or getattr(error, "status_code", None)
        if status in (429, 500, 502, 503, 504, 529):
            return True
        err_str = str(getattr(error, "body", "") or error).lower()
        return any(
            k in err_str
            for k in [
                "429",
                "503",
                "502",
                "504",
                "529",
                "rate limit",
                "resource_exhausted",
                "unavailable",
                "high demand",
                "spikes in demand",
                "overloaded",
                "capacity",
                "temporarily unavailable",
                "try again later",
                "service unavailable",
            ]
        )

    @classmethod
    def _handle_rate_limit_error(cls, api_key: str, error: Exception, method_name: str = "generate") -> None:
        """
        Klasifikasi presisi rate limit & transient overload Google Gemini API:
        - RPD (24h): Hanya jika respon eksplisit memuat indikator limit/kuota harian.
        - Server Overload / High Demand (HTTP 503 / 502 / 504 / 529 / UNAVAILABLE): Cooldown 30s + rotate key.
        - Retry-After header / body delay hint: Cooldown dinamis + 2.0s buffer.
        - RPM / TPM / Burst / Capacity Overload (65s): Default untuk seluruh HTTP 429 / RESOURCE_EXHAUSTED.
        """
        body = getattr(error, "body", "") or str(error)
        body_lower = body.lower()
        status = getattr(error, "status", None) or getattr(error, "status_code", None)

        is_rpd = any(
            k in body_lower
            for k in [
                "requests per day",
                "per day",
                "rpd",
                "daily quota",
                "daily limit",
                "generatecontent requests per day",
                "exceeded your daily",
            ]
        )
        if is_rpd:
            cls._key_cooldowns[api_key] = time.time() + 86400
            if api_key.startswith("ya29."):
                try:
                    from monika.infrastructure.auth.antigravity_bridge import mark_antigravity_account_cooldown

                    mark_antigravity_account_cooldown(api_key, 86400.0)
                except Exception:
                    pass
            logger.error(f"Gemini key hit RPD quota in {method_name} ({mask_credential(api_key)}). Cooldown 24h.")
            return

        is_overload = status in (500, 502, 503, 504, 529) or any(
            k in body_lower
            for k in [
                "503",
                "502",
                "504",
                "529",
                "unavailable",
                "high demand",
                "spikes in demand",
                "overloaded",
                "service unavailable",
                "temporarily unavailable",
                "capacity",
            ]
        )

        retry_after = getattr(error, "retry_after", None)
        if retry_after is not None and retry_after > 0:
            cooldown_sec = float(retry_after) + 2.0
        else:
            m = re.search(r"try again in ([\d\.]+)s", body_lower) or re.search(r"retry after (\d+)", body_lower)
            if m:
                try:
                    cooldown_sec = float(m.group(1)) + 2.0
                except ValueError, TypeError:
                    cooldown_sec = 30.0 if is_overload else 65.0
            elif is_overload:
                cooldown_sec = 30.0
            else:
                cooldown_sec = 65.0

        cls._key_cooldowns[api_key] = time.time() + cooldown_sec
        cls.rotate_api_key()
        if api_key.startswith("ya29."):
            try:
                from monika.infrastructure.auth.antigravity_bridge import mark_antigravity_account_cooldown

                mark_antigravity_account_cooldown(api_key, cooldown_sec)
            except Exception:
                pass

        clean_detail = format_api_error_summary(status or (503 if is_overload else 429), body)
        if is_overload:
            logger.warning(
                f"Gemini key ({mask_credential(api_key)}) hit transient overload/high demand in {method_name} "
                f"({clean_detail}). Cooldown {cooldown_sec:.1f}s, attempting next key/failover."
            )
        else:
            logger.warning(
                f"Gemini key ({mask_credential(api_key)}) hit RPM/TPM limit in {method_name} "
                f"({clean_detail}). Cooldown {cooldown_sec:.1f}s."
            )

    def _build_stream_config(self) -> StreamConfig:
        provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get("gemini", {})
        stream_cfg = provider_cfg.get("streaming", {})
        return StreamConfig(
            idle_timeout=float(stream_cfg.get("idle_timeout_seconds", 45.0)),
            safety_timeout=float(stream_cfg.get("safety_timeout_seconds", 600.0)),
            first_chunk_timeout=float(stream_cfg.get("first_chunk_timeout_seconds", 90.0)),
        )

    def set_thinking_budget(self, budget: int) -> None:
        """Sets thinking budget and resolves corresponding Gemini thinking level."""
        if budget == 0:
            self.thinking_budget = 0
            self.thinking_level = "none"
            self.resolved_thinking_level = "MINIMAL"
        else:
            try:
                from monika.infrastructure.llm.adaptive_thinking import QuantizedThinkingAllocator

                quantized_budget = QuantizedThinkingAllocator.quantize(budget)
            except Exception:
                quantized_budget = 4096 if budget >= 4000 else 1024
            self.thinking_budget = quantized_budget
            if quantized_budget >= 10000:
                self.resolved_thinking_level = "HIGH"
            elif quantized_budget >= 4000:
                self.resolved_thinking_level = "MEDIUM"
            else:
                self.resolved_thinking_level = "LOW"
            self.thinking_level = self.resolved_thinking_level.lower()

    def _build_thinking_config(self) -> Optional[dict]:
        """
        Builds model-compatible thinkingConfig for Google Gemini API.
        - Gemini 2.5 series models use 'thinkingBudget' (integer).
        - Gemini 3.x / 4.x (Argon) series models use 'thinkingLevel' (Enum: LOW/MEDIUM/HIGH/MINIMAL).
        - Legacy models (1.5/2.0) omit thinkingConfig to avoid 400 Bad Request.
        """
        resolved = str(getattr(self, "resolved_model", None) or self.model).lower()
        is_thinking_off = str(self.thinking_level or "none").lower() in ("none", "off")

        # Models with native thinking support: 2.5, 3.x, 4.x, argon
        if not any(k in resolved for k in ("2.5", "3.", "3-", "4.", "4-", "argon")):
            return None

        if "2.5" in resolved:
            if is_thinking_off:
                return {"thinkingBudget": 0}
            return {"thinkingBudget": max(0, self.thinking_budget or 0)}

        if "3.8" in resolved and is_thinking_off:
            return None

        if is_thinking_off:
            return {"thinkingLevel": "MINIMAL"}
        return {"thinkingLevel": self.resolved_thinking_level}

    async def generate(
        self,
        prompt: str,
        system: Any = "",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_schema: Optional[dict] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        if not system and "system_prompt" in kwargs:
            system = kwargs.pop("system_prompt")

        static_sys = system
        dynamic_sys = ""
        if isinstance(system, tuple) and len(system) >= 2:
            static_sys = system[0]
            dynamic_sys = str(system[1]).strip() if system[1] else ""

        flat_sys = _flatten_system_prompt(static_sys)
        actual_prompt = f"{prompt}\n\n{dynamic_sys}" if dynamic_sys else prompt
        contents = [{"role": "user", "parts": [{"text": actual_prompt}]}]
        is_thinking_none = str(self.thinking_level or "none").lower() in ("none", "off")
        if max_tokens is not None:
            # Caller requested a specific output budget.
            # If thinking is active, add headroom so thinking does not eat into candidate output quota.
            if not is_thinking_none:
                tb = getattr(self, "thinking_budget", None)
                if getattr(self, "resolved_thinking_level", "") in ("HIGH", "XHIGH", "MAX"):
                    actual_budget = max(tb if tb is not None else 0, 8192)
                elif getattr(self, "resolved_thinking_level", "") == "MEDIUM":
                    actual_budget = max(tb if tb is not None else 0, 4096)
                else:
                    actual_budget = max(tb if tb is not None else 0, 2048)
                eff_max_tokens = max(max_tokens + actual_budget, max_tokens)
            else:
                eff_max_tokens = max_tokens
        else:
            # Fall back to provider default max_tokens (typically 36000 or 65536)
            eff_max_tokens = self.max_tokens or 36000
            if not is_thinking_none:
                tb = getattr(self, "thinking_budget", None)
                if getattr(self, "resolved_thinking_level", "") in ("HIGH", "XHIGH", "MAX"):
                    actual_budget = max(tb if tb is not None else 0, 8192)
                elif getattr(self, "resolved_thinking_level", "") == "MEDIUM":
                    actual_budget = max(tb if tb is not None else 0, 4096)
                else:
                    actual_budget = max(tb if tb is not None else 0, 2048)
                eff_max_tokens = max(eff_max_tokens, actual_budget + 8192, 16384)

        eff_max_tokens = min(eff_max_tokens, 65536)
        eff_temp = temperature if temperature is not None else self.default_temperature
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": eff_max_tokens,
                "temperature": eff_temp,
            },
        }
        thinking_cfg = self._build_thinking_config()
        if thinking_cfg is not None:
            payload["generationConfig"]["thinkingConfig"] = thinking_cfg

        if flat_sys:
            payload["systemInstruction"] = {"parts": [{"text": flat_sys}]}

        if response_schema:
            payload["generationConfig"]["responseMimeType"] = "application/json"
            payload["generationConfig"]["responseSchema"] = _sanitize_schema_for_gemini(response_schema)

        provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get("gemini", {})
        use_streaming = provider_cfg.get("streaming", {}).get("enabled", bool(self.settings))

        endpoint = "streamGenerateContent?alt=sse" if use_streaming else "generateContent"
        url = f"{self.BASE_URL}/{self.resolved_model}:{endpoint}"

        async with get_session() as session:
            if not await GeminiRateLimiter(session).try_acquire(self.model):
                logger.warning(f"Gemini {self.model} quota exhausted.")
                return None

        stream_config = self._build_stream_config()
        timeout_sec = float(provider_cfg.get("timeout_seconds", 120.0))
        max_attempts = min(max(len(self.free_api_keys) if self.free_api_keys else 1, 1), 5)
        for attempt in range(max_attempts):
            api_key = self._get_api_key(sticky=True)
            if not api_key:
                logger.error("No Gemini API key available.")
                return None

            if api_key.startswith("ya29."):
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            else:
                headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

            try:
                is_paid_attempt = self._is_paid_key(api_key)
                is_free_attempt = not is_paid_attempt
                if use_streaming:
                    stream_res = await streaming_request(
                        url,
                        payload=payload,
                        headers=headers,
                        config=stream_config,
                        parser=_gemini_stream_parser,
                        model_name=self.model,
                    )
                    usage = stream_res.usage or {}
                    inp = usage.get("promptTokenCount", 0)
                    outp = usage.get("candidatesTokenCount", 0)
                    cached = usage.get("cachedContentTokenCount", 0) or 0
                    thoughts = usage.get("thoughtsTokenCount", 0) or 0
                    if inp > 0 or outp > 0:
                        await self._save_token_usage(
                            self.model,
                            "generate",
                            inp,
                            outp,
                            cached_tokens=cached,
                            thinking_tokens=thoughts,
                            is_direct_free_tier=is_free_attempt,
                            is_paid=is_paid_attempt,
                            cost_source="gemini_paid_exact" if is_paid_attempt else "gemini_free_tier",
                            exact_cost=0.0 if is_free_attempt else None,
                        )

                    if stream_res.finish_reason == "MAX_TOKENS":
                        logger.warning(
                            f"Gemini {self.model} output truncated by token limit (finishReason=MAX_TOKENS, maxOutputTokens={eff_max_tokens}, outp={outp}, think={thoughts})"
                        )
                        if self.resolved_thinking_level != "MINIMAL":
                            is_v25 = "2.5" in str(self.model).lower()
                            rec_thinking = {"thinkingBudget": 0} if is_v25 else {"thinkingLevel": "MINIMAL"}
                            logger.info(
                                f"Gemini {self.model} attempting auto-recovery retry with {rec_thinking} (output truncated by token limit)..."
                            )
                            recovery_payload = dict(payload)
                            recovery_payload["generationConfig"] = dict(payload["generationConfig"])
                            recovery_payload["generationConfig"]["thinkingConfig"] = rec_thinking
                            recovery_payload["generationConfig"]["maxOutputTokens"] = (
                                65536  # Max capacity saat recovery
                            )
                            try:
                                rec_res = await streaming_request(
                                    url,
                                    payload=recovery_payload,
                                    headers=headers,
                                    config=stream_config,
                                    parser=_gemini_stream_parser,
                                    model_name=self.model,
                                )
                                if rec_res and rec_res.text:
                                    rec_usage = rec_res.usage or {}
                                    rec_inp = rec_usage.get("promptTokenCount", 0)
                                    rec_outp = rec_usage.get("candidatesTokenCount", 0)
                                    rec_cached = rec_usage.get("cachedContentTokenCount", 0) or 0
                                    rec_thoughts = rec_usage.get("thoughtsTokenCount", 0) or 0
                                    if rec_inp > 0 or rec_outp > 0:
                                        await self._save_token_usage(
                                            self.model,
                                            "generate",
                                            rec_inp,
                                            rec_outp,
                                            cached_tokens=rec_cached,
                                            thinking_tokens=rec_thoughts,
                                            is_direct_free_tier=is_free_attempt,
                                            is_paid=is_paid_attempt,
                                            cost_source="gemini_paid_exact" if is_paid_attempt else "gemini_free_tier",
                                            exact_cost=0.0 if is_free_attempt else None,
                                        )
                                    return rec_res.text
                            except Exception as rec_err:
                                logger.warning(f"Gemini auto-recovery failed: {rec_err}")
                        elif outp > 0 and stream_res.text:
                            # Output terpotong tapi thinking kecil → kembalikan partial agar tidak semua hilang
                            logger.warning(
                                f"Gemini {self.model} partial output returned (think={thoughts}, outp={outp}). Recovery not applicable."
                            )
                            return stream_res.text

                    if stream_res.text:
                        return stream_res.text
                else:
                    data = await fetch_with_retry(
                        url,
                        method="POST",
                        json=payload,
                        headers=headers,
                        timeout=int(timeout_sec),
                        max_retries=1,
                        raise_on_429=True,
                        use_circuit_breaker=False,
                    )

                    if data and isinstance(data, dict):
                        block = _check_gemini_block(data)
                        if block:
                            logger.warning(f"Gemini {self.model} generate blocked/empty: {block}")
                            continue

                        usage = data.get("usageMetadata", {})
                        inp = usage.get("promptTokenCount", 0)
                        outp = usage.get("candidatesTokenCount", 0)
                        cached = usage.get("cachedContentTokenCount", 0) or 0
                        thoughts = usage.get("thoughtsTokenCount", 0) or 0
                        if inp > 0 or outp > 0:
                            await self._save_token_usage(
                                self.model,
                                "generate",
                                inp,
                                outp,
                                cached_tokens=cached,
                                thinking_tokens=thoughts,
                                is_direct_free_tier=is_free_attempt,
                                is_paid=is_paid_attempt,
                                cost_source="gemini_paid_exact" if is_paid_attempt else "gemini_free_tier",
                                exact_cost=0.0 if is_free_attempt else None,
                            )

                        candidates = data.get("candidates", [])
                        if candidates:
                            finish_reason = candidates[0].get("finishReason", "")
                            if finish_reason == "MAX_TOKENS":
                                logger.warning(
                                    f"Gemini {self.model} output truncated by token limit (finishReason=MAX_TOKENS, maxOutputTokens={eff_max_tokens}, outp={outp}, think={thoughts})"
                                )
                                if self.resolved_thinking_level != "MINIMAL":
                                    is_v25 = "2.5" in str(self.model).lower()
                                    rec_thinking = {"thinkingBudget": 0} if is_v25 else {"thinkingLevel": "MINIMAL"}
                                    logger.info(
                                        f"Gemini {self.model} attempting auto-recovery retry with {rec_thinking}..."
                                    )
                                    recovery_payload = dict(payload)
                                    recovery_payload["generationConfig"] = dict(payload["generationConfig"])
                                    recovery_payload["generationConfig"]["thinkingConfig"] = rec_thinking
                                    recovery_payload["generationConfig"]["maxOutputTokens"] = 65536
                                    try:
                                        rec_data = await fetch_with_retry(
                                            url,
                                            method="POST",
                                            json=recovery_payload,
                                            headers=headers,
                                            timeout=int(timeout_sec),
                                            max_retries=1,
                                            raise_on_429=True,
                                            use_circuit_breaker=False,
                                        )
                                        if rec_data and isinstance(rec_data, dict):
                                            rec_cands = rec_data.get("candidates", [])
                                            if rec_cands:
                                                for p in rec_cands[0].get("content", {}).get("parts", []):
                                                    if "text" in p and p.get("thought") is not True:
                                                        return p["text"]
                                    except Exception as rec_err:
                                        logger.warning(f"Gemini auto-recovery failed: {rec_err}")

                            content = candidates[0].get("content", {})
                            parts = content.get("parts", [])
                            for part in parts:
                                if "text" in part and part.get("thought") is not True:
                                    return part["text"]

            except RateLimitError as e:
                self._handle_rate_limit_error(api_key, e, "generate")
                continue
            except (StreamTimeoutError, StreamSafetyTimeoutError) as e:
                logger.warning(f"Gemini generate streaming timeout on {self.model}: {e}")
                self._key_cooldowns[api_key] = time.time() + 15.0
                if use_streaming:
                    try:
                        logger.info(f"Gemini {self.model} attempting non-streaming fallback for generate...")
                        non_stream_url = f"{self.BASE_URL}/{self.resolved_model}:generateContent"
                        data = await fetch_with_retry(
                            non_stream_url,
                            method="POST",
                            json=payload,
                            headers=headers,
                            timeout=int(timeout_sec),
                            max_retries=1,
                            raise_on_429=True,
                            use_circuit_breaker=False,
                        )
                        if data and isinstance(data, dict):
                            candidates = data.get("candidates", [])
                            if candidates:
                                for part in candidates[0].get("content", {}).get("parts", []):
                                    if "text" in part and part.get("thought") is not True:
                                        return part["text"]
                    except Exception as fb_err:
                        logger.warning(f"Gemini generate non-streaming fallback failed: {fb_err}")
                if attempt + 1 < max_attempts:
                    continue
                raise
            except Exception as e:
                if self._is_transient_error(e):
                    self._handle_rate_limit_error(api_key, e, "generate")
                    continue
                clean_msg = format_api_error_summary(getattr(e, "status", 500), getattr(e, "body", "") or str(e))
                logger.warning(
                    f"Gemini generate attempt {attempt + 1} failed with key ({mask_credential(api_key)}): {clean_msg}"
                )

        return None

    async def classify_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[dict]:
        from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

        anchored_sys = CacheBreakpointManager.pad_system_prompt_to_threshold(
            system_prompt or "", model_name=self.model, provider_name="gemini"
        )
        full_prompt = prompt if schema else f"{prompt}\n\nRespond with ONLY valid JSON, no markdown, no explanation."
        result = await self.generate(
            full_prompt,
            system=anchored_sys,
            response_schema=schema,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        if not result:
            return None
        from monika.infrastructure.providers.base_provider import extract_and_parse_json

        parsed = extract_and_parse_json(result)
        if parsed is not None:
            return parsed
        logger.warning(f"Gemini classify_json: parse failed (schema={bool(schema)}): {result[:200]}")
        return None

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any) -> MockResponse:
        gemini_tools = []
        if tools:
            from monika.infrastructure.providers.schema_normalizer import ToolSchemaNormalizer

            gemini_tools = ToolSchemaNormalizer.to_gemini(tools)

        gemini_contents = []
        static_sys = system_prompt
        dynamic_note = ""
        if isinstance(system_prompt, tuple) and len(system_prompt) >= 2:
            static_sys = system_prompt[0]
            dynamic_note = str(system_prompt[1]).strip() if system_prompt[1] else ""
        flat_sys = _flatten_system_prompt(static_sys)

        tool_id_to_name = {}

        for m in messages:
            role = "user" if m.get("role") in ("user", "tool") else "model"
            parts = []

            # Handle OpenAI-style tool message (role: 'tool')
            if m.get("role") == "tool":
                tool_call_id = m.get("tool_call_id")
                tool_name = m.get("name") or tool_id_to_name.get(tool_call_id, "unknown_tool")
                content_val = m.get("content", "")
                parsed_content = content_val
                if isinstance(content_val, str):
                    try:
                        parsed_content = json.loads(content_val)
                    except Exception:
                        parsed_content = {"result": content_val}
                elif not isinstance(content_val, dict):
                    parsed_content = {"result": str(content_val)}
                parts.append(
                    {
                        "functionResponse": {
                            "name": tool_name,
                            "response": {"name": tool_name, "content": parsed_content},
                        }
                    }
                )
            # Handle OpenAI-style assistant message with tool_calls
            elif m.get("tool_calls"):
                for tc in m["tool_calls"]:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args = fn.get("arguments", {})
                    if isinstance(fn_args, str):
                        try:
                            fn_args = json.loads(fn_args)
                        except Exception:
                            fn_args = {}
                    tc_id = tc.get("id")
                    if tc_id:
                        tool_id_to_name[tc_id] = fn_name
                    parts.append({"functionCall": {"name": fn_name, "args": fn_args}})
                if m.get("content"):
                    parts.insert(0, {"text": str(m["content"])})
            else:
                raw_blocks = m.get("content")
                blocks = (
                    raw_blocks
                    if isinstance(raw_blocks, list)
                    else ([{"type": "text", "text": str(raw_blocks)}] if raw_blocks is not None else [])
                )
                for block in blocks:
                    b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", "text")
                    if b_type == "tool_result":
                        content_val = (
                            block.get("content", "") if isinstance(block, dict) else getattr(block, "content", "")
                        )
                        tool_use_id = (
                            block.get("tool_use_id") if isinstance(block, dict) else getattr(block, "tool_use_id", None)
                        )
                        tool_name = tool_id_to_name.get(tool_use_id, "unknown_tool")
                        parsed_content = content_val
                        if isinstance(content_val, str):
                            try:
                                parsed_content = json.loads(content_val)
                            except Exception:
                                parsed_content = {"result": content_val}
                        elif not isinstance(content_val, dict):
                            parsed_content = {"result": str(content_val)}

                        part_dict: dict[str, Any] = {
                            "functionResponse": {
                                "name": tool_name,
                                "response": {"name": tool_name, "content": parsed_content},
                            }
                        }
                        if tool_use_id:
                            str_id = str(tool_use_id)
                            # thoughtSignature harus dari Gemini model response (bukan ID buatan kita).
                            # Gemini native signature: tidak memiliki prefix "call_", "toolu_", atau "gemini_tool_fallback_".
                            # ID "call_" = OpenAI format, "toolu_" = Anthropic format — keduanya bukan Gemini thought_signature.
                            # Tanpa thought_signature yang valid, Gemini 3.x akan return 400 pada multi-turn tool calling.
                            is_synthetic_id = (
                                str_id.startswith("gemini_tool_fallback_")
                                or str_id.startswith("call_")
                                or str_id.startswith("toolu_")
                            )
                            if not is_synthetic_id:
                                # ID ini berasal dari Gemini (thought_signature asli) — WAJIB dipass kembali
                                part_dict["thoughtSignature"] = str_id
                        parts.append(part_dict)
                    elif b_type == "tool_use":
                        name_val = block.get("name") if isinstance(block, dict) else getattr(block, "name", "")
                        input_val = block.get("input") if isinstance(block, dict) else getattr(block, "input", {})
                        tool_id = block.get("id") if isinstance(block, dict) else getattr(block, "id", None)
                        if tool_id:
                            tool_id_to_name[tool_id] = name_val
                        part_dict: dict[str, Any] = {"functionCall": {"name": name_val, "args": input_val}}
                        if tool_id:
                            str_id = str(tool_id)
                            # Sama seperti tool_result: hanya pass thought_signature jika ID adalah Gemini native signature
                            is_synthetic_id = (
                                str_id.startswith("gemini_tool_fallback_")
                                or str_id.startswith("call_")
                                or str_id.startswith("toolu_")
                            )
                            if not is_synthetic_id:
                                part_dict["thoughtSignature"] = str_id
                        parts.append(part_dict)
                    elif b_type in ("thinking", "thought"):
                        thinking_txt = (
                            block.get("thinking", "") if isinstance(block, dict) else getattr(block, "thinking", "")
                        )
                        if not thinking_txt:
                            thinking_txt = (
                                block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
                            )
                        sig = block.get("signature", "") if isinstance(block, dict) else getattr(block, "signature", "")
                        if not sig:
                            sig = (
                                block.get("thought_signature", "")
                                if isinstance(block, dict)
                                else getattr(block, "thought_signature", "")
                            )
                        if not sig:
                            sig = (
                                block.get("thoughtSignature", "")
                                if isinstance(block, dict)
                                else getattr(block, "thoughtSignature", "")
                            )
                        if thinking_txt:
                            part_dict: dict[str, Any] = {"text": str(thinking_txt), "thought": True}
                            if sig:
                                import base64

                                if isinstance(sig, bytes):
                                    part_dict["thoughtSignature"] = base64.b64encode(sig).decode("utf-8")
                                else:
                                    str_sig = str(sig).strip()
                                    try:
                                        base64.b64decode(str_sig, validate=True)
                                        part_dict["thoughtSignature"] = str_sig
                                    except Exception:
                                        part_dict["thoughtSignature"] = base64.b64encode(
                                            str_sig.encode("utf-8")
                                        ).decode("utf-8")
                            parts.append(part_dict)
                    elif b_type == "text":
                        text_val = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                        parts.append({"text": text_val})
                    elif b_type == "image":
                        source = block.get("source", {}) if isinstance(block, dict) else getattr(block, "source", {})
                        if isinstance(source, dict):
                            media_type = str(source.get("media_type", "image/jpeg"))
                            data = str(source.get("data", ""))
                            if data:
                                parts.append({"inlineData": {"mimeType": media_type, "data": data}})
                    elif b_type == "image_url":
                        img_url_data = (
                            block.get("image_url", {}) if isinstance(block, dict) else getattr(block, "image_url", {})
                        )
                        url = img_url_data.get("url", "") if isinstance(img_url_data, dict) else str(img_url_data)
                        if url.startswith("data:") and ";base64," in url:
                            header, b64_data = url.split(";base64,", 1)
                            mime_type = header[5:] if header.startswith("data:") else "image/jpeg"
                            if b64_data:
                                parts.append({"inlineData": {"mimeType": mime_type, "data": b64_data}})
            if parts:
                gemini_contents.append({"role": role, "parts": parts})

        if dynamic_note:
            injected = False
            for gc in reversed(gemini_contents):
                if gc.get("role") == "user":
                    user_parts = list(gc.get("parts", []))
                    for i in range(len(user_parts) - 1, -1, -1):
                        p = user_parts[i]
                        if isinstance(p, dict) and "text" in p and not p.get("thought"):
                            user_parts[i] = dict(p, text=f"{p['text']}\n\n{dynamic_note}")
                            injected = True
                            break
                        elif hasattr(p, "text") and not getattr(p, "thought", False):
                            user_parts[i] = {"text": f"{getattr(p, 'text')}\n\n{dynamic_note}"}
                            injected = True
                            break
                    if injected:
                        gc["parts"] = user_parts
                        break
            if not injected and gemini_contents:
                gemini_contents[-1]["parts"] = list(gemini_contents[-1].get("parts", [])) + [{"text": dynamic_note}]

        eff_max_tokens = self.max_tokens or 36000
        is_thinking_active = str(self.thinking_level or "none").lower() not in ("none", "off")
        if is_thinking_active:
            tb = getattr(self, "thinking_budget", 0) or 0
            if getattr(self, "resolved_thinking_level", "") in ("HIGH", "XHIGH", "MAX"):
                min_headroom = max(tb, 8192)
            elif getattr(self, "resolved_thinking_level", "") == "MEDIUM":
                min_headroom = max(tb, 4096)
            else:
                min_headroom = max(tb, 2048)
            eff_max_tokens = max(eff_max_tokens + min_headroom, eff_max_tokens, min_headroom + 4096, 12288)

        eff_max_tokens = min(eff_max_tokens, 65536)

        payload = {
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": self.default_temperature,
                "maxOutputTokens": eff_max_tokens,
            },
        }
        thinking_cfg = self._build_thinking_config()
        if thinking_cfg is not None:
            payload["generationConfig"]["thinkingConfig"] = thinking_cfg
        if flat_sys:
            from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

            anchored_sys = CacheBreakpointManager.pad_system_prompt_to_threshold(
                flat_sys, model_name=self.model, provider_name="gemini"
            )
            payload["systemInstruction"] = {"parts": [{"text": anchored_sys}]}
        if gemini_tools:
            payload["tools"] = gemini_tools

        provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get("gemini", {})
        use_streaming = provider_cfg.get("streaming", {}).get("enabled", bool(self.settings))

        endpoint = "streamGenerateContent?alt=sse" if use_streaming else "generateContent"
        url = f"{self.BASE_URL}/{self.resolved_model}:{endpoint}"

        async with get_session() as session:
            if not await GeminiRateLimiter(session).try_acquire(self.model):
                raise Exception(f"Gemini {self.model} quota exhausted.")

        data = None
        stream_res = None
        last_req_err = None
        api_key = ""
        stream_config = self._build_stream_config()
        headers: dict[str, str] = {}
        timeout_sec = float(provider_cfg.get("timeout_seconds", 120.0))
        max_attempts = min(max(len(self.free_api_keys) if self.free_api_keys else 1, 1), 5)
        for attempt in range(max_attempts):
            api_key = self._get_api_key(sticky=True)
            if not api_key:
                break

            try:
                if api_key.startswith("ya29."):
                    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                else:
                    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
                if use_streaming:
                    stream_res = await streaming_request(
                        url,
                        payload=payload,
                        headers=headers,
                        config=stream_config,
                        parser=_gemini_stream_parser,
                        model_name=self.model,
                    )
                    break
                else:
                    data = await fetch_with_retry(
                        url,
                        method="POST",
                        json=payload,
                        headers=headers,
                        timeout=int(timeout_sec),
                        max_retries=1,
                        raise_on_429=True,
                        use_circuit_breaker=False,
                    )
                    if data and isinstance(data, dict):
                        block = _check_gemini_block(data)
                        if block:
                            logger.warning(f"Gemini {self.model} run_tool_agent blocked/empty: {block}")
                            continue
                        break
                    else:
                        last_req_err = "Empty/failed response from Gemini API"
            except RateLimitError as e:
                self._handle_rate_limit_error(api_key, e, "run_tool_agent")
                last_req_err = e
            except (StreamTimeoutError, StreamSafetyTimeoutError) as e:
                logger.warning(f"Gemini run_tool_agent streaming timeout on {self.model}: {e}")
                self._key_cooldowns[api_key] = time.time() + 15.0
                last_req_err = e
                if use_streaming:
                    try:
                        logger.info(f"Gemini {self.model} attempting non-streaming fallback for run_tool_agent...")
                        non_stream_url = f"{self.BASE_URL}/{self.resolved_model}:generateContent"
                        data = await fetch_with_retry(
                            non_stream_url,
                            method="POST",
                            json=payload,
                            headers=headers,
                            timeout=int(timeout_sec),
                            max_retries=1,
                            raise_on_429=True,
                            use_circuit_breaker=False,
                        )
                        if data and isinstance(data, dict):
                            use_streaming = False
                            break
                    except Exception as fb_err:
                        logger.warning(f"Gemini run_tool_agent non-streaming fallback failed: {fb_err}")
                if attempt + 1 < max_attempts:
                    continue
                raise
            except Exception as e:
                last_req_err = e
                if self._is_transient_error(e):
                    self._handle_rate_limit_error(api_key, e, "run_tool_agent")
                    continue
                clean_msg = format_api_error_summary(getattr(e, "status", 500), getattr(e, "body", "") or str(e))
                logger.warning(
                    f"Gemini run_tool_agent attempt {attempt + 1} failed with key ({mask_credential(api_key)}): {clean_msg}"
                )

        if use_streaming:
            if stream_res is None:
                raise Exception(
                    f"Gemini API streaming request failed for {self.model}: {last_req_err or 'all attempts failed'}"
                )

            blocks = []
            stop_reason = "end_turn"
            if stream_res.finish_reason == "MAX_TOKENS":
                logger.warning(
                    f"Gemini {self.model} run_tool_agent output truncated by token limit (finishReason=MAX_TOKENS, maxOutputTokens={eff_max_tokens})"
                )
                stop_reason = "max_tokens"

            if stream_res.thinking_text:
                sig = getattr(stream_res, "thought_signature", "") or ""
                blocks.append(
                    MockBlock(
                        type="thinking",
                        thinking=stream_res.thinking_text,
                        text=stream_res.thinking_text,
                        thought=True,
                        signature=sig,
                        thought_signature=sig,
                        thoughtSignature=sig,
                    )
                )

            if stream_res.text:
                blocks.append(MockBlock(type="text", text=stream_res.text))

            import uuid

            for tc in stream_res.tool_calls:
                ts = tc.get("thoughtSignature") or f"gemini_tool_fallback_{uuid.uuid4().hex[:8]}"
                b = MockBlock(type="tool_use", name=tc["name"], input=tc.get("args", {}), id=ts)
                if tc.get("thoughtSignature"):
                    setattr(b, "thoughtSignature", tc["thoughtSignature"])
                    setattr(b, "thought_signature", tc["thoughtSignature"])
                blocks.append(b)
                stop_reason = "tool_use"

            usage = stream_res.usage or {}
            thoughts = usage.get("thoughtsTokenCount", 0) or 0
            resp = MockResponse(
                content=blocks,
                stop_reason=stop_reason,
                input_tokens=usage.get("promptTokenCount", 0),
                output_tokens=usage.get("candidatesTokenCount", 0),
                thinking_tokens=thoughts,
                cached_tokens=usage.get("cachedContentTokenCount", 0) or 0,
            )
            resp.is_paid = self._is_paid_key(api_key)
            return resp
        else:
            if not data or not isinstance(data, dict):
                raise Exception(f"Gemini API request failed for {self.model}: {last_req_err or 'all attempts failed'}")

            candidates = data.get("candidates", [])
            if not candidates:
                block_info = _check_gemini_block(data) or "unknown"
                raise Exception(f"Gemini returned empty candidates (block_info={block_info}). Full response: {data}")

            parts = candidates[0].get("content", {}).get("parts", [])
            blocks = []
            stop_reason = "end_turn"
            finish_reason = candidates[0].get("finishReason", "")
            if finish_reason == "MAX_TOKENS":
                logger.warning(
                    f"Gemini {self.model} run_tool_agent output truncated by token limit (finishReason=MAX_TOKENS, maxOutputTokens={eff_max_tokens})"
                )
                stop_reason = "max_tokens"

            for part in parts:
                if "text" in part:
                    is_thought = part.get("thought") is True
                    ts = part.get("thoughtSignature") or part.get("thought_signature")
                    if is_thought:
                        blocks.append(
                            MockBlock(
                                type="thinking",
                                text=part["text"],
                                thought=True,
                                thought_signature=ts,
                                thoughtSignature=ts,
                            )
                        )
                    else:
                        blocks.append(MockBlock(type="text", text=part["text"]))
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    import uuid

                    ts = (
                        part.get("thoughtSignature")
                        or part.get("thought_signature")
                        or fc.get("id")
                        or f"gemini_tool_fallback_{uuid.uuid4().hex[:8]}"
                    )
                    b = MockBlock(type="tool_use", name=fc["name"], input=fc.get("args", {}), id=ts)
                    if "thoughtSignature" in part or "thought_signature" in part:
                        setattr(b, "thoughtSignature", ts)
                        setattr(b, "thought_signature", ts)
                    blocks.append(b)
                    stop_reason = "tool_use"

            usage = data.get("usageMetadata", {})
            thoughts = usage.get("thoughtsTokenCount", 0) or 0
            resp = MockResponse(
                content=blocks,
                stop_reason=stop_reason,
                input_tokens=usage.get("promptTokenCount", 0),
                output_tokens=usage.get("candidatesTokenCount", 0),
                thinking_tokens=thoughts,
                cached_tokens=usage.get("cachedContentTokenCount", 0) or 0,
            )
            resp.is_paid = self._is_paid_key(api_key)
            return resp

    async def run_chat_loop(
        self, system_prompt: str, conversation_history: list, new_user_message: str, tools: list, tool_executor=None
    ) -> dict:
        messages = [{"role": h["role"], "content": h["content"]} for h in conversation_history]
        messages.append({"role": "user", "content": new_user_message})

        from monika.infrastructure.llm.context_compaction import ContextCompactionEngine

        compactor = ContextCompactionEngine(self.settings)

        turns = 0
        tool_calls_made = 0
        final_text = ""
        proposed_action = None
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_tokens = 0
        total_thinking_tokens = 0
        any_turn_paid = False
        consecutive_chat_tool_sig = None
        repeated_chat_tool_count = 0

        while turns < self.max_tool_turns:
            turns += 1
            messages = compactor.check_and_compact(messages, context_window=self.settings.get("context_window", 128000))
            try:
                response = await self.run_tool_agent(messages, tools, system_prompt)
            except Exception as e:
                clean_err = format_api_error_summary(getattr(e, "status", 500), getattr(e, "body", "") or str(e))
                return {"reply": f"API error: {clean_err}", "success": False, "error": clean_err}

            if getattr(response, "is_paid", False):
                any_turn_paid = True

            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens
            total_cached_tokens += getattr(response, "cached_tokens", 0) or 0
            total_thinking_tokens += getattr(response, "thinking_tokens", 0) or 0

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            for block in assistant_content:
                if block.type == "text":
                    final_text = block.text

            if response.stop_reason == "end_turn":
                break
            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue
                tool_name = block.name
                tool_input = block.input
                tool_use_id = block.id

                # Anti-Oscillation Tool Loop Guard (Hash-based)
                try:
                    sig_args = json.dumps(tool_input, sort_keys=True, default=str)
                except Exception:
                    sig_args = str(tool_input)
                call_sig = f"{tool_name}:{hashlib.md5(sig_args.encode()).hexdigest()}"
                if call_sig == consecutive_chat_tool_sig:
                    repeated_chat_tool_count += 1
                else:
                    consecutive_chat_tool_sig = call_sig
                    repeated_chat_tool_count = 1

                if repeated_chat_tool_count >= 2:
                    logger.warning(
                        f"[Gemini][ChatLoop] Anti-Oscillation: Suppressing repeated tool call #{repeated_chat_tool_count} for {tool_name}"
                    )
                    suppressed_result = {
                        "status": "already_executed",
                        "notice": f"Tool '{tool_name}' with identical parameters was already executed in this conversation turn. Do not repeat identical calls. Use data already obtained.",
                    }
                    tool_calls_made += 1
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(suppressed_result)}
                    )
                    continue

                tool_calls_made += 1

                if tool_name == "propose_action":
                    proposed_action = tool_input
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps({"status": "proposed", "message": "Action proposed."}),
                        }
                    )
                    continue

                from monika.infrastructure.database.db import get_session as _gs

                async with _gs() as session:
                    if tool_executor is not None:
                        bound_executor = tool_executor
                    else:
                        import importlib

                        tool_executor_cls = importlib.import_module(
                            "monika.application.analysis.tools.tool_executor"
                        ).ToolExecutor
                        bound_executor = tool_executor_cls(session, settings=self.settings, model_name=self.model)
                    try:
                        result = await bound_executor.execute(tool_name, tool_input)
                    except Exception as exec_err:
                        logger.error(f"Gemini chat tool execution error ({tool_name}): {exec_err}", exc_info=True)
                        from monika.application.agent.harness.turn_failure_diagnostics import (
                            TurnFailureDiagnosticBuilder,
                        )

                        diag = TurnFailureDiagnosticBuilder.from_tool_execution_error(
                            turn_number=turns,
                            tool_name=tool_name,
                            tool_input=tool_input if isinstance(tool_input, dict) else {},
                            error_msg=str(exec_err),
                        )
                        result = {"status": "error", "error": str(exec_err), "_turn_failure_diagnostic": diag.to_dict()}
                raw_payload = json.dumps(result, ensure_ascii=False, default=str)
                pruned_payload = compactor.micro_prune(raw_payload, tool_name=tool_name)
                tool_results.append({"type": "tool_result", "tool_use_id": tool_use_id, "content": pruned_payload})

            messages.append({"role": "user", "content": tool_results})

        if total_input_tokens > 0 or total_output_tokens > 0:
            from monika.infrastructure.database.db import get_session as _gs

            async with _gs() as session:
                await self._save_token_usage(
                    self.model,
                    "chat_telegram",
                    total_input_tokens,
                    total_output_tokens,
                    session,
                    cached_tokens=total_cached_tokens,
                    thinking_tokens=total_thinking_tokens,
                    is_direct_free_tier=not any_turn_paid,
                    is_paid=any_turn_paid,
                    cost_source="gemini_paid_exact" if any_turn_paid else "gemini_free_tier",
                    exact_cost=0.0 if not any_turn_paid else None,
                )

        return {
            "reply": final_text or "Maaf, tidak ada respons teks.",
            "tool_calls_made": tool_calls_made,
            "turns": turns,
            "proposed_action": proposed_action,
            "success": True,
            "error": None,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "thinking_tokens": total_thinking_tokens,
        }
