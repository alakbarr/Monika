import logging
import json
import asyncio
import time
import hashlib
import re
from types import SimpleNamespace
from typing import Dict, Any, Optional
import os
from analysis.providers.base_provider import BaseLLMClient, _flatten_system_prompt
from analysis.tools.tool_executor import ToolExecutor
from utils.api.streaming import StreamConfig, StreamTimeoutError, StreamSafetyTimeoutError

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
        return str(content)
        
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


class OpenAIProvider(BaseLLMClient):
    """
    Provider untuk model OpenAI (GPT-4o, GPT-4o-mini).
    Note: Requires `openai` package installed.
    """
    def __init__(self, model: str, max_tokens: int = 2048, api_key: Optional[str] = None, settings: Optional[dict] = None,
                 temperature: float = 0.0, max_tool_turns: int = 15, thinking_level: str = "none", **kwargs):
        super().__init__(model, max_tokens=max_tokens, max_tool_turns=max_tool_turns,
                         thinking_level=thinking_level, settings=settings, temperature=temperature, **kwargs)
        self.provider_name = "openai"
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
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

    def _get_provider_name(self) -> str:
        cls_name = self.__class__.__name__.lower()
        if "groq" in cls_name:
            return "groq"
        if getattr(self, "_is_deepseek", False) or "deepseek" in cls_name or "deepseek" in str(getattr(self, "model", "")).lower():
            return "deepseek"
        if "openrouter" in cls_name:
            return "openrouter"
        if getattr(self, "provider_name", None) and self.provider_name != "openai":
            return self.provider_name
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
                from utils.llm.adaptive_thinking import QuantizedThinkingAllocator
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
            provider_config.get("features", {}).get("reasoning_effort") or
            provider_config.get("features", {}).get("reasoning") or
            False
        )
        
        is_reasoning_model = any(x in self.model.lower() for x in ['o1', 'o3', 'gpt-5'])
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
        provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get(provider_name, {})
        stream_cfg = provider_cfg.get("streaming", {})
        default_idle = 15.0 if provider_name == "groq" else (60.0 if provider_name == "deepseek" else 45.0)
        default_first = 30.0 if provider_name == "groq" else (120.0 if provider_name in ["openrouter", "deepseek"] else 90.0)
        return StreamConfig(
            idle_timeout=float(stream_cfg.get("idle_timeout_seconds", default_idle)),
            safety_timeout=float(stream_cfg.get("safety_timeout_seconds", 600.0)),
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

        stream_iter = stream.__aiter__()
        while True:
            effective_timeout = (
                config.first_chunk_timeout if is_first_chunk
                else config.idle_timeout
            )
            try:
                chunk = await asyncio.wait_for(
                    stream_iter.__anext__(),
                    timeout=effective_timeout
                )
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                now = time.monotonic()
                timeout_type = "first chunk" if is_first_chunk else "idle"
                raise StreamTimeoutError(
                    f"OpenAI streaming {timeout_type} timeout ({effective_timeout:.0f}s) "
                    f"for {self.model} after {chunks_received} chunks",
                    idle_seconds=now - last_event_time,
                    chunks_received=chunks_received
                )

            now = time.monotonic()
            if (now - start_time) > config.safety_timeout:
                raise StreamSafetyTimeoutError(
                    f"OpenAI stream safety timeout {config.safety_timeout:.0f}s exceeded for {self.model}",
                    idle_seconds=now - last_event_time,
                    chunks_received=chunks_received
                )

            last_event_time = now
            chunks_received += 1
            is_first_chunk = False

            if hasattr(chunk, "usage") and chunk.usage:
                usage = chunk.usage

            if hasattr(chunk, "model") and chunk.model:
                served_model = chunk.model

            for choice in (getattr(chunk, "choices", None) or []):
                delta = getattr(choice, "delta", None)
                if delta:
                    if getattr(delta, "content", None):
                        content += delta.content
                    if getattr(delta, "reasoning_content", None):
                        reasoning += delta.reasoning_content
                    elif getattr(delta, "reasoning", None):
                        reasoning += delta.reasoning

                    tc_list = getattr(delta, "tool_calls", None) or []
                    for tc in tc_list:
                        idx = getattr(tc, "index", 0)
                        if idx not in tool_calls_dict:
                            tool_calls_dict[idx] = {
                                "id": getattr(tc, "id", "") or "",
                                "name": getattr(getattr(tc, "function", None), "name", "") or "",
                                "arguments": ""
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
                function=SimpleNamespace(
                    name=tc_data["name"],
                    arguments=tc_data["arguments"]
                )
            )
            tool_calls_objs.append(tc_obj)

        msg_obj = SimpleNamespace(
            content=content if content else None,
            reasoning=reasoning if reasoning else None,
            reasoning_content=reasoning if reasoning else None,
            tool_calls=tool_calls_objs if tool_calls_objs else None
        )
        choice_obj = SimpleNamespace(
            message=msg_obj,
            finish_reason=finish_reason or ("tool_calls" if tool_calls_objs else "stop")
        )
        return SimpleNamespace(
            choices=[choice_obj],
            usage=usage,
            model=served_model
        )

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
                m = re.search(r"(?:less than or equal to|must be <=|maximum value (?:for \w+ )?is)\s*[`'\"]?(\d+)", err_str)
                if m and ("max_completion_tokens" in err_str or "max_tokens" in err_str or "token" in err_str):
                    limit = int(m.group(1))
                    token_key = "max_completion_tokens" if "max_completion_tokens" in current_kwargs else "max_tokens"
                    old_val = current_kwargs.get(token_key)
                    if old_val and old_val > limit:
                        logger.warning(f"[{self.model}] Token ceiling clamp: {token_key}={old_val} exceeds model limit {limit}. Auto-recovering with {limit}.")
                        current_kwargs[token_key] = limit
                        self.max_tokens = min(self.max_tokens, limit)
                        continue

                # Case 3: Parameter swap: max_tokens not supported -> max_completion_tokens
                if ("max_tokens is not supported" in err_str or "use max_completion_tokens" in err_str) and "max_tokens" in current_kwargs:
                    logger.warning(f"[{self.model}] Swapping deprecated max_tokens to max_completion_tokens.")
                    current_kwargs["max_completion_tokens"] = current_kwargs.pop("max_tokens")
                    continue

                # Case 4: Parameter swap: max_completion_tokens unsupported -> max_tokens
                if ("unsupported parameter: max_completion_tokens" in err_str or "extra inputs are not permitted" in err_str) and "max_completion_tokens" in current_kwargs:
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

        # Prompt cache key optimization for modern OpenAI models (o1, o3, gpt-4o, gpt-5)
        if provider_name == "openai":
            is_cache_key_supported = any(m in str(self.model).lower() for m in ("gpt-4o", "gpt-4.1", "gpt-5", "o1", "o3"))
            if is_cache_key_supported:
                clean_role = re.sub(r'[^a-zA-Z0-9_-]', '_', str(getattr(self, "role", "agent")))
                sys_content = ""
                for m in (kwargs.get("messages") or []):
                    if isinstance(m, dict) and m.get("role") == "system":
                        sys_content = str(m.get("content") or "")
                        break
                tool_names = sorted([t.get("function", {}).get("name", "") for t in (kwargs.get("tools") or []) if isinstance(t, dict)])
                cache_sig = f"{clean_role}:{hashlib.sha256(sys_content.encode('utf-8')).hexdigest()[:16]}:{','.join(tool_names)}"
                cache_key = f"monika_{hashlib.sha256(cache_sig.encode('utf-8')).hexdigest()[:24]}"
                kwargs.setdefault("prompt_cache_key", cache_key)

        provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get(provider_name, {})
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
            inp = int(usage.get('prompt_tokens', 0) or 0)
            outp = int(usage.get('completion_tokens', 0) or 0)
            details = usage.get('prompt_tokens_details') or {}
            cached = 0
            if isinstance(details, dict):
                cached = int(details.get('cached_tokens', 0) or 0)
            if not cached:
                cached = int(usage.get('prompt_cache_hit_tokens', 0) or 0)

            cache_creation = int(usage.get('prompt_cache_miss_tokens', 0) or 0)
            if not cache_creation and isinstance(details, dict):
                cache_creation = int(details.get('cache_creation_tokens', 0) or 0)

            comp_details = usage.get('completion_tokens_details') or {}
            thinking = 0
            if isinstance(comp_details, dict):
                thinking = int(comp_details.get('reasoning_tokens', 0) or 0)

            c_cost = usage.get('total_cost') or usage.get('cost')
            exact_cost = float(c_cost) if c_cost is not None and isinstance(c_cost, (int, float)) and c_cost >= 0 else None
            return inp, outp, cached, thinking, exact_cost, cache_creation

        inp = getattr(usage, 'prompt_tokens', 0)
        inp = int(inp) if isinstance(inp, (int, float)) else 0
        outp = getattr(usage, 'completion_tokens', 0)
        outp = int(outp) if isinstance(outp, (int, float)) else 0

        details = getattr(usage, 'prompt_tokens_details', None)
        cached = 0
        if details:
            c_val = getattr(details, 'cached_tokens', 0) if not isinstance(details, dict) else details.get('cached_tokens', 0)
            if isinstance(c_val, (int, float)):
                cached = int(c_val)
        if not cached:
            hit_val = getattr(usage, 'prompt_cache_hit_tokens', 0)
            if isinstance(hit_val, (int, float)):
                cached = int(hit_val)

        cache_creation = getattr(usage, 'prompt_cache_miss_tokens', 0)
        cache_creation = int(cache_creation) if isinstance(cache_creation, (int, float)) else 0
        if not cache_creation and details:
            cc_val = getattr(details, 'cache_creation_tokens', 0) if not isinstance(details, dict) else details.get('cache_creation_tokens', 0)
            if isinstance(cc_val, (int, float)):
                cache_creation = int(cc_val)

        comp_details = getattr(usage, 'completion_tokens_details', None)
        thinking_tokens = 0
        if comp_details:
            r_val = getattr(comp_details, 'reasoning_tokens', 0) if not isinstance(comp_details, dict) else comp_details.get('reasoning_tokens', 0)
            if isinstance(r_val, (int, float)):
                thinking_tokens = int(r_val)

        exact_cost = None
        c_cost = getattr(usage, 'total_cost', None) or getattr(usage, 'cost', None)
        if c_cost is not None and isinstance(c_cost, (int, float)) and c_cost >= 0:
            exact_cost = float(c_cost)

        return int(inp), int(outp), cached, thinking_tokens, exact_cost, cache_creation

    async def generate(self, prompt: str, system: Optional[Any] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[str]:
        if not self.client:
            return None
        messages = []
        static_sys = system
        dynamic_sys = ""
        if isinstance(system, tuple) and len(system) >= 2:
            static_sys = system[0]
            dynamic_sys = str(system[1]).strip() if system[1] else ""
        flat_sys = _flatten_system_prompt(static_sys)
        if flat_sys:
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
            "model", "messages", "max_tokens", "max_completion_tokens", "temperature",
            "top_p", "n", "stream", "stream_options", "stop", "presence_penalty",
            "frequency_penalty", "logit_bias", "user", "response_format", "seed",
            "tools", "tool_choice", "parallel_tool_calls", "timeout", "extra_body",
            "extra_query", "extra_headers", "reasoning_effort", "prompt_cache_key",
        }
        call_kwargs = {k: v for k, v in kwargs.items() if k in openai_valid_params}
        call_kwargs.update({
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tok,
            "temperature": eff_temp
        })
        self._apply_reasoning_params(call_kwargs)
        try:
            response = await self._create_chat_completion(call_kwargs)
            if not response:
                return None
            self.last_served_model = getattr(response, 'model', None)
            if hasattr(response, 'usage') and response.usage:
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
            finish_reason = getattr(choice, 'finish_reason', None)
            if finish_reason == 'length':
                logger.warning(f"[{self.model}] generate: response truncated by token limit (finish_reason='length', max_tokens={kwargs.get('max_tokens')})")
            return _extract_message_text(choice)
        except (StreamTimeoutError, StreamSafetyTimeoutError) as e:
            logger.warning(f"[{self.model}] generate streaming timeout: {e}")
            raise
        except Exception as e:
            err_str = str(e).lower()
            is_subclass_provider = self.__class__.__name__ != "OpenAIProvider"
            if "prompt tokens limit exceeded" in err_str or "insufficient credits" in err_str:
                logger.warning(f"OpenRouter 402: prompt tokens exceed credit balance for {self.model} ({e}). Fail-fast to next fallback.")
                if is_subclass_provider:
                    raise
                return None
            if "402" in err_str or "fewer max_tokens" in err_str or "can only afford" in err_str:
                import re
                m = re.search(r"can only afford (\d+)", str(e))
                if m:
                    affordable = max(512, int(m.group(1)) - 64)
                    logger.warning(f"OpenRouter 402 credit clamp for {self.model}: retrying with max_tokens={affordable}")
                    try:
                        kwargs["max_tokens"] = affordable
                        response = await self._create_chat_completion(kwargs)
                        if not response:
                            return None
                        if hasattr(response, 'usage') and response.usage:
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
            if "429" in err_str or "rate limit" in err_str or "502" in err_str or "503" in err_str or "529" in err_str or "bad gateway" in err_str or "service unavailable" in err_str or "provider returned error" in err_str:
                if is_subclass_provider:
                    raise
            logger.warning(f"OpenAI generate failed with {self.model}: {e}")
            return None

    async def generate_content(self, system_prompt: str = "", user_message: str = "", response_schema: Optional[dict] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[str]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
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
                from analysis.schemas.pydantic_schemas import make_openai_strict_schema
                is_strict_capable = (self._get_provider_name() == "openai") or any(m in str(self.model).lower() for m in ("gpt-4o", "gpt-4.1", "o1", "o3"))
                
                if is_array_schema:
                    wrapped_schema = {
                        "type": "object",
                        "properties": {"items": response_schema},
                        "required": ["items"]
                    }
                    final_schema = make_openai_strict_schema(wrapped_schema) if is_strict_capable else wrapped_schema
                    kwargs["response_format"] = {
                        "type": "json_schema", 
                        "json_schema": {"name": "structured_response", "schema": final_schema, "strict": is_strict_capable}
                    }
                    json_hint = "\n\nYou MUST return a JSON object with key 'items' containing the array."
                    user_msg = kwargs["messages"][-1]["content"]
                    if isinstance(user_msg, str):
                        kwargs["messages"][-1]["content"] += json_hint
                else:
                    final_schema = make_openai_strict_schema(response_schema) if is_strict_capable else response_schema
                    kwargs["response_format"] = {
                        "type": "json_schema", 
                        "json_schema": {"name": "structured_response", "schema": final_schema, "strict": is_strict_capable}
                    }
                
            self._apply_reasoning_params(kwargs)
            try:
                response = await self._create_chat_completion(kwargs)
                if not response:
                    return ""
                self.last_served_model = getattr(response, 'model', None)
                if hasattr(response, 'usage') and response.usage:
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
                finish_reason = getattr(choice, 'finish_reason', None)
                if finish_reason == 'length':
                    logger.warning(f"[{self.model}] generate_content: response truncated by token limit (finish_reason='length', max_tokens={kwargs.get('max_tokens')})")
                return _extract_message_text(choice)
            except (StreamTimeoutError, StreamSafetyTimeoutError) as e:
                logger.warning(f"[{self.model}] generate_content streaming timeout: {e}")
                raise
            except Exception as e:
                err_str = str(e).lower()
                is_subclass_provider = self.__class__.__name__ != "OpenAIProvider"
                if "prompt tokens limit exceeded" in err_str or "insufficient credits" in err_str:
                    logger.warning(f"OpenRouter 402: prompt tokens exceed credit balance in generate_content for {self.model} ({e}). Fail-fast to fallback.")
                    if is_subclass_provider:
                        raise
                    return ""
                if "402" in err_str or "fewer max_tokens" in err_str or "can only afford" in err_str:
                    import re
                    m = re.search(r"can only afford (\d+)", str(e))
                    if m:
                        affordable = max(512, int(m.group(1)) - 64)
                        logger.warning(f"OpenRouter 402 credit clamp in generate_content for {self.model}: retrying with max_tokens={affordable}")
                        try:
                            kwargs["max_tokens"] = affordable
                            response = await self._create_chat_completion(kwargs)
                            if not response:
                                return ""
                            if hasattr(response, 'usage') and response.usage:
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
                            return _extract_message_text(response.choices[0])
                        except (StreamTimeoutError, StreamSafetyTimeoutError) as retry_to:
                            logger.warning(f"[{self.model}] generate_content retry streaming timeout: {retry_to}")
                            raise
                        except Exception as retry_err:
                            logger.warning(f"OpenRouter 402 retry failed in generate_content for {self.model}: {retry_err}")
                            if is_subclass_provider:
                                raise
                            return ""
                    else:
                        logger.warning(f"OpenRouter 402 credit limit reached for {self.model} in generate_content: {e}")
                        if is_subclass_provider:
                            raise
                        return ""
                if "json_schema" in err_str or "response_format" in err_str or "400" in err_str or "schema" in err_str or "unsupported" in err_str:
                    logger.warning(f"Structured response_format rejected by {self.model} ({e}), falling back to prompt-only JSON instruction.")
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
                        if hasattr(response, 'usage') and response.usage:
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

    async def classify_json(self, prompt: str, system_prompt: Optional[str] = None, schema: Optional[dict] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[dict]:
        if not self.client:
            return None
        sys_prompt = system_prompt or "You are a data classification assistant. Always output valid JSON conforming to the schema requested."
        for attempt in range(2):
            try:
                # If attempt > 0 (retry after parse failure or truncated output), expand token budget to 32768
                override_tokens = 32768 if attempt > 0 else max_tokens
                result_text = await self.generate_content(sys_prompt, prompt, response_schema=schema, temperature=temperature, max_tokens=override_tokens)
                if not result_text:
                    if attempt == 0:
                        await asyncio.sleep(1.0)
                        continue
                    logger.warning(f"[{self.model}] classify_json: generate_content returned empty/None")
                    return None
                from analysis.providers.base_provider import extract_and_parse_json
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
        # Lexicographical sort by tool name and recursive schema key sorting guarantees 100% deterministic prefix order for DeepSeek & OpenAI KV cache
        sorted_tools = sorted(tools, key=lambda t: t.get("name", "") if isinstance(t, dict) else "")
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": _canonicalize_schema(t.get("input_schema", {"type": "object", "properties": {}}))
                }
            }
            for t in sorted_tools
        ]

    def _normalize_messages(self, messages: list) -> list:
        """Normalizes messages across heterogeneous provider formats (Anthropic/Gemini to OpenAI)."""
        norm_messages = []
        for m in messages:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "user")
            content = m.get("content")

            if isinstance(content, list):
                text_parts = []
                tool_calls = []
                tool_results = []

                for block in content:
                    b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if b_type == "text":
                        text_val = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                        if text_val:
                            text_parts.append(text_val)
                    elif b_type == "tool_result":
                        c_val = block.get("content") if isinstance(block, dict) else getattr(block, "content", "")
                        tid = block.get("tool_use_id") if isinstance(block, dict) else getattr(block, "tool_use_id", "call_0")
                        tname = block.get("name") if isinstance(block, dict) else getattr(block, "name", "tool")
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": str(tid),
                            "name": str(tname),
                            "content": json.dumps(c_val, default=str) if not isinstance(c_val, str) else c_val
                        })
                    elif b_type == "tool_use":
                        tname = block.get("name") if isinstance(block, dict) else getattr(block, "name", "tool")
                        tinput = block.get("input") if isinstance(block, dict) else getattr(block, "input", {})
                        tid = block.get("id") if isinstance(block, dict) else getattr(block, "id", "call_0")
                        tool_calls.append({
                            "id": str(tid),
                            "type": "function",
                            "function": {
                                "name": tname,
                                "arguments": json.dumps(tinput) if not isinstance(tinput, str) else tinput
                            }
                        })

                if role == "assistant" or tool_calls:
                    ast_msg: dict[str, Any] = {"role": "assistant"}
                    ast_msg["content"] = " ".join(text_parts) if text_parts else ""
                    if tool_calls:
                        ast_msg["tool_calls"] = tool_calls
                    if m.get("reasoning_content"):
                        ast_msg["reasoning_content"] = m["reasoning_content"]
                    norm_messages.append(ast_msg)
                elif text_parts:
                    norm_messages.append({"role": role, "content": " ".join(text_parts)})

                if tool_results:
                    norm_messages.extend(tool_results)
            else:
                norm_messages.append(m)
        return norm_messages

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any):
        if not self.client:
            raise Exception("OpenAI API client not initialized")
        
        req_messages = []
        static_sys = system_prompt
        dynamic_sys = ""
        if isinstance(system_prompt, tuple) and len(system_prompt) >= 2:
            static_sys = system_prompt[0]
            dynamic_sys = str(system_prompt[1]).strip() if system_prompt[1] else ""
        elif hasattr(system_prompt, "compile_stable_system"):
            static_sys = system_prompt.compile_stable_system()
            dynamic_sys = getattr(system_prompt, "tier3_volatile", "")

        flat_sys = _flatten_system_prompt(static_sys)
        if flat_sys:
            req_messages.append({"role": "system", "content": flat_sys})

        norm_msgs = self._normalize_messages(messages)
        if dynamic_sys and norm_msgs:
            last_user = next((m for m in reversed(norm_msgs) if m.get("role") == "user"), None)
            if last_user and "<context_snapshot>" not in str(last_user.get("content", "")):
                if isinstance(last_user.get("content"), str):
                    last_user["content"] = f"{last_user['content']}\n\n<context_snapshot>\n{dynamic_sys}\n</context_snapshot>"
                elif isinstance(last_user.get("content"), list):
                    last_user["content"].append({"type": "text", "text": f"\n\n<context_snapshot>\n{dynamic_sys}\n</context_snapshot>"})

        req_messages.extend(norm_msgs)
        openai_tools = self._convert_tools(tools) if tools else None
        
        kwargs = {
            "model": self.model,
            "messages": req_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.kwargs.get("temperature", self.default_temperature)
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            
        self._apply_reasoning_params(kwargs)
            
        response = await self._create_chat_completion(kwargs)
        return response

    async def run_chat_loop(self, system_prompt: str, conversation_history: list, new_user_message: str, tools: list, tool_executor=None) -> dict:
        if not self.client:
            return {"success": False, "reply": "OpenAI API not initialized.", "error": "Not initialized"}
        
        from database.db import get_session
        async with get_session() as session:
            from analysis.tools.tool_executor import ToolExecutor
            executor = tool_executor or ToolExecutor(session, settings=self.settings, model_name=self.model)

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

            from utils.llm.context_compaction import ContextCompactionEngine
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

                if hasattr(response, 'usage') and response.usage:
                    inp, outp, cached, thinking, _, cache_creation = self._extract_usage(response.usage)
                    total_input += inp
                    total_output += outp
                    total_cached += cached
                    total_thinking += thinking

                if not getattr(response, 'choices', None) or len(response.choices) == 0:
                    logger.error("OpenAI chat error: empty choices in response")
                    return {"success": False, "reply": "Maaf, respon model kosong (empty choices).", "error": "No choices in response"}

                choice = response.choices[0]
                if not choice or not getattr(choice, 'message', None):
                    logger.error("OpenAI chat error: choice missing message object")
                    return {"success": False, "reply": "Maaf, pesan model tidak ditemukan.", "error": "No message in choice"}

                message = choice.message
                ast_msg: dict[str, Any] = {"role": "assistant"}
                if message.content:
                    ast_msg["content"] = message.content
                    
                if getattr(message, 'reasoning_content', None):
                    ast_msg["reasoning_content"] = message.reasoning_content
                    
                if message.tool_calls:
                    ast_msg["tool_calls"] = []
                    for t in message.tool_calls:
                        ast_msg["tool_calls"].append({
                            "id": t.id,
                            "type": "function",
                            "function": {
                                "name": t.function.name,
                                "arguments": t.function.arguments
                            }
                        })
                messages.append(ast_msg)

                if message.content:
                    final_text = message.content

                # C1 Safety: Truncated tool call abort guard
                if getattr(choice, 'finish_reason', None) == "length" and message.tool_calls:
                    logger.critical(
                        f"[SafetyGuard] Model output truncated (finish_reason=length) with {len(message.tool_calls)} "
                        f"tool call(s). Aborting execution to prevent malformed trade/analysis parameters."
                    )
                    messages.append({
                        "role": "user",
                        "content": "[GUARDRAIL ERROR: Output was truncated mid-generation. Tool calls were aborted for safety. Please re-state concisely.]"
                    })
                    return {
                        "success": False,
                        "reply": "Respon model terpotong (max_tokens). Eksekusi tool dibatalkan demi keamanan parameter trading.",
                        "error": "TRUNCATED_TOOL_CALLS",
                        "aborted_tools": len(message.tool_calls)
                    }

                if not message.tool_calls:
                    break

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_input = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tool_input = {}

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
                        logger.warning(f"[OpenAI][ChatLoop] Anti-Oscillation: Suppressing repeated tool call #{repeated_chat_tool_count} for {tool_name}")
                        suppressed_result = {
                            "status": "already_executed",
                            "notice": f"Tool '{tool_name}' with identical parameters was already executed in this conversation turn. Do not repeat identical calls. Use data already obtained."
                        }
                        tool_calls_made += 1
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": json.dumps(suppressed_result),
                        })
                        continue

                    tool_calls_made += 1
                    
                    if tool_name == "propose_action":
                        proposed_action = tool_input
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_name,
                            "content": json.dumps({"status": "proposed", "message": "Action proposed to user."})
                        })
                        continue

                    res = await executor.execute(tool_name, tool_input)
                    raw_content = json.dumps(res, default=str, ensure_ascii=False)
                    pruned_content = compactor.micro_prune(raw_content, tool_name=tool_name)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": pruned_content
                    })

            await self._save_token_usage(self.model, "chat_telegram", total_input, total_output, cached_tokens=total_cached, thinking_tokens=total_thinking)

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
