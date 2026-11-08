import asyncio
import hashlib
import json
import logging
import os
import re
import time
from types import SimpleNamespace
from typing import Any, Dict, Optional

from monika.infrastructure.llm.rate_limiting.streaming import StreamConfig, StreamSafetyTimeoutError, StreamTimeoutError
from monika.infrastructure.providers.base_provider import BaseLLMClient, _flatten_system_prompt

logger = logging.getLogger(__name__)


from monika.infrastructure.providers.openai_chat import OpenAIChatMixin
from monika.infrastructure.providers.openai_protocol import (
    _canonicalize_schema,
    _extract_message_text,
    make_openai_strict_schema,
    sanitize_tool_parameters_schema,
)

OPENAI_DIRECT_MODEL_ALIASES: dict[str, str] = {
    "gpt-6-luna-xhigh": "gpt-6-luna",
    "gpt-6-luna-max": "gpt-6-luna",
    "gpt-6-luna-decision": "gpt-6-luna",
    "gpt-5.6-luna-xhigh": "gpt-5.6-luna",
    "gpt-5.6-luna-max": "gpt-5.6-luna",
    "gpt-5.6-sol-high": "gpt-5.6-sol",
    "gpt-5.6-sol-medium": "gpt-5.6-sol",
    "gpt-sol-6.1": "gpt-6.1-sol",
    "gpt-sol-6": "gpt-6-sol",
    "gpt-sol-5.6": "gpt-5.6-sol",
}


class OpenAIProvider(OpenAIChatMixin):
    """
    Provider untuk model OpenAI (GPT-4o, GPT-4o-mini).
    Note: Requires `openai` package installed.
    """

    _UNSUPPORTED_PROMPT_CACHE_PROVIDERS: frozenset[str] = frozenset({"groq"})
    _UNSUPPORTED_PROMPT_CACHE_MODELS: set[str] = {
        "qwen/qwen3.8-27b",
        "qwen3.8-27b",
        "groq-qwen3.8-27b",
        "qwen/qwen3.6-27b",
        "qwen3.6-27b",
    }

    def __init__(
        self,
        model: str,
        max_tokens: int = 2048,
        api_key: Optional[str] = None,
        settings: Optional[dict] = None,
        temperature: float = 0.0,
        max_tool_turns: int = 15,
        thinking_level: str = "none",
        **kwargs,
    ):
        resolved_model = model
        target_prov = kwargs.get("provider_name") or getattr(self, "provider_name", "") or "openai"
        if self.__class__.__name__ in ("OpenAIProvider", "CodexProvider") and target_prov in ("openai", "codex"):
            clean_m = model[len("openai/") :] if model.lower().startswith("openai/") else model
            resolved_model = OPENAI_DIRECT_MODEL_ALIASES.get(clean_m.lower(), clean_m)
        super().__init__(
            resolved_model,
            max_tokens=max_tokens,
            max_tool_turns=max_tool_turns,
            thinking_level=thinking_level,
            settings=settings,
            temperature=temperature,
            **kwargs,
        )
        if not hasattr(self, "raw_model_name"):
            self.raw_model_name = model
        self.provider_name = target_prov
        from monika.core.security.credential_vault import vault

        self.api_key = api_key or vault.get_secret("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.role = kwargs.get("role", getattr(self, "role", model))
        self.kwargs = kwargs
        self.last_served_model: Optional[str] = None
        self._prompt_cache_key_supported: bool = True
        try:
            from openai import AsyncOpenAI

            provider_cfg = (settings or {}).get("llm", {}).get("providers", {}).get(target_prov, {}) or (
                settings or {}
            ).get("llm", {}).get("providers", {}).get("openai", {})
            max_retries = provider_cfg.get("max_retries", 3)
            timeout_sec = float(provider_cfg.get("timeout_seconds", 360.0))
            base_url = kwargs.get("base_url") or provider_cfg.get("base_url")
            client_kwargs = {"api_key": self.api_key, "max_retries": max_retries, "timeout": timeout_sec}
            if base_url:
                client_kwargs["base_url"] = str(base_url)
            if self.api_key:
                self.client = AsyncOpenAI(**client_kwargs)
            else:
                self.client = None
        except ImportError:
            logger.warning("OpenAI package not installed. Run `pip install openai`.")
            self.client = None

    def set_api_key(self, api_key: str) -> None:
        """Update active API key and re-initialize underlying AsyncOpenAI client."""
        super().set_api_key(api_key)
        self.api_key = api_key
        old_client = getattr(self, "client", None)
        if old_client is not None and hasattr(old_client, "close"):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(old_client.close())
            except RuntimeError:
                pass
        try:
            from openai import AsyncOpenAI

            provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get(self._get_provider_name(), {})
            max_retries = provider_cfg.get("max_retries", 3)
            timeout_sec = float(provider_cfg.get("timeout_seconds", 360.0))
            base_url = getattr(self.client, "base_url", None) if self.client is not None else None
            client_kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": max_retries, "timeout": timeout_sec}
            if base_url:
                client_kwargs["base_url"] = str(base_url)
            self.client = AsyncOpenAI(**client_kwargs)
        except Exception as e:
            logger.debug(f"Failed to re-initialize OpenAI client on key update: {e}")

    def _get_provider_name(self) -> str:
        if getattr(self, "provider_name", None) and self.provider_name != "openai":
            return self.provider_name
        cls_name = self.__class__.__name__.lower()
        if "openrouter" in cls_name:
            return "openrouter"
        if "groq" in cls_name:
            return "groq"
        if (
            getattr(self, "_is_deepseek", False)
            or "deepseek" in cls_name
            or ("deepseek" in str(getattr(self, "model", "")).lower() and "openrouter" not in cls_name)
        ):
            return "deepseek"
        client_url = getattr(self.client, "base_url", None)
        if client_url and "mock" not in client_url.__class__.__name__.lower():
            url_str = str(client_url).lower()
            if "openrouter" in url_str:
                return "openrouter"
            if "groq" in url_str:
                return "groq"
            if "deepseek" in url_str:
                return "deepseek"
        return "openai"

    def set_thinking_budget(self, budget: int) -> None:
        """Sets thinking budget and resolves corresponding reasoning effort."""
        if budget == 0:
            self.thinking_budget = 0
            self.thinking_level = "none"
        else:
            try:
                from monika.infrastructure.llm.adaptive_thinking import QuantizedThinkingAllocator

                quantized_budget = QuantizedThinkingAllocator.quantize(budget)
            except Exception:
                quantized_budget = 4096 if budget >= 4000 else 1024
            self.thinking_budget = quantized_budget
            if quantized_budget >= 10000:
                self.thinking_level = "high"
            elif quantized_budget >= 4000:
                self.thinking_level = "medium"
            else:
                self.thinking_level = "low"

    def _apply_reasoning_params(self, kwargs: dict) -> None:
        provider_name = self._get_provider_name()

        provider_config = self.settings.get("llm", {}).get("providers", {}).get(provider_name, {})
        supports_reasoning_effort = (
            provider_config.get("features", {}).get("reasoning_effort")
            or provider_config.get("features", {}).get("reasoning")
            or False
        )

        REASONING_SUBSTRINGS = (
            "o1",
            "o3",
            "o4",
            "gpt-5",
            "gpt-6",
            "deepseek-v4",
            "r1",
            "glm-5",
            "muse-spark",
            "kimi-k",
            "gemini-3.8",
            "gemini-4",
            "fable",
            "opus-5",
            "sonnet-5",
        )
        is_reasoning_model = any(x in self.model.lower() for x in REASONING_SUBSTRINGS)
        requested_tokens = int(kwargs.get("max_tokens") or kwargs.get("max_completion_tokens") or self.max_tokens)

        floor_map = {
            "minimal": 1024,
            "low": 2048,
            "medium": 4096,
            "high": 8192,
            "xhigh": 16384,
            "extended": 16384,
            "max": 32768,
        }

        if is_reasoning_model:
            kwargs.pop("temperature", None)

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

            if provider_name == "deepseek":
                kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

            if supports_reasoning_effort:
                kwargs["reasoning_effort"] = effort
                kwargs.pop("temperature", None)

            from monika.infrastructure.providers.capabilities import resolve_effective_max_tokens

            safe_tokens = resolve_effective_max_tokens(
                model_name=self.model,
                provider_name=provider_name,
                requested_max_tokens=requested_tokens,
                thinking_budget=getattr(self, "thinking_budget", None),
                thinking_level=self.thinking_level,
                settings=self.settings,
            )
            if "max_completion_tokens" in kwargs or is_reasoning_model or supports_reasoning_effort:
                kwargs["max_completion_tokens"] = safe_tokens
                kwargs.pop("max_tokens", None)
            else:
                kwargs["max_tokens"] = safe_tokens
        elif is_reasoning_model:
            from monika.infrastructure.providers.capabilities import resolve_effective_max_tokens

            safe_tokens = resolve_effective_max_tokens(
                model_name=self.model,
                provider_name=provider_name,
                requested_max_tokens=max(requested_tokens, 4096),
                thinking_level="medium",
                settings=self.settings,
            )
            kwargs["max_completion_tokens"] = safe_tokens
            kwargs.pop("max_tokens", None)
            kwargs.pop("temperature", None)

        if provider_name == "groq":
            if "max_tokens" in kwargs:
                kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
            tok_key = "max_completion_tokens"
            if tok_key in kwargs and kwargs[tok_key]:
                # ==============================================================================
                # ARCHITECTURAL INVARIANT: Model-aware completion ceiling for Groq
                # Compound: 8,192 | 8B/Gemma: 8,192 | 70B/Qwen: 32,768 | OSS: 65,536
                # ==============================================================================
                model_str = self.model.lower()
                if "oss" in model_str:
                    max_limit = 65536
                elif "qwen" in model_str or "70b" in model_str:
                    max_limit = 32768
                elif "compound" in model_str or "8b" in model_str:
                    max_limit = 8192
                else:
                    max_limit = getattr(self.capabilities, "max_output_tokens", 8192) or 8192

                if self.thinking_level and str(self.thinking_level).lower() in ("high", "xhigh", "extended", "max"):
                    kwargs[tok_key] = max_limit
                else:
                    kwargs[tok_key] = min(kwargs[tok_key], max_limit)

    def _build_stream_config(self) -> StreamConfig:
        provider_name = self._get_provider_name()
        llm_cfg = (self.settings or {}).get("llm", {})
        provider_cfg = llm_cfg.get(provider_name, {}) or llm_cfg.get("providers", {}).get(provider_name, {})
        stream_cfg = provider_cfg.get("streaming", {})
        default_idle = 30.0 if provider_name == "groq" else 120.0
        default_first = 60.0 if provider_name == "groq" else 300.0
        return StreamConfig(
            idle_timeout=float(stream_cfg.get("idle_timeout_seconds", default_idle)),
            safety_timeout=float(stream_cfg.get("safety_timeout_seconds", 1200.0)),
            first_chunk_timeout=float(stream_cfg.get("first_chunk_timeout_seconds", default_first)),
        )

    async def _consume_openai_stream(self, stream, config: Optional[StreamConfig] = None):
        """
        Consumes AsyncStream[ChatCompletionChunk] with idle-timeout liveness tracking.
        Reconstructs a mock object compatible with non-streaming ChatCompletion response.
        """
        if config is None:
            config = self._build_stream_config()

        start_time = time.monotonic()
        last_event_time = start_time
        is_first_chunk = True
        chunks_received = 0

        content = ""
        reasoning = ""
        tool_calls_dict = {}
        finish_reason = None
        usage = None
        served_model = None
        extra_fields: dict[str, Any] = {}

        stream_iter = stream.__aiter__()
        try:
            while True:
                effective_timeout = config.first_chunk_timeout if is_first_chunk else config.idle_timeout
                try:
                    chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=effective_timeout)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    now = time.monotonic()
                    timeout_type = "first chunk" if is_first_chunk else "idle"
                    raise StreamTimeoutError(
                        f"OpenAI streaming {timeout_type} timeout ({effective_timeout:.0f}s) "
                        f"for {self.model} after {chunks_received} chunks",
                        idle_seconds=now - last_event_time,
                        chunks_received=chunks_received,
                    )

                now = time.monotonic()
                if (now - start_time) > config.safety_timeout:
                    raise StreamSafetyTimeoutError(
                        f"OpenAI stream safety timeout {config.safety_timeout:.0f}s exceeded for {self.model}",
                        idle_seconds=now - last_event_time,
                        chunks_received=chunks_received,
                    )

                last_event_time = now
                chunks_received += 1
                is_first_chunk = False

                if hasattr(chunk, "usage") and chunk.usage:
                    usage = chunk.usage

                if hasattr(chunk, "model") and chunk.model:
                    served_model = chunk.model

                extra_fields = {}
                for choice in getattr(chunk, "choices", None) or []:
                    delta = getattr(choice, "delta", None)
                    if delta:
                        if getattr(delta, "content", None):
                            content += delta.content
                        if getattr(delta, "reasoning_content", None):
                            reasoning += delta.reasoning_content
                        elif getattr(delta, "reasoning", None):
                            reasoning += delta.reasoning

                        for k in ("thought_signature", "thought", "reasoning_details", "extra_content"):
                            val = getattr(delta, k, None)
                            if val:
                                extra_fields[k] = val

                        tc_list = getattr(delta, "tool_calls", None) or []
                        for tc in tc_list:
                            idx = getattr(tc, "index", 0)
                            if idx not in tool_calls_dict:
                                tool_calls_dict[idx] = {
                                    "id": getattr(tc, "id", "") or "",
                                    "name": getattr(getattr(tc, "function", None), "name", "") or "",
                                    "arguments": "",
                                }
                            fn = getattr(tc, "function", None)
                            if fn and getattr(fn, "arguments", None):
                                tool_calls_dict[idx]["arguments"] += fn.arguments
                            if getattr(tc, "id", None) and not tool_calls_dict[idx]["id"]:
                                tool_calls_dict[idx]["id"] = tc.id
                            if fn and getattr(fn, "name", None) and not tool_calls_dict[idx]["name"]:
                                tool_calls_dict[idx]["name"] = fn.name

                    if getattr(choice, "finish_reason", None):
                        finish_reason = choice.finish_reason
        finally:
            import inspect

            resp = getattr(stream, "response", None)
            resp_aclose = getattr(resp, "aclose", None)
            if callable(resp_aclose):
                try:
                    res = resp_aclose()
                    if inspect.isawaitable(res):
                        await res
                except Exception:
                    pass
            else:
                stream_aclose = getattr(stream, "aclose", None)
                if callable(stream_aclose):
                    try:
                        res = stream_aclose()
                        if inspect.isawaitable(res):
                            await res
                    except Exception:
                        pass
                else:
                    stream_close = getattr(stream, "close", None)
                    if callable(stream_close):
                        try:
                            res = stream_close()
                            if inspect.isawaitable(res):
                                await res
                        except Exception:
                            pass

        tool_calls_objs = []
        for idx in sorted(tool_calls_dict.keys()):
            tc_data = tool_calls_dict[idx]
            tc_obj = SimpleNamespace(
                id=tc_data["id"] or f"call_{idx}",
                type="function",
                function=SimpleNamespace(name=tc_data["name"], arguments=tc_data["arguments"]),
            )
            tool_calls_objs.append(tc_obj)

        msg_obj = SimpleNamespace(
            content=content if content else None,
            reasoning=reasoning if reasoning else None,
            reasoning_content=reasoning if reasoning else None,
            tool_calls=tool_calls_objs if tool_calls_objs else None,
            **extra_fields,
        )
        choice_obj = SimpleNamespace(
            message=msg_obj, finish_reason=finish_reason or ("tool_calls" if tool_calls_objs else "stop")
        )
        return SimpleNamespace(choices=[choice_obj], usage=usage, model=served_model)

    async def _call_chat_completions_with_recovery(self, target_kwargs: Optional[dict] = None, **kwargs):
        """
        Executes client.chat.completions.create with universal self-healing against:
        1. prompt_cache_key unsupported by endpoint
        2. max_completion_tokens / max_tokens ceiling exceeded (400 limit error)
        3. Parameter naming mismatch (max_tokens vs max_completion_tokens)
        """
        client = self.client
        if client is None:
            logger.error(f"[{self.model}] OpenAI client is not initialized.")
            return None
        current_kwargs = dict(target_kwargs) if target_kwargs is not None else dict(kwargs)
        for attempt in range(3):
            try:
                return await client.chat.completions.create(**current_kwargs)
            except Exception as e:
                err_str = str(e).lower()

                # Case 1: prompt_cache_key rejected by endpoint
                if "prompt_cache_key" in err_str and "prompt_cache_key" in current_kwargs:
                    self._prompt_cache_key_supported = False
                    prov = self._get_provider_name()
                    model_id = str(getattr(self, "model", "")).strip()
                    if model_id:
                        self._UNSUPPORTED_PROMPT_CACHE_MODELS.add(model_id)
                        self._UNSUPPORTED_PROMPT_CACHE_MODELS.add(f"{prov}:{model_id}")
                    logger.info(
                        f"[{self.model}] prompt_cache_key not supported by {prov} endpoint; disabling for future requests and retrying."
                    )
                    current_kwargs.pop("prompt_cache_key", None)
                    continue

                # Case 2: max_completion_tokens / max_tokens limit exceeded (e.g. Groq/OpenAI 400 error)
                # Matches: "`max_completion_tokens` must be less than or equal to `8192`", "must be <= 8192", "maximum value is 8192"
                m = re.search(
                    r"(?:less than or equal to|must be <=|maximum value (?:for \w+ )?is)\s*[`'\"]?(\d+)", err_str
                )
                if m and ("max_completion_tokens" in err_str or "max_tokens" in err_str or "token" in err_str):
                    limit = int(m.group(1))
                    token_key = "max_completion_tokens" if "max_completion_tokens" in current_kwargs else "max_tokens"
                    old_val = current_kwargs.get(token_key)
                    if old_val and old_val > limit:
                        logger.warning(
                            f"[{self.model}] Token ceiling clamp: {token_key}={old_val} exceeds model limit {limit}. Auto-recovering with {limit}."
                        )
                        current_kwargs[token_key] = limit
                        self.max_tokens = min(self.max_tokens, limit)
                        continue

                # Case 3: Parameter swap: max_tokens not supported -> max_completion_tokens
                if (
                    "max_tokens is not supported" in err_str or "use max_completion_tokens" in err_str
                ) and "max_tokens" in current_kwargs:
                    logger.warning(f"[{self.model}] Swapping deprecated max_tokens to max_completion_tokens.")
                    current_kwargs["max_completion_tokens"] = current_kwargs.pop("max_tokens")
                    continue

                # Case 4: Parameter swap: max_completion_tokens unsupported -> max_tokens
                if (
                    "unsupported parameter: max_completion_tokens" in err_str
                    or "extra inputs are not permitted" in err_str
                ) and "max_completion_tokens" in current_kwargs:
                    logger.warning(f"[{self.model}] Swapping max_completion_tokens to max_tokens for compatible proxy.")
                    current_kwargs["max_tokens"] = current_kwargs.pop("max_completion_tokens")
                    continue

                # Case 5: tool_choice unsupported by proxy/model (e.g. 400 error)
                if (
                    "tool_choice" in err_str
                    or "tool choice" in err_str
                    or "unsupported parameter: tool_choice" in err_str
                ) and "tool_choice" in current_kwargs:
                    logger.warning(
                        f"[{self.model}] tool_choice parameter not supported by endpoint; auto-recovering without tool_choice."
                    )
                    current_kwargs.pop("tool_choice", None)
                    continue

                # If no recovery rule matched, re-raise original exception
                raise

    def _supports_prompt_cache_key(self, provider_name: str) -> bool:
        """Return True if the active provider and model support the prompt_cache_key parameter."""
        if not getattr(self, "_prompt_cache_key_supported", True):
            return False
        if provider_name in self._UNSUPPORTED_PROMPT_CACHE_PROVIDERS:
            return False
        model_id = str(getattr(self, "model", "")).strip()
        if model_id in self._UNSUPPORTED_PROMPT_CACHE_MODELS:
            return False
        if f"{provider_name}:{model_id}" in self._UNSUPPORTED_PROMPT_CACHE_MODELS:
            return False
        return True

    async def _create_chat_completion(self, kwargs: dict):
        if not self.client:
            raise RuntimeError("OpenAI API client not initialized")

        provider_name = self._get_provider_name()

        # Session affinity headers for load balancer KV-cache replica pinning (OpenRouter, DeepSeek, OpenAI)
        affinity_headers = self._get_session_affinity_headers()
        if affinity_headers:
            extra_headers = kwargs.get("extra_headers") or {}
            kwargs["extra_headers"] = {**affinity_headers, **extra_headers}

        # Auto-populate prompt_cache_key clamped to 64 chars when supported
        sub = getattr(self, "sub_task", None) or kwargs.pop("sub_task", None)
        if "prompt_cache_key" not in kwargs and self._supports_prompt_cache_key(provider_name):
            base_role = getattr(self, "role", None) or getattr(self, "task_role", "default")
            role_part = f"{base_role}:{sub}" if sub else base_role
            raw_key = getattr(self, "session_id", None) or f"monika_{role_part}"
            key_str = str(raw_key).strip()
            if not key_str.startswith("monika_"):
                key_str = f"monika_{key_str}"
            kwargs["prompt_cache_key"] = key_str[:64]

        provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get(provider_name, {}) or (
            self.settings or {}
        ).get("llm", {}).get(provider_name, {})
        use_streaming = provider_cfg.get("streaming", {}).get("enabled", bool(self.settings))

        if use_streaming:
            call_kwargs = dict(kwargs)
            call_kwargs["stream"] = True
            call_kwargs["stream_options"] = {"include_usage": True}
            raw_response = await self._call_chat_completions_with_recovery(call_kwargs)
            if raw_response is None:
                return None
            if hasattr(raw_response, "choices") and raw_response.choices:
                return raw_response
            if hasattr(raw_response, "__aiter__"):
                return await self._consume_openai_stream(raw_response)
            return raw_response
        else:
            return await self._call_chat_completions_with_recovery(kwargs)

    @staticmethod
    def _extract_usage(usage) -> tuple[int, int, int, int, Optional[float], int]:
        """
        Universal extraction of token usage metrics across OpenAI, DeepSeek, Groq, OpenRouter.
        Returns:
            (input_tokens, output_tokens, cached_tokens, thinking_tokens, exact_cost, cache_creation_tokens)
        """
        if not usage:
            return 0, 0, 0, 0, None, 0

        if isinstance(usage, dict):
            inp = int(usage.get("prompt_tokens", 0) or 0)
            outp = int(usage.get("completion_tokens", 0) or 0)
            details = usage.get("prompt_tokens_details") or {}
            cached = 0
            if isinstance(details, dict):
                cached = int(details.get("cached_tokens", 0) or 0)
            if not cached:
                cached = int(usage.get("prompt_cache_hit_tokens", 0) or 0)

            cache_creation = 0
            if isinstance(details, dict):
                cache_creation = int(details.get("cache_creation_tokens", 0) or 0)

            comp_details = usage.get("completion_tokens_details") or {}
            thinking = 0
            if isinstance(comp_details, dict):
                thinking = int(comp_details.get("reasoning_tokens", 0) or 0)

            c_cost = usage.get("total_cost") or usage.get("cost")
            if c_cost is None and "model_extra" in usage and isinstance(usage["model_extra"], dict):
                c_cost = usage["model_extra"].get("cost") or usage["model_extra"].get("total_cost")
            exact_cost = (
                float(c_cost) if c_cost is not None and isinstance(c_cost, (int, float)) and c_cost >= 0 else None
            )
            return inp, outp, cached, thinking, exact_cost, cache_creation

        inp = getattr(usage, "prompt_tokens", 0)
        inp = int(inp) if isinstance(inp, (int, float)) else 0
        outp = getattr(usage, "completion_tokens", 0)
        outp = int(outp) if isinstance(outp, (int, float)) else 0

        details = getattr(usage, "prompt_tokens_details", None)
        cached = 0
        if details:
            c_val = (
                getattr(details, "cached_tokens", 0)
                if not isinstance(details, dict)
                else details.get("cached_tokens", 0)
            )
            if isinstance(c_val, (int, float)):
                cached = int(c_val)
        if not cached:
            hit_val = getattr(usage, "prompt_cache_hit_tokens", 0)
            if isinstance(hit_val, (int, float)):
                cached = int(hit_val)

        cache_creation = 0
        if details:
            cc_val = (
                getattr(details, "cache_creation_tokens", 0)
                if not isinstance(details, dict)
                else details.get("cache_creation_tokens", 0)
            )
            if isinstance(cc_val, (int, float)):
                cache_creation = int(cc_val)

        comp_details = getattr(usage, "completion_tokens_details", None)
        thinking_tokens = 0
        if comp_details:
            r_val = (
                getattr(comp_details, "reasoning_tokens", 0)
                if not isinstance(comp_details, dict)
                else comp_details.get("reasoning_tokens", 0)
            )
            if isinstance(r_val, (int, float)):
                thinking_tokens = int(r_val)

        exact_cost = None
        c_cost = getattr(usage, "total_cost", None) or getattr(usage, "cost", None)
        if c_cost is None and hasattr(usage, "model_extra") and isinstance(usage.model_extra, dict):
            c_cost = usage.model_extra.get("cost") or usage.model_extra.get("total_cost")
        if c_cost is not None and isinstance(c_cost, (int, float)) and c_cost >= 0:
            exact_cost = float(c_cost)

        return int(inp), int(outp), cached, thinking_tokens, exact_cost, cache_creation

    async def generate(
        self,
        prompt: str,
        system: Optional[Any] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        if not self.client:
            return None
        if not system and "system_prompt" in kwargs:
            system = kwargs.pop("system_prompt")
        messages = []
        static_sys = system
        dynamic_sys = ""
        if isinstance(system, tuple) and len(system) >= 2:
            static_sys = system[0]
            dynamic_sys = str(system[1]).strip() if system[1] else ""
        flat_sys = _flatten_system_prompt(static_sys)
        if (self.model in ("openrouter/free", "free") or ":free" in str(self.model).lower()) and isinstance(
            flat_sys, str
        ):
            if "=== ROLE DIRECTIVE ===\n\n" in flat_sys:
                flat_sys = flat_sys.split("=== ROLE DIRECTIVE ===\n\n", 1)[1]
            elif "\n\n---\n\n" in flat_sys and flat_sys.startswith("=== CANONICAL SYSTEM GOVERNANCE"):
                flat_sys = flat_sys.split("\n\n---\n\n", 1)[1]
        if flat_sys:
            provider_name = self._get_provider_name()
            is_openrouter = (
                provider_name in ("openrouter", "9router")
                or "openrouter" in str(getattr(self.client, "base_url", "")).lower()
            )
            is_claude_or_qwen = any(k in self.model.lower() for k in ("claude", "anthropic", "qwen"))
            if is_openrouter and is_claude_or_qwen:
                messages.append(
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": flat_sys, "cache_control": {"type": "ephemeral"}}],
                    }
                )
            else:
                messages.append({"role": "system", "content": flat_sys})
        actual_prompt = f"{prompt}\n\n{dynamic_sys}" if dynamic_sys else prompt
        messages.append({"role": "user", "content": actual_prompt})

        eff_temp = temperature if temperature is not None else self.kwargs.get("temperature", self.default_temperature)

        from monika.infrastructure.providers.capabilities import resolve_effective_max_tokens

        base_tok = max_tokens if max_tokens is not None else self.max_tokens
        provider_name = self._get_provider_name()
        max_tok = resolve_effective_max_tokens(
            model_name=self.model,
            provider_name=provider_name,
            requested_max_tokens=base_tok,
            thinking_budget=getattr(self, "thinking_budget", None),
            thinking_level=self.thinking_level,
            settings=self.settings,
        )
        openai_valid_params = {
            "model",
            "messages",
            "max_tokens",
            "max_completion_tokens",
            "temperature",
            "top_p",
            "n",
            "stream",
            "stream_options",
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "logit_bias",
            "user",
            "response_format",
            "seed",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "timeout",
            "extra_body",
            "extra_query",
            "extra_headers",
            "reasoning_effort",
            "prompt_cache_key",
        }
        gen_prefix_hash = hashlib.sha256(str(flat_sys).encode("utf-8")).hexdigest()[:16] if flat_sys else None
        call_task_role = kwargs.get("task_role")
        call_subsystem = kwargs.get("subsystem")
        call_symbol = kwargs.get("symbol")
        call_task_name = kwargs.get("task_name")
        call_prefix_hash = kwargs.get("prefix_hash") or gen_prefix_hash

        call_kwargs = {k: v for k, v in kwargs.items() if k in openai_valid_params}
        call_kwargs.update({"model": self.model, "messages": messages, "max_tokens": max_tok, "temperature": eff_temp})
        self._apply_reasoning_params(call_kwargs)
        try:
            response = await self._create_chat_completion(call_kwargs)
            if not response:
                return None
            self.last_served_model = getattr(response, "model", None)
            if hasattr(response, "usage") and response.usage:
                inp, outp, cached, thinking_tokens, exact_cost, cache_creation = self._extract_usage(response.usage)
                kw = {}
                if cached > 0:
                    kw["cached_tokens"] = cached
                if cache_creation > 0:
                    kw["cache_creation_tokens"] = cache_creation
                if thinking_tokens > 0:
                    kw["thinking_tokens"] = thinking_tokens
                if exact_cost is not None:
                    kw["exact_cost"] = exact_cost
                    kw["cost_source"] = "openrouter_exact"
                    kw["is_paid"] = exact_cost > 0.0
                if call_task_role:
                    kw["task_role"] = call_task_role
                if call_subsystem:
                    kw["subsystem"] = call_subsystem
                if call_symbol:
                    kw["symbol"] = call_symbol
                if call_prefix_hash:
                    kw["prefix_hash"] = call_prefix_hash
                await self._save_token_usage(self.model, call_task_name or "generate", inp, outp, **kw)
            if not response.choices:
                return ""
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            if finish_reason == "length":
                logger.warning(
                    f"[{self.model}] generate: response truncated by token limit (finish_reason='length', max_tokens={call_kwargs.get('max_tokens') or call_kwargs.get('max_completion_tokens')})"
                )
            return _extract_message_text(choice)
        except (StreamTimeoutError, StreamSafetyTimeoutError) as e:
            logger.warning(f"[{self.model}] generate streaming timeout: {e}")
            raise
        except Exception as e:
            err_str = str(e).lower()
            is_subclass_provider = self.__class__.__name__ != "OpenAIProvider"
            if "prompt tokens limit exceeded" in err_str or "insufficient credits" in err_str:
                logger.warning(
                    f"OpenRouter 402: prompt tokens exceed credit balance for {self.model} ({e}). Fail-fast to next fallback."
                )
                if is_subclass_provider:
                    raise
                return None
            if "402" in err_str or "fewer max_tokens" in err_str or "can only afford" in err_str:
                import re

                m = re.search(r"can only afford (\d+)", str(e))
                if m:
                    affordable = max(512, int(m.group(1)) - 64)
                    logger.warning(
                        f"OpenRouter 402 credit clamp for {self.model}: retrying with max_tokens={affordable}"
                    )
                    try:
                        call_kwargs["max_tokens"] = affordable
                        response = await self._create_chat_completion(call_kwargs)
                        if not response:
                            return None
                        if hasattr(response, "usage") and response.usage:
                            inp, outp, cached, thinking_tokens, exact_cost, cache_creation = self._extract_usage(
                                response.usage
                            )
                            kw = {}
                            if cached > 0:
                                kw["cached_tokens"] = cached
                            if cache_creation > 0:
                                kw["cache_creation_tokens"] = cache_creation
                            if thinking_tokens > 0:
                                kw["thinking_tokens"] = thinking_tokens
                            if exact_cost is not None:
                                kw["exact_cost"] = exact_cost
                                kw["cost_source"] = "openrouter_exact"
                                kw["is_paid"] = exact_cost > 0.0
                            if call_task_role:
                                kw["task_role"] = call_task_role
                            if call_subsystem:
                                kw["subsystem"] = call_subsystem
                            if call_symbol:
                                kw["symbol"] = call_symbol
                            if call_prefix_hash:
                                kw["prefix_hash"] = call_prefix_hash
                            await self._save_token_usage(self.model, call_task_name or "generate", inp, outp, **kw)
                        if not response.choices:
                            return ""
                        return _extract_message_text(response.choices[0])
                    except (StreamTimeoutError, StreamSafetyTimeoutError) as retry_to:
                        logger.warning(f"[{self.model}] generate retry streaming timeout: {retry_to}")
                        raise
                    except Exception as retry_err:
                        logger.warning(f"OpenRouter 402 retry failed for {self.model}: {retry_err}")
                        if is_subclass_provider:
                            raise
                        return None
                else:
                    logger.warning(f"OpenRouter 402 credit limit reached for {self.model}: {e}")
                    if is_subclass_provider:
                        raise
                    return None
            if (
                "429" in err_str
                or "rate limit" in err_str
                or "502" in err_str
                or "503" in err_str
                or "529" in err_str
                or "bad gateway" in err_str
                or "service unavailable" in err_str
                or "provider returned error" in err_str
            ):
                if is_subclass_provider:
                    raise
            logger.warning(f"OpenAI generate failed with {self.model}: {e}")
            return None

    async def generate_content(
        self,
        system_prompt: str = "",
        user_message: str = "",
        response_schema: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[str]:
        messages = []
        eff_sys = system_prompt
        if (self.model in ("openrouter/free", "free") or ":free" in str(self.model).lower()) and isinstance(
            eff_sys, str
        ):
            if "=== ROLE DIRECTIVE ===\n\n" in eff_sys:
                eff_sys = eff_sys.split("=== ROLE DIRECTIVE ===\n\n", 1)[1]
            elif "\n\n---\n\n" in eff_sys and eff_sys.startswith("=== CANONICAL SYSTEM GOVERNANCE"):
                eff_sys = eff_sys.split("\n\n---\n\n", 1)[1]

        if eff_sys:
            provider_name = self._get_provider_name()
            is_openrouter = (
                provider_name in ("openrouter", "9router")
                or "openrouter" in str(getattr(self.client, "base_url", "")).lower()
            )
            is_claude_or_qwen = any(k in self.model.lower() for k in ("claude", "anthropic", "qwen"))
            if is_openrouter and is_claude_or_qwen:
                messages.append(
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": eff_sys, "cache_control": {"type": "ephemeral"}}],
                    }
                )
            else:
                messages.append({"role": "system", "content": eff_sys})
        messages.append({"role": "user", "content": user_message})
        eff_temp = temperature if temperature is not None else self.kwargs.get("temperature", self.default_temperature)
        provider_name = self._get_provider_name()
        is_groq = "groq" in self.__class__.__name__.lower() or provider_name == "groq"
        is_openrouter = (
            "openrouter" in self.__class__.__name__.lower()
            or provider_name in ("openrouter", "9router")
            or "openrouter" in str(getattr(self.client, "base_url", "")).lower()
        )
        from monika.infrastructure.providers.capabilities import resolve_effective_max_tokens

        base_tok = max_tokens if max_tokens is not None else self.max_tokens
        max_tok = resolve_effective_max_tokens(
            model_name=self.model,
            provider_name=provider_name,
            requested_max_tokens=base_tok,
            thinking_budget=getattr(self, "thinking_budget", None),
            thinking_level=self.thinking_level,
            settings=self.settings,
        )

        gen_prefix_hash = hashlib.sha256(str(eff_sys).encode("utf-8")).hexdigest()[:16] if eff_sys else None
        call_task_role = kwargs.get("task_role")
        call_subsystem = kwargs.get("subsystem")
        call_symbol = kwargs.get("symbol")
        call_task_name = kwargs.get("task_name")
        call_prefix_hash = kwargs.get("prefix_hash") or gen_prefix_hash

        if response_schema:
            is_array_schema = isinstance(response_schema, dict) and response_schema.get("type") == "array"

            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tok,
                "temperature": eff_temp,
            }

            is_antigravity = self._get_provider_name() == "antigravity"
            if is_openrouter or is_antigravity:
                # OpenRouter / Antigravity: Avoid sending strict response_format if reasoning is active or unsupported.
                # Prompt-enforced JSON schema is 100% reliable across bridge proxies and reasoning models.
                if self.thinking_level == "none" and not is_array_schema and not is_antigravity:
                    kwargs["response_format"] = {"type": "json_object"}
                json_hint = (
                    f"\n\nYou MUST return valid JSON conforming to this schema without commentary, preamble, or markdown wrapper. "
                    f"Do NOT emit XML tags, function call tags, or tool calls (e.g. <invoke>, <tool_call>, <dots_function_call>). "
                    f"Output ONLY the raw JSON object:\n{json.dumps(response_schema)}"
                )
                user_msg = kwargs["messages"][-1]["content"]
                if isinstance(user_msg, str):
                    kwargs["messages"][-1]["content"] += json_hint
                elif isinstance(user_msg, list):
                    kwargs["messages"][-1]["content"].append({"type": "text", "text": json_hint})
            elif is_groq:
                if not is_array_schema:
                    kwargs["response_format"] = {"type": "json_object"}
                json_hint = (
                    f"\n\nYou MUST return valid JSON conforming to this schema without commentary, preamble, or markdown wrapper. "
                    f"Do NOT emit XML tags, function call tags, or tool calls (e.g. <invoke>, <tool_call>, <dots_function_call>). "
                    f"Output ONLY the raw JSON object:\n{json.dumps(response_schema)}"
                )
                user_msg = kwargs["messages"][-1]["content"]
                if isinstance(user_msg, str):
                    kwargs["messages"][-1]["content"] += json_hint
                elif isinstance(user_msg, list):
                    kwargs["messages"][-1]["content"].append({"type": "text", "text": json_hint})
            else:
                is_strict_capable = (self._get_provider_name() == "openai") or any(
                    m in str(self.model).lower() for m in ("gpt-4o", "gpt-4.1", "o1", "o3")
                )

                if is_array_schema:
                    wrapped_schema = {"type": "object", "properties": {"items": response_schema}, "required": ["items"]}
                    final_schema = make_openai_strict_schema(wrapped_schema) if is_strict_capable else wrapped_schema
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "structured_response",
                            "schema": final_schema,
                            "strict": is_strict_capable,
                        },
                    }
                    json_hint = "\n\nYou MUST return a JSON object with key 'items' containing the array."
                    user_msg = kwargs["messages"][-1]["content"]
                    if isinstance(user_msg, str):
                        kwargs["messages"][-1]["content"] += json_hint
                else:
                    final_schema = make_openai_strict_schema(response_schema) if is_strict_capable else response_schema
                    kwargs["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "structured_response",
                            "schema": final_schema,
                            "strict": is_strict_capable,
                        },
                    }

            self._apply_reasoning_params(kwargs)
            try:
                response = await self._create_chat_completion(kwargs)
                if not response:
                    return None if response_schema else ""
                self.last_served_model = getattr(response, "model", None)
                if hasattr(response, "usage") and response.usage:
                    inp, outp, cached, thinking_tokens, exact_cost, cache_creation = self._extract_usage(response.usage)
                    kw = {}
                    if cached > 0:
                        kw["cached_tokens"] = cached
                    if cache_creation > 0:
                        kw["cache_creation_tokens"] = cache_creation
                    if thinking_tokens > 0:
                        kw["thinking_tokens"] = thinking_tokens
                    if exact_cost is not None:
                        kw["exact_cost"] = exact_cost
                        kw["cost_source"] = "openrouter_exact"
                        kw["is_paid"] = exact_cost > 0.0
                    if call_task_role:
                        kw["task_role"] = call_task_role
                    if call_subsystem:
                        kw["subsystem"] = call_subsystem
                    if call_symbol:
                        kw["symbol"] = call_symbol
                    if call_prefix_hash:
                        kw["prefix_hash"] = call_prefix_hash
                    await self._save_token_usage(self.model, call_task_name or "generate_content", inp, outp, **kw)
                if not response.choices:
                    return None if response_schema else ""
                choice = response.choices[0]
                finish_reason = getattr(choice, "finish_reason", None)
                if finish_reason == "length":
                    logger.warning(
                        f"[{self.model}] generate_content: response truncated by token limit (finish_reason='length', max_tokens={kwargs.get('max_tokens') or kwargs.get('max_completion_tokens')})"
                    )
                content = _extract_message_text(choice)
                if response_schema:
                    if not content or not content.strip():
                        return None
                    try:
                        cleaned = content.strip()
                        if cleaned.startswith("```"):
                            lines = cleaned.split("\n")
                            if lines[0].startswith("```"):
                                lines = lines[1:]
                            if lines and lines[-1].startswith("```"):
                                lines = lines[:-1]
                            cleaned = "\n".join(lines).strip()
                        json.loads(cleaned)
                    except Exception as je:
                        logger.warning(
                            f"[{self.model}] generate_content schema JSON parse failed ({je}): {content[:100]}"
                        )
                        return None
                return content
            except (StreamTimeoutError, StreamSafetyTimeoutError) as e:
                logger.warning(f"[{self.model}] generate_content streaming timeout: {e}")
                raise
            except Exception as e:
                err_str = str(e).lower()
                is_subclass_provider = self.__class__.__name__ != "OpenAIProvider"
                if "prompt tokens limit exceeded" in err_str or "insufficient credits" in err_str:
                    logger.warning(
                        f"OpenRouter 402: prompt tokens exceed credit balance in generate_content for {self.model} ({e}). Fail-fast to fallback."
                    )
                    if is_subclass_provider:
                        raise
                    return ""
                if "402" in err_str or "fewer max_tokens" in err_str or "can only afford" in err_str:
                    import re

                    m = re.search(r"can only afford (\d+)", str(e))
                    if m:
                        affordable = max(512, int(m.group(1)) - 64)
                        logger.warning(
                            f"OpenRouter 402 credit clamp in generate_content for {self.model}: retrying with max_tokens={affordable}"
                        )
                        try:
                            kwargs["max_tokens"] = affordable
                            response = await self._create_chat_completion(kwargs)
                            if not response:
                                return ""
                            if hasattr(response, "usage") and response.usage:
                                inp, outp, cached, thinking_tokens, exact_cost, cache_creation = self._extract_usage(
                                    response.usage
                                )
                                kw = {}
                                if cached > 0:
                                    kw["cached_tokens"] = cached
                                if cache_creation > 0:
                                    kw["cache_creation_tokens"] = cache_creation
                                if thinking_tokens > 0:
                                    kw["thinking_tokens"] = thinking_tokens
                                if exact_cost is not None:
                                    kw["exact_cost"] = exact_cost
                                    kw["cost_source"] = "openrouter_exact"
                                    kw["is_paid"] = exact_cost > 0.0
                                if call_task_role:
                                    kw["task_role"] = call_task_role
                                if call_subsystem:
                                    kw["subsystem"] = call_subsystem
                                if call_symbol:
                                    kw["symbol"] = call_symbol
                                if call_prefix_hash:
                                    kw["prefix_hash"] = call_prefix_hash
                                await self._save_token_usage(
                                    self.model, call_task_name or "generate_content", inp, outp, **kw
                                )
                            if not response.choices:
                                return ""
                            return _extract_message_text(response.choices[0])
                        except (StreamTimeoutError, StreamSafetyTimeoutError) as retry_to:
                            logger.warning(f"[{self.model}] generate_content retry streaming timeout: {retry_to}")
                            raise
                        except Exception as retry_err:
                            logger.warning(
                                f"OpenRouter 402 retry failed in generate_content for {self.model}: {retry_err}"
                            )
                            if is_subclass_provider:
                                raise
                            return ""
                    else:
                        logger.warning(f"OpenRouter 402 credit limit reached for {self.model} in generate_content: {e}")
                        if is_subclass_provider:
                            raise
                        return ""
                if (
                    "json_schema" in err_str
                    or "response_format" in err_str
                    or "400" in err_str
                    or "schema" in err_str
                    or "unsupported" in err_str
                ):
                    logger.warning(
                        f"Structured response_format rejected by {self.model} ({e}), falling back to prompt-only JSON instruction."
                    )
                    kwargs.pop("response_format", None)
                    json_hint = f"\n\nYou MUST return valid JSON without commentary or wrapper text. Schema:\n{json.dumps(response_schema)}"
                    user_msg = kwargs["messages"][-1]["content"]
                    if isinstance(user_msg, str):
                        if "You MUST return valid JSON" not in user_msg:
                            kwargs["messages"][-1]["content"] += json_hint
                    elif isinstance(user_msg, list):
                        kwargs["messages"][-1]["content"].append({"type": "text", "text": json_hint})
                    try:
                        response = await self._create_chat_completion(kwargs)
                        if not response:
                            return ""
                        if hasattr(response, "usage") and response.usage:
                            inp, outp, cached, thinking_tokens, exact_cost, cache_creation = self._extract_usage(
                                response.usage
                            )
                            kw = {}
                            if cached > 0:
                                kw["cached_tokens"] = cached
                            if cache_creation > 0:
                                kw["cache_creation_tokens"] = cache_creation
                            if thinking_tokens > 0:
                                kw["thinking_tokens"] = thinking_tokens
                            if exact_cost is not None:
                                kw["exact_cost"] = exact_cost
                                kw["cost_source"] = "openrouter_exact"
                                kw["is_paid"] = exact_cost > 0.0
                            if call_task_role:
                                kw["task_role"] = call_task_role
                            if call_subsystem:
                                kw["subsystem"] = call_subsystem
                            if call_symbol:
                                kw["symbol"] = call_symbol
                            if call_prefix_hash:
                                kw["prefix_hash"] = call_prefix_hash
                            await self._save_token_usage(
                                self.model, call_task_name or "generate_content", inp, outp, **kw
                            )
                        if not response.choices:
                            return None if response_schema else ""
                        content = _extract_message_text(response.choices[0])
                        if response_schema:
                            if not content or not content.strip():
                                return None
                            try:
                                cleaned = content.strip()
                                if cleaned.startswith("```"):
                                    lines = cleaned.split("\n")
                                    if lines[0].startswith("```"):
                                        lines = lines[1:]
                                    if lines and lines[-1].startswith("```"):
                                        lines = lines[:-1]
                                    cleaned = "\n".join(lines).strip()
                                json.loads(cleaned)
                            except Exception as je:
                                logger.warning(
                                    f"[{self.model}] generate_content fallback schema JSON parse failed ({je}): {content[:100]}"
                                )
                                return None
                        return content
                    except (StreamTimeoutError, StreamSafetyTimeoutError) as fb_to:
                        logger.warning(f"[{self.model}] generate_content fallback streaming timeout: {fb_to}")
                        raise
                    except Exception as fallback_err:
                        if is_subclass_provider:
                            raise
                        logger.warning(f"Structured JSON fallback failed for {self.model}: {fallback_err}")
                        return None if response_schema else ""
                if is_subclass_provider:
                    raise
                logger.warning(f"OpenAI generate_content failed for {self.model}: {e}")
                return None if response_schema else ""

        else:
            return await self.generate(
                user_message,
                system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )

    async def classify_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        schema: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Optional[dict]:
        if not self.client:
            return None

        # Positional schema handling: classify_json(prompt, schema_dict)
        actual_schema = schema
        actual_sys_prompt = system_prompt
        if isinstance(actual_sys_prompt, dict) and actual_schema is None:
            actual_schema = actual_sys_prompt
            actual_sys_prompt = None

        sys_prompt = (
            str(actual_sys_prompt)
            if actual_sys_prompt
            else "You are a data classification assistant. Always output valid JSON conforming to the schema requested."
        )

        effective_schema = actual_schema if actual_schema is not None else {"type": "object"}

        current_prompt = prompt
        for attempt in range(2):
            try:
                # If attempt > 0 (retry after parse failure or truncated output), expand token budget moderately
                override_tokens = min(int(max_tokens or 4096) * 2, 8192) if attempt > 0 else max_tokens
                result_text = await self.generate_content(
                    sys_prompt,
                    current_prompt,
                    response_schema=effective_schema,
                    temperature=temperature,
                    max_tokens=override_tokens,
                    **kwargs,
                )
                if not result_text:
                    if attempt == 0:
                        await asyncio.sleep(1.0)
                        continue
                    logger.warning(f"[{self.model}] classify_json: generate_content returned empty/None")
                    return None
                from monika.infrastructure.providers.base_provider import extract_and_parse_json

                if len(result_text) > 20000:
                    parsed = await asyncio.to_thread(extract_and_parse_json, result_text)
                else:
                    parsed = extract_and_parse_json(result_text)
                if parsed is not None:
                    return parsed
                logger.warning(f"[{self.model}] classify_json: parse failed on text: {result_text[:250]}")
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    is_tool_call_hallucination = any(
                        tag in result_text
                        for tag in ("<invoke", "<dots_function_call", "<function_calls", "<tool_call")
                    )
                    if is_tool_call_hallucination:
                        correction_suffix = (
                            "\n\n[CRITICAL CORRECTION]: Your previous response attempted to invoke a tool via XML tags. "
                            "Tools are NOT available in this evaluation mode. Do NOT emit any tool calls, function calls, "
                            "or XML tags (<invoke>, <tool_call>, <dots_function_call>). "
                            "Evaluate strictly based on the provided context and return ONLY a valid JSON object."
                        )
                    else:
                        correction_suffix = (
                            "\n\n[CRITICAL CORRECTION]: Your previous response could not be parsed as valid JSON. "
                            "Do NOT emit preamble, commentary, markdown wrappers, or XML tags. "
                            "Output ONLY a raw, syntactically valid JSON object."
                        )
                    current_prompt = prompt + correction_suffix
                    continue
                return None
            except Exception as e:
                logger.warning(f"[{self.model}] classify_json exception ({type(e).__name__}): {e}")
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue
                return None
        return None
