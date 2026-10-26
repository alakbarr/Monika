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


def _extract_message_text(choice) -> str:
    """
    Universal robust text extraction across standard OpenAI, OpenRouter, and reasoning models.
    Checks:
    1. choice.message.content
    2. choice.message.reasoning / reasoning_content
    3. choice.message.model_extra (Pydantic v2 OpenRouter extra fields: reasoning, reasoning_content, thought)
    4. choice.message.model_dump()
    """
    if not choice or not hasattr(choice, "message"):
        return ""
    msg = choice.message

    # 1. Standard message content
    content = getattr(msg, "content", None)
    if content is not None and str(content).strip():
        text = str(content)
        if any(tag in text.lower() for tag in ("<think>", "<thought>", "<reasoning>", "<scratchpad>")):
            from monika.infrastructure.providers.streaming_think_scrubber import StreamingThinkScrubber

            clean_text, _ = StreamingThinkScrubber.scrub_text(text)
            if clean_text.strip():
                return clean_text.strip()
        return text

    # 2. Direct reasoning attributes
    reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)
    if reasoning is not None and str(reasoning).strip():
        return str(reasoning)

    # 3. Pydantic v2 model_extra dictionary
    model_extra = getattr(msg, "model_extra", None) or {}
    if isinstance(model_extra, dict):
        for key in ["reasoning", "reasoning_content", "thought", "reasoning_text"]:
            val = model_extra.get(key)
            if val is not None and str(val).strip():
                return str(val)

    # 4. Model dump fallback
    if hasattr(msg, "model_dump"):
        try:
            dump = msg.model_dump()
            if isinstance(dump, dict):
                for key in ["content", "reasoning", "reasoning_content", "thought"]:
                    val = dump.get(key)
                    if val is not None and str(val).strip():
                        return str(val)
        except Exception:
            pass

    return ""


def _canonicalize_schema(schema: Any) -> Any:
    """Recursively sort dictionary keys for 100% deterministic JSON serialization and KV-cache prefix stability."""
    if isinstance(schema, dict):
        return {k: _canonicalize_schema(v) for k, v in sorted(schema.items())}
    if isinstance(schema, list):
        return [_canonicalize_schema(item) for item in schema]
    return schema


def sanitize_tool_parameters_schema(schema_dict: Any) -> Any:
    """
    Sanitize JSON Schema for OpenAI / OpenRouter function calling parameters.
    Guarantees 100% compliance with JSON Schema Draft-07 function calling specifications:
    1. Removes any 'default' field whose value is None / null (avoids Azure/OpenAI 400 'None is not valid under any of the given schemas').
    2. Simplifies nullable type arrays like ["string", "null"] to "string" or standard types (avoids Meta 400 'null is not valid under any of the schemas').
    3. Simplifies anyOf with null branches: anyOf: [T, {"type": "null"}] -> T.
    4. Ensures array schemas always contain an 'items' specification.
    5. Ensures object schemas always have 'properties' dict.
    6. Recursively cleans all nested objects, properties, and definitions.
    """
    if not isinstance(schema_dict, dict):
        return schema_dict

    import copy

    s = copy.deepcopy(schema_dict)

    def _clean(d: Any) -> Any:
        if isinstance(d, dict):
            # 1. Remove default if None
            if "default" in d and d["default"] is None:
                del d["default"]

            # 2. Simplify type: [T, "null"] -> T
            if "type" in d and isinstance(d["type"], list):
                non_null_types = [t for t in d["type"] if t != "null"]
                if len(non_null_types) == 1:
                    d["type"] = non_null_types[0]
                elif len(non_null_types) > 1:
                    d["type"] = non_null_types[0]
                else:
                    d["type"] = "string"

            # 3. Simplify anyOf with null branches
            if "anyOf" in d and isinstance(d["anyOf"], list):
                non_null_branches = [
                    b
                    for b in d["anyOf"]
                    if not (isinstance(b, dict) and (b.get("type") == "null" or b == {"type": "null"}))
                ]
                if len(non_null_branches) == 1 and isinstance(non_null_branches[0], dict):
                    cleaned_branch = _clean(non_null_branches[0])
                    del d["anyOf"]
                    d.update(cleaned_branch)
                elif len(non_null_branches) > 1:
                    d["anyOf"] = [_clean(b) for b in non_null_branches]
                else:
                    del d["anyOf"]
                    d["type"] = "string"

            # 4. Guarantee array has items
            if d.get("type") == "array" and "items" not in d:
                d["items"] = {"type": "string"}

            # 5. Guarantee object has properties
            if d.get("type") == "object" and "properties" not in d:
                d["properties"] = {}

            # Recurse for all keys
            for k, v in list(d.items()):
                d[k] = _clean(v)
            return d
        elif isinstance(d, list):
            return [_clean(item) for item in d]
        return d

    return _clean(s)


def make_openai_strict_schema(schema_dict: dict) -> dict:
    """
    Transforms standard Pydantic JSON schema into OpenAI strict: true compliant schema.
    Requirements for OpenAI Structured Outputs (strict: true):
    1. 'additionalProperties': False on all object schemas.
    2. Every property in 'properties' MUST be listed in 'required'.
    3. Fields optional in domain logic are made nullable via anyOf: [orig, {"type": "null"}].
    """
    import copy

    if not isinstance(schema_dict, dict):
        return schema_dict

    s = copy.deepcopy(schema_dict)

    def _patch_object(obj: dict):
        if not isinstance(obj, dict):
            return

        if obj.get("type") == "object" or "properties" in obj:
            obj["additionalProperties"] = False
            props = obj.get("properties", {})
            orig_req = set(obj.get("required", []))
            obj["required"] = list(props.keys())

            for key, prop in props.items():
                if key not in orig_req:
                    if "anyOf" in prop:
                        has_null = any(x.get("type") == "null" for x in prop["anyOf"] if isinstance(x, dict))
                        if not has_null:
                            prop["anyOf"].append({"type": "null"})
                    elif "type" in prop:
                        orig_type = prop["type"]
                        if isinstance(orig_type, str):
                            if orig_type != "null":
                                prop["anyOf"] = [{"type": orig_type}, {"type": "null"}]
                                del prop["type"]
                        elif isinstance(orig_type, list):
                            if "null" not in orig_type:
                                prop["type"] = orig_type + ["null"]
                    else:
                        prop["anyOf"] = [copy.deepcopy(prop), {"type": "null"}]

        for v in obj.values():
            if isinstance(v, dict):
                _patch_object(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        _patch_object(item)

    _patch_object(s)
    return s


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


class OpenAIProvider(BaseLLMClient):
    """
    Provider untuk model OpenAI (GPT-4o, GPT-4o-mini).
    Note: Requires `openai` package installed.
    """

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
        try:
            from openai import AsyncOpenAI

            provider_cfg = (settings or {}).get("llm", {}).get("providers", {}).get("openai", {})
            max_retries = provider_cfg.get("max_retries", 3)
            timeout_sec = float(provider_cfg.get("timeout_seconds", 120.0))
            if self.api_key:
                self.client = AsyncOpenAI(api_key=self.api_key, max_retries=max_retries, timeout=timeout_sec)
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
            timeout_sec = float(provider_cfg.get("timeout_seconds", 120.0))
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

            reasoning_headroom = floor_map.get(lvl, 2048)
            safe_tokens = requested_tokens + reasoning_headroom
            if "max_completion_tokens" in kwargs or is_reasoning_model or supports_reasoning_effort:
                kwargs["max_completion_tokens"] = safe_tokens
                kwargs.pop("max_tokens", None)
            else:
                kwargs["max_tokens"] = safe_tokens
        elif is_reasoning_model:
            kwargs["max_completion_tokens"] = max(requested_tokens + 4096, 4096)
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
        default_idle = 15.0 if provider_name == "groq" else (60.0 if provider_name == "deepseek" else 45.0)
        default_first = (
            30.0 if provider_name == "groq" else (120.0 if provider_name in ["openrouter", "deepseek"] else 90.0)
        )
        return StreamConfig(
            idle_timeout=float(stream_cfg.get("idle_timeout_seconds", default_idle)),
            safety_timeout=float(stream_cfg.get("safety_timeout_seconds", 180.0)),
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
                    logger.warning(f"[{self.model}] prompt_cache_key rejected by endpoint, retrying without it.")
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

                # If no recovery rule matched, re-raise original exception
                raise

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
        if "prompt_cache_key" not in kwargs:
            raw_key = (
                getattr(self, "session_id", None)
                or getattr(self, "_session_affinity_id", None)
                or f"monika_{getattr(self, 'role', 'default')}"
            )
            key_str = str(raw_key).strip()
            if not key_str.startswith("monika_"):
                key_str = f"monika_{key_str}"
            kwargs["prompt_cache_key"] = key_str[:64]

        provider_cfg = (self.settings or {}).get("llm", {}).get(provider_name, {})
        use_streaming = provider_cfg.get("streaming", {}).get("enabled", bool(self.settings))

        if use_streaming:
            call_kwargs = dict(kwargs)
            call_kwargs["stream"] = True
            if provider_name != "deepseek":
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

            cache_creation = int(usage.get("prompt_cache_miss_tokens", 0) or 0)
            if not cache_creation and isinstance(details, dict):
                cache_creation = int(details.get("cache_creation_tokens", 0) or 0)

            comp_details = usage.get("completion_tokens_details") or {}
            thinking = 0
            if isinstance(comp_details, dict):
                thinking = int(comp_details.get("reasoning_tokens", 0) or 0)

            c_cost = usage.get("total_cost") or usage.get("cost")
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

        cache_creation = getattr(usage, "prompt_cache_miss_tokens", 0)
        cache_creation = int(cache_creation) if isinstance(cache_creation, (int, float)) else 0
        if not cache_creation and details:
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

        base_tok = max_tokens if max_tokens is not None else self.max_tokens
        is_openrouter = "openrouter" in str(getattr(self.client, "base_url", "")) or "openrouter" in self.model
        if is_openrouter:
            max_tok = max(base_tok, 16384) if self.thinking_level != "none" else max(base_tok, 8192)
        else:
            max_tok = base_tok
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
                await self._save_token_usage(self.model, "generate", inp, outp, **kw)
            if not response.choices:
                return ""
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            if finish_reason == "length":
                logger.warning(
                    f"[{self.model}] generate: response truncated by token limit (finish_reason='length', max_tokens={kwargs.get('max_tokens')})"
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
                            await self._save_token_usage(self.model, "generate", inp, outp, **kw)
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
        if system_prompt:
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
                        "content": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                    }
                )
            else:
                messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})
        eff_temp = temperature if temperature is not None else self.kwargs.get("temperature", self.default_temperature)
        is_groq = "groq" in self.__class__.__name__.lower()
        is_openrouter = "openrouter" in self.__class__.__name__.lower()
        if max_tokens is not None:
            max_tok = max_tokens
        elif is_openrouter:
            max_tok = max(self.max_tokens, 16384) if self.thinking_level != "none" else max(self.max_tokens, 8192)
        else:
            max_tok = self.max_tokens

        if response_schema:
            is_array_schema = isinstance(response_schema, dict) and response_schema.get("type") == "array"

            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tok,
                "temperature": eff_temp,
            }

            if is_openrouter:
                # OpenRouter with reasoning: Avoid sending response_format if reasoning is active,
                # as upstream inference engines often reject/strip it. Prompt-enforced JSON is 100% reliable.
                if self.thinking_level == "none" and not is_array_schema:
                    kwargs["response_format"] = {"type": "json_object"}
                json_hint = f"\n\nYou MUST return valid JSON conforming to this schema:\n{json.dumps(response_schema)}"
                user_msg = kwargs["messages"][-1]["content"]
                if isinstance(user_msg, str):
                    kwargs["messages"][-1]["content"] += json_hint
                elif isinstance(user_msg, list):
                    kwargs["messages"][-1]["content"].append({"type": "text", "text": json_hint})
            elif is_groq:
                if not is_array_schema:
                    kwargs["response_format"] = {"type": "json_object"}
                json_hint = f"\n\nYou MUST return valid JSON conforming to this schema:\n{json.dumps(response_schema)}"
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
                    return ""
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
                    await self._save_token_usage(self.model, "generate_content", inp, outp, **kw)
                if not response.choices:
                    return ""
                choice = response.choices[0]
                finish_reason = getattr(choice, "finish_reason", None)
                if finish_reason == "length":
                    logger.warning(
                        f"[{self.model}] generate_content: response truncated by token limit (finish_reason='length', max_tokens={kwargs.get('max_tokens')})"
                    )
                return _extract_message_text(choice)
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
                                await self._save_token_usage(self.model, "generate_content", inp, outp, **kw)
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
                            await self._save_token_usage(self.model, "generate_content", inp, outp, **kw)
                        if not response.choices:
                            return ""
                        return _extract_message_text(response.choices[0])
                    except (StreamTimeoutError, StreamSafetyTimeoutError) as fb_to:
                        logger.warning(f"[{self.model}] generate_content fallback streaming timeout: {fb_to}")
                        raise
                    except Exception as fallback_err:
                        if is_subclass_provider:
                            raise
                        logger.warning(f"Structured JSON fallback failed for {self.model}: {fallback_err}")
                        return ""
                if is_subclass_provider:
                    raise
                logger.warning(f"OpenAI generate_content failed for {self.model}: {e}")
                return ""

        else:
            return await self.generate(user_message, system_prompt, temperature=temperature)

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
        sys_prompt = (
            system_prompt
            or "You are a data classification assistant. Always output valid JSON conforming to the schema requested."
        )
        for attempt in range(2):
            try:
                # If attempt > 0 (retry after parse failure or truncated output), expand token budget to 32768
                override_tokens = 32768 if attempt > 0 else max_tokens
                result_text = await self.generate_content(
                    sys_prompt, prompt, response_schema=schema, temperature=temperature, max_tokens=override_tokens
                )
                if not result_text:
                    if attempt == 0:
                        await asyncio.sleep(1.0)
                        continue
                    logger.warning(f"[{self.model}] classify_json: generate_content returned empty/None")
                    return None
                from monika.infrastructure.providers.base_provider import extract_and_parse_json

                parsed = extract_and_parse_json(result_text)
                if parsed is not None:
                    return parsed
                logger.warning(f"[{self.model}] classify_json: parse failed on text: {result_text[:250]}")
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue
                return None
            except Exception as e:
                logger.warning(f"[{self.model}] classify_json exception ({type(e).__name__}): {e}")
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue
                return None
        return None

    def _convert_tools(self, tools: list) -> list:
        provider_name = self._get_provider_name()
        is_openrouter = (
            provider_name in ("openrouter", "9router")
            or "openrouter" in str(getattr(self.client, "base_url", "")).lower()
        )
        is_claude_or_qwen = any(k in self.model.lower() for k in ("claude", "anthropic", "qwen"))
        supports_cache_control = is_openrouter and is_claude_or_qwen

        from monika.infrastructure.providers.schema_normalizer import ToolSchemaNormalizer

        return ToolSchemaNormalizer.to_openai(tools, supports_cache_control=supports_cache_control)

    def _normalize_messages(self, messages: list) -> list:
        """Normalizes messages across heterogeneous provider formats (Anthropic/Gemini to OpenAI)."""
        call_id_to_name: dict[str, str] = {}
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            for tc in msg.get("tool_calls", []):
                if isinstance(tc, dict):
                    cid = tc.get("id")
                    fn_name = tc.get("function", {}).get("name")
                    if cid and fn_name:
                        call_id_to_name[str(cid)] = str(fn_name)
            c = msg.get("content")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        bid = b.get("id")
                        bname = b.get("name")
                        if bid and bname:
                            call_id_to_name[str(bid)] = str(bname)

        norm_messages = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "user")
            content = m.get("content")

            if isinstance(content, list):
                text_parts = []
                image_parts: list[dict[str, Any]] = []
                tool_calls = []
                tool_results = []
                thinking_parts = []

                for block in content:
                    b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if b_type == "text":
                        text_val = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                        if text_val:
                            text_parts.append(text_val)
                    elif b_type == "image":
                        source = block.get("source", {}) if isinstance(block, dict) else getattr(block, "source", {})
                        if isinstance(source, dict):
                            media_type = str(source.get("media_type", "image/jpeg"))
                            data = str(source.get("data", ""))
                            if data:
                                image_parts.append(
                                    {
                                        "type": "image_url",
                                        "image_url": {"url": f"data:{media_type};base64,{data}"},
                                    }
                                )
                    elif b_type == "image_url":
                        img_url_data = (
                            block.get("image_url", {}) if isinstance(block, dict) else getattr(block, "image_url", {})
                        )
                        if isinstance(img_url_data, dict) and img_url_data.get("url"):
                            image_parts.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": str(img_url_data["url"])},
                                }
                            )
                        elif isinstance(img_url_data, str) and img_url_data:
                            image_parts.append(
                                {
                                    "type": "image_url",
                                    "image_url": {"url": img_url_data},
                                }
                            )
                    elif b_type in ("thinking", "thought"):
                        t_val = block.get("thinking") if isinstance(block, dict) else getattr(block, "thinking", None)
                        if not t_val:
                            t_val = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                        if t_val:
                            thinking_parts.append(str(t_val))
                    elif b_type == "tool_result":
                        c_val = block.get("content") if isinstance(block, dict) else getattr(block, "content", "")
                        tid = (
                            block.get("tool_use_id")
                            if isinstance(block, dict)
                            else getattr(block, "tool_use_id", "call_0")
                        )
                        raw_tname = block.get("name") if isinstance(block, dict) else getattr(block, "name", None)
                        if not raw_tname or str(raw_tname).lower() == "none":
                            raw_tname = call_id_to_name.get(str(tid)) or "tool"
                        tname = str(raw_tname)
                        content_str = json.dumps(c_val, default=str) if not isinstance(c_val, str) else c_val
                        if (
                            "gemini" in self.model.lower()
                            or "google" in self.model.lower()
                            or getattr(self, "provider_name", "") == "google"
                        ):
                            try:
                                parsed = json.loads(content_str)
                                if not isinstance(parsed, (dict, list)):
                                    content_str = json.dumps({"output": content_str})
                            except Exception:
                                content_str = json.dumps({"output": content_str})

                        tool_results.append(
                            {
                                "role": "tool",
                                "tool_call_id": str(tid),
                                "name": tname,
                                "content": content_str,
                            }
                        )
                    elif b_type == "tool_use":
                        tname = block.get("name") if isinstance(block, dict) else getattr(block, "name", "tool")
                        tinput = block.get("input") if isinstance(block, dict) else getattr(block, "input", {})
                        tid = block.get("id") if isinstance(block, dict) else getattr(block, "id", "call_0")
                        tool_calls.append(
                            {
                                "id": str(tid),
                                "type": "function",
                                "function": {
                                    "name": tname,
                                    "arguments": json.dumps(tinput) if not isinstance(tinput, str) else tinput,
                                },
                            }
                        )

                if role == "assistant" or tool_calls:
                    ast_msg: dict[str, Any] = {"role": "assistant"}
                    ast_msg["content"] = " ".join(text_parts) if text_parts else ""
                    if tool_calls:
                        ast_msg["tool_calls"] = tool_calls
                    if m.get("reasoning_content"):
                        ast_msg["reasoning_content"] = m["reasoning_content"]
                    elif thinking_parts:
                        ast_msg["reasoning_content"] = "\n".join(thinking_parts)
                    for k in ("thought_signature", "thought", "reasoning_details", "extra_content"):
                        if k in m and m[k] is not None:
                            ast_msg[k] = m[k]
                    norm_messages.append(ast_msg)
                    if tool_results:
                        norm_messages.extend(tool_results)
                        tool_results = []
                else:
                    if tool_results:
                        norm_messages.extend(tool_results)
                        tool_results = []
                    if image_parts and role == "user":
                        content_payload: list[dict[str, Any]] = []
                        if text_parts:
                            content_payload.append({"type": "text", "text": " ".join(text_parts)})
                        content_payload.extend(image_parts)
                        norm_messages.append({"role": role, "content": content_payload})
                    elif text_parts:
                        norm_messages.append({"role": role, "content": " ".join(text_parts)})
            elif role == "tool":
                tid = m.get("tool_call_id", "")
                raw_name = m.get("name")
                if not raw_name or str(raw_name).lower() == "none":
                    m_copy = dict(m)
                    m_copy["name"] = call_id_to_name.get(str(tid)) or "tool"
                    norm_messages.append(m_copy)
                else:
                    norm_messages.append(dict(m))
            else:
                norm_messages.append(dict(m))
        return norm_messages

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any):
        if not self.client:
            raise Exception("OpenAI API client not initialized")

        req_messages = []
        static_sys = system_prompt
        dynamic_sys = ""
        compile_fn = getattr(system_prompt, "compile_stable_system", None)
        if isinstance(system_prompt, tuple) and len(system_prompt) >= 2:
            static_sys = system_prompt[0]
            dynamic_sys = str(system_prompt[1]).strip() if system_prompt[1] else ""
        elif callable(compile_fn):
            static_sys = compile_fn()
            dynamic_sys = getattr(system_prompt, "tier3_volatile", "")

        flat_sys = _flatten_system_prompt(static_sys)
        provider_name = self._get_provider_name()
        is_openrouter = (
            provider_name in ("openrouter", "9router")
            or "openrouter" in str(getattr(self.client, "base_url", "")).lower()
        )
        is_claude_or_qwen = any(k in self.model.lower() for k in ("claude", "anthropic", "qwen"))

        if flat_sys:
            if is_openrouter and is_claude_or_qwen:
                req_messages.append(
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": flat_sys, "cache_control": {"type": "ephemeral"}}],
                    }
                )
            else:
                req_messages.append({"role": "system", "content": flat_sys})

        norm_msgs = self._normalize_messages(messages)
        if dynamic_sys and norm_msgs:
            first_user_idx = next((i for i, m in enumerate(norm_msgs) if m.get("role") == "user"), None)
            if first_user_idx is not None:
                first_user = dict(norm_msgs[first_user_idx])
                user_content = first_user.get("content", "")
                if "<context_snapshot>" not in str(user_content):
                    if isinstance(user_content, str):
                        first_user["content"] = (
                            f"{user_content}\n\n<context_snapshot>\n{dynamic_sys}\n</context_snapshot>"
                        )
                    elif isinstance(user_content, list):
                        first_user["content"] = list(user_content) + [
                            {"type": "text", "text": f"\n\n<context_snapshot>\n{dynamic_sys}\n</context_snapshot>"}
                        ]
                norm_msgs[first_user_idx] = first_user

        if is_openrouter and is_claude_or_qwen:
            from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager

            cbm = CacheBreakpointManager()
            max_msg_bp = 2 if tools else 3
            norm_msgs = cbm.apply_to_messages(norm_msgs, max_message_breakpoints=max_msg_bp)

        req_messages.extend(norm_msgs)
        openai_tools = self._convert_tools(tools) if tools else None

        kwargs = {
            "model": self.model,
            "messages": req_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.kwargs.get("temperature", self.default_temperature),
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        self._apply_reasoning_params(kwargs)

        response = await self._create_chat_completion(kwargs)
        return response

    async def run_chat_loop(
        self, system_prompt: str, conversation_history: list, new_user_message: str, tools: list, tool_executor=None
    ) -> dict:
        if not self.client:
            return {"success": False, "reply": "OpenAI API not initialized.", "error": "Not initialized"}

        from monika.infrastructure.database.db import get_session

        async with get_session() as session:
            if tool_executor is not None:
                executor = tool_executor
            else:
                import importlib

                tool_executor_cls = importlib.import_module(
                    "monika.application.analysis.tools.tool_executor"
                ).ToolExecutor
                executor = tool_executor_cls(session, settings=self.settings, model_name=self.model)

            messages = []
            for msg in conversation_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": new_user_message})

            turns = 0
            tool_calls_made = 0
            final_text = ""
            proposed_action = None
            total_input = 0
            total_output = 0
            total_cached = 0
            total_thinking = 0
            consecutive_chat_tool_sig = None
            repeated_chat_tool_count = 0

            from monika.infrastructure.llm.context_compaction import ContextCompactionEngine

            compactor = ContextCompactionEngine(self.settings)

            while turns < self.max_tool_turns:
                turns += 1

                # NOTE: In-place observation masking REMOVED — it destroys server KV cache.
                # Tool results are immutable once appended to messages.
                # For token pressure, atomic compaction occurs at turn boundaries.

                try:
                    response = await self.run_tool_agent(messages, tools, system_prompt)
                except Exception as e:
                    logger.error(f"OpenAI chat error: {e}")
                    return {"success": False, "reply": f"API error: {e}", "error": str(e)}

                if not response:
                    logger.error("OpenAI chat error: empty response")
                    return {"success": False, "reply": "Maaf, respon model kosong.", "error": "Empty response"}

                if hasattr(response, "usage") and response.usage:
                    inp, outp, cached, thinking, _, cache_creation = self._extract_usage(response.usage)
                    total_input += inp
                    total_output += outp
                    total_cached += cached
                    total_thinking += thinking

                if not getattr(response, "choices", None) or len(response.choices) == 0:
                    logger.error("OpenAI chat error: empty choices in response")
                    return {
                        "success": False,
                        "reply": "Maaf, respon model kosong (empty choices).",
                        "error": "No choices in response",
                    }

                choice = response.choices[0]
                if not choice or not getattr(choice, "message", None):
                    logger.error("OpenAI chat error: choice missing message object")
                    return {
                        "success": False,
                        "reply": "Maaf, pesan model tidak ditemukan.",
                        "error": "No message in choice",
                    }

                message = choice.message
                ast_msg: dict[str, Any] = {"role": "assistant"}
                if message.content:
                    ast_msg["content"] = message.content

                if getattr(message, "reasoning_content", None):
                    ast_msg["reasoning_content"] = message.reasoning_content

                extra = getattr(message, "model_extra", {}) or {}
                for k in ("thought_signature", "thought", "reasoning_details", "extra_content"):
                    val = getattr(message, k, None) or (extra.get(k) if isinstance(extra, dict) else None)
                    if val is not None:
                        ast_msg[k] = val

                if message.tool_calls:
                    ast_msg["tool_calls"] = []
                    for t in message.tool_calls:
                        ast_msg["tool_calls"].append(
                            {
                                "id": t.id,
                                "type": "function",
                                "function": {"name": t.function.name, "arguments": t.function.arguments},
                            }
                        )
                messages.append(ast_msg)

                if message.content:
                    final_text = message.content

                # C1 Safety: Truncated tool call abort guard
                if getattr(choice, "finish_reason", None) == "length" and message.tool_calls:
                    logger.critical(
                        f"[SafetyGuard] Model output truncated (finish_reason=length) with {len(message.tool_calls)} "
                        f"tool call(s). Aborting execution to prevent malformed trade/analysis parameters."
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "[GUARDRAIL ERROR: Output was truncated mid-generation. Tool calls were aborted for safety. Please re-state concisely.]",
                        }
                    )
                    return {
                        "success": False,
                        "reply": "Respon model terpotong (max_tokens). Eksekusi tool dibatalkan demi keamanan parameter trading.",
                        "error": "TRUNCATED_TOOL_CALLS",
                        "aborted_tools": len(message.tool_calls),
                    }

                if not message.tool_calls:
                    break

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    from monika.application.agent.harness.tool_repair import repair_tool_arguments

                    tool_input = repair_tool_arguments(tool_call.function.arguments)

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
                            f"[OpenAI][ChatLoop] Anti-Oscillation: Suppressing repeated tool call #{repeated_chat_tool_count} for {tool_name}"
                        )
                        suppressed_result = {
                            "status": "already_executed",
                            "notice": f"Tool '{tool_name}' with identical parameters was already executed in this conversation turn. Do not repeat identical calls. Use data already obtained.",
                        }
                        tool_calls_made += 1
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": json.dumps(suppressed_result),
                            }
                        )
                        continue

                    tool_calls_made += 1

                    if tool_name == "propose_action":
                        proposed_action = tool_input
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_name,
                                "content": json.dumps({"status": "proposed", "message": "Action proposed to user."}),
                            }
                        )
                        continue

                    try:
                        res = await executor.execute(tool_name, tool_input)
                    except Exception as exec_err:
                        logger.error(f"OpenAI chat tool execution error ({tool_name}): {exec_err}", exc_info=True)
                        from monika.application.agent.harness.turn_failure_diagnostics import (
                            TurnFailureDiagnosticBuilder,
                        )

                        diag = TurnFailureDiagnosticBuilder.from_tool_execution_error(
                            turn_number=turns,
                            tool_name=tool_name,
                            tool_input=tool_input if isinstance(tool_input, dict) else {},
                            error_msg=str(exec_err),
                        )
                        res = {"status": "error", "error": str(exec_err), "_turn_failure_diagnostic": diag.to_dict()}
                    raw_content = json.dumps(res, default=str, ensure_ascii=False)
                    pruned_content = compactor.micro_prune(raw_content, tool_name=tool_name)
                    tool_content = pruned_content
                    if (
                        "gemini" in self.model.lower()
                        or "google" in self.model.lower()
                        or getattr(self, "provider_name", "") == "google"
                    ):
                        try:
                            parsed_check = json.loads(tool_content)
                            if not isinstance(parsed_check, (dict, list)):
                                tool_content = json.dumps({"output": tool_content})
                        except Exception:
                            tool_content = json.dumps({"output": tool_content})
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": tool_content}
                    )

            await self._save_token_usage(
                self.model,
                "chat_telegram",
                total_input,
                total_output,
                cached_tokens=total_cached,
                thinking_tokens=total_thinking,
            )

            return {
                "success": True,
                "reply": final_text,
                "proposed_action": proposed_action,
                "tool_calls_made": tool_calls_made,
                "turns": turns,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "thinking_tokens": total_thinking,
            }
