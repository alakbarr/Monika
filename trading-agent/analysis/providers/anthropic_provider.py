import json
import logging
import os
import time
import asyncio
import random
import hashlib
from datetime import datetime, timezone
from typing import Optional, Any

import anthropic
from anthropic import (
    RateLimitError as AnthropicRateLimitError,
    APIStatusError as AnthropicAPIStatusError,
    APITimeoutError as AnthropicAPITimeoutError,
    APIConnectionError as AnthropicAPIConnectionError,
    BadRequestError as AnthropicBadRequestError,
    AuthenticationError as AnthropicAuthError,
)
from sqlalchemy.ext.asyncio import AsyncSession
from utils.api.claude_rate_limiter import ClaudeRateLimiter
from utils.api.streaming import StreamConfig, StreamTimeoutError, StreamSafetyTimeoutError

from analysis.tools.tool_executor import ToolExecutor
from database.models import ActivityLog
from analysis.providers.base_provider import BaseLLMClient, MockResponse

logger = logging.getLogger("TradingAgent.AnthropicProvider")

def _build_system_blocks(system_prompt) -> list[dict]:
    """
    Menerima system_prompt sebagai:
      - list of dicts (langsung dari CacheBreakpointManager.wrap_system_tiers()), ATAU
      - str biasa (backward compatible, di-cache jadi satu block), ATAU
      - tuple (static_cacheable_text, dynamic_per_call_text)
    """
    if not system_prompt:
        return []
    if isinstance(system_prompt, list):
        return [b for b in system_prompt if isinstance(b, dict) and b.get("text", "").strip()]
    if isinstance(system_prompt, tuple):
        static_text, dynamic_text = system_prompt
        blocks = []
        if static_text and static_text.strip():
            blocks.append({'type': 'text', 'text': static_text, 'cache_control': {'type': 'ephemeral'}})
        if dynamic_text and dynamic_text.strip():
            blocks.append({'type': 'text', 'text': dynamic_text})
        return blocks
    if isinstance(system_prompt, str) and not system_prompt.strip():
        return []
    return [{'type': 'text', 'text': system_prompt, 'cache_control': {'type': 'ephemeral'}}]
class AnthropicProvider(BaseLLMClient):
    """
    Klien async Anthropic (Claude) dengan dukungan tool loop multi-turn.
    """

    def __init__(self, model: str, max_tokens: int = 8192, max_tool_turns: int = 15,
                 thinking_level: str = "none", settings: Optional[dict] = None, temperature: float = 0.0, **kwargs):
        super().__init__(model, max_tokens, max_tool_turns, thinking_level, settings, temperature, **kwargs)
        self.provider_name = "anthropic"
        api_key = kwargs.get("api_key") or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key and hasattr(anthropic, "AsyncAnthropic") and "unittest.mock" in type(anthropic.AsyncAnthropic).__module__:
            api_key = "mock_key"

        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set. Claude will not function.")
            self.client = None
        else:
            provider_cfg = (settings or {}).get("llm", {}).get("providers", {}).get("anthropic", {})
            max_retries = provider_cfg.get("max_retries", 3)
            timeout_sec = float(provider_cfg.get("timeout_seconds", 120.0))
            self.client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=max_retries, timeout=timeout_sec)

    def set_thinking_budget(self, budget: int) -> None:
        """Sets thinking budget and resolves corresponding Anthropic thinking parameters."""
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

    def _build_stream_config(self) -> StreamConfig:
        provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get("anthropic", {})
        stream_cfg = provider_cfg.get("streaming", {})
        return StreamConfig(
            idle_timeout=float(stream_cfg.get("idle_timeout_seconds", 30.0)),
            safety_timeout=float(stream_cfg.get("safety_timeout_seconds", 600.0)),
            first_chunk_timeout=float(stream_cfg.get("first_chunk_timeout_seconds", 60.0)),
        )

    async def _consume_anthropic_stream(self, create_kwargs: dict, config: Optional[StreamConfig] = None):
        """
        Consumes Anthropic async message stream with idle-timeout liveness tracking.
        """
        if not self.client:
            raise RuntimeError("Anthropic API client not initialized")

        if config is None:
            config = self._build_stream_config()

        start_time = time.monotonic()
        last_event_time = start_time
        is_first_chunk = True
        chunks_received = 0

        async with self.client.messages.stream(**create_kwargs) as stream:
            stream_iter = stream.__aiter__()
            while True:
                effective_timeout = (
                    config.first_chunk_timeout if is_first_chunk
                    else config.idle_timeout
                )
                try:
                    event = await asyncio.wait_for(
                        stream_iter.__anext__(),
                        timeout=effective_timeout
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    now = time.monotonic()
                    timeout_type = "first chunk" if is_first_chunk else "idle"
                    raise StreamTimeoutError(
                        f"Anthropic streaming {timeout_type} timeout ({effective_timeout:.0f}s) "
                        f"for {self.model} after {chunks_received} events",
                        idle_seconds=now - last_event_time,
                        chunks_received=chunks_received
                    )

                now = time.monotonic()
                if (now - start_time) > config.safety_timeout:
                    raise StreamSafetyTimeoutError(
                        f"Anthropic stream safety timeout {config.safety_timeout:.0f}s exceeded for {self.model}",
                        idle_seconds=now - last_event_time,
                        chunks_received=chunks_received
                    )

                last_event_time = now
                chunks_received += 1
                is_first_chunk = False

            return await stream.get_final_message()

    async def generate(self, prompt: str, system: str = "", temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[str]:
        """Single-turn text generation dengan retry otomatis untuk transient errors & dukungan reasoning penuh."""
        if not self.client:
            return None
            
        use_thinking = self.thinking_level is not None and str(self.thinking_level).lower() != 'none'
        ADAPTIVE_MODELS = ['sonnet-5', 'opus-5', 'opus-4-7', 'opus-4-8', 'sonnet-4-6', 'opus-4-6', 'adaptive']
        is_adaptive = use_thinking and any(x in self.model.lower() for x in ADAPTIVE_MODELS)
        thinking_budget = getattr(self, "thinking_budget", None) or self.THINKING_BUDGETS.get(self.thinking_level, 4096)

        eff_tokens = max_tokens if max_tokens is not None else self.max_tokens
        is_haiku = "haiku" in self.model.lower()
        if is_haiku:
            safe_max = min(eff_tokens, 8192)
        elif use_thinking:
            safe_max = min(max(eff_tokens, (thinking_budget or 4096) + 4096), 64000)
        else:
            safe_max = min(eff_tokens, 64000)
        eff_temp = temperature if temperature is not None else self.default_temperature

        create_kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            create_kwargs["system"] = _build_system_blocks(system)

        if use_thinking:
            if is_adaptive:
                create_kwargs["max_tokens"] = safe_max
                create_kwargs["thinking"] = {"type": "adaptive"}
                effort_level = self.thinking_level if self.thinking_level in ["low", "medium", "high", "xhigh", "max"] else "high"
                create_kwargs["output_config"] = {"effort": effort_level}
            else:
                create_kwargs["max_tokens"] = max(safe_max, thinking_budget + 4000)
                create_kwargs["temperature"] = 1.0
                create_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": thinking_budget
                }
        else:
            create_kwargs["max_tokens"] = safe_max
            create_kwargs["temperature"] = eff_temp

        provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get("anthropic", {})
        use_streaming = provider_cfg.get("streaming", {}).get("enabled", bool(self.settings))

        for attempt in range(2):
            try:
                await ClaudeRateLimiter.acquire_session_slot(self.model)
                if use_streaming:
                    response = await self._consume_anthropic_stream(create_kwargs)
                else:
                    response = await self.client.messages.create(**create_kwargs)
                
                if hasattr(response, 'usage') and response.usage:
                    inp = getattr(response.usage, 'input_tokens', 0)
                    outp = getattr(response.usage, 'output_tokens', 0)
                    cached_in = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
                    cache_create = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
                    outp_details = getattr(response.usage, 'output_tokens_details', None)
                    thinking = getattr(outp_details, 'thinking_tokens', 0) or 0 if outp_details else 0
                    await self._save_token_usage(self.model, "generate", inp, outp, cached_tokens=cached_in, cache_creation_tokens=cache_create, thinking_tokens=thinking)

                if response.content:
                    for block in response.content:
                        txt = getattr(block, "text", None)
                        if txt:
                            return txt
                return None
            except (StreamTimeoutError, StreamSafetyTimeoutError) as e:
                logger.warning(f"Anthropic generate streaming timeout on {self.model}: {e}")
                raise
            except (AnthropicAPITimeoutError, AnthropicAPIConnectionError) as e:
                if attempt == 0:
                    logger.warning(f"Anthropic generate network/timeout with {self.model}: {e}. Retrying in 3s...")
                    await asyncio.sleep(3.0)
                    continue
                logger.warning(f"Anthropic generate failed with {self.model}: {e}")
                return None
            except AnthropicRateLimitError as e:
                if attempt == 0:
                    wait = 5.0 + random.uniform(0, 1.5)
                    logger.warning(f"Anthropic generate 429 rate limit with {self.model}: {e}. Retrying in {wait:.1f}s...")
                    await asyncio.sleep(wait)
                    continue
                logger.warning(f"Anthropic generate rate limited with {self.model}: {e}")
                return None
            except AnthropicAPIStatusError as e:
                if e.status_code == 529 and attempt == 0:
                    wait = 6.0 + random.uniform(0, 2.0)
                    logger.warning(f"Anthropic generate 529 overloaded with {self.model}: {e}. Retrying in {wait:.1f}s...")
                    await asyncio.sleep(wait)
                    continue
                logger.warning(f"Anthropic generate API status error ({e.status_code}) with {self.model}: {e}")
                return None
            except Exception as e:
                err_str = str(e).lower()
                is_transient = 'timeout' in err_str or '529' in err_str or 'overloaded' in err_str or '429' in err_str
                if is_transient and attempt == 0:
                    logger.warning(f"Anthropic generate transient error with {self.model}: {e}. Retrying in 4s...")
                    await asyncio.sleep(4.0)
                    continue
                logger.warning(f"Anthropic generate failed with {self.model}: {e}")
                return None
        return None

    THINKING_CAPABLE_MODELS = [
        'claude-sonnet-5', 'claude-opus-5', 'claude-opus-4-8',
        'claude-opus-4-7', 'claude-sonnet-4-6', 'claude-opus-4-6'
    ]
    THINKING_BUDGETS = {'low': 1024, 'medium': 4096, 'high': 10000, 'xhigh': 16000, 'extended': 16000, 'max': 32000}

    async def classify_json(self, prompt: str, system_prompt: Optional[str] = None, schema: Optional[dict] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[dict]:
        """Menghasilkan output JSON valid."""
        if not self.client:
            return None
        eff_tokens = max_tokens if max_tokens is not None else self.max_tokens
        eff_temp = temperature if temperature is not None else self.default_temperature
        if schema:
            tool_def = {
                'name': 'emit_structured_response',
                'description': 'Emit the final structured JSON response conforming exactly to the schema.',
                'input_schema': schema,
            }
            ADAPTIVE_MODELS = ['sonnet-5', 'opus-5', 'opus-4-7', 'opus-4-8', 'sonnet-4-6', 'opus-4-6', 'adaptive']
            use_thinking = bool(self.thinking_level and str(self.thinking_level).lower() != "none" and any(x in self.model.lower() for x in self.THINKING_CAPABLE_MODELS))
            is_adaptive = use_thinking and any(x in self.model.lower() for x in ADAPTIVE_MODELS)
            
            from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
            cbm = CacheBreakpointManager()
            sys_blocks, cached_tools = cbm.wrap_classify_json(system_prompt, tool_def, pad_to_cache_threshold=True)
            if not sys_blocks:
                sys_blocks = _build_system_blocks(system_prompt)
            if not cached_tools:
                cached_tools = [tool_def]

            create_kwargs = {
                'model': self.model,
                'system': sys_blocks,
                'tools': cached_tools,
                'messages': [{'role': 'user', 'content': prompt}],
            }
            TELEGRAPHIC_DIRECTIVE = (
                "\n\n[TELEGRAPHIC THINKING PROTOCOL]: Think strictly in dense analytical bullet points. "
                "Verify math, test thesis against ATR/ADR boundaries, and conclude immediately. "
                "Zero conversational intros, retrospective meta-commentary, or rambling. "
                "After you finish reasoning, you MUST call the `emit_structured_response` tool exactly once with your final answer. "
                "Do not respond with plain text."
            )
            is_haiku = "haiku" in self.model.lower()
            output_headroom = 4096 if is_haiku else 8192

            if use_thinking:
                if is_adaptive:
                    create_kwargs['max_tokens'] = max(self.max_tokens, output_headroom)
                    create_kwargs['thinking'] = {'type': 'adaptive'}
                    effort_level = self.thinking_level if self.thinking_level in ['low', 'medium', 'high', 'xhigh', 'max'] else 'high'
                    create_kwargs['output_config'] = {'effort': effort_level}
                    # Adaptive thinking fully supports tool_choice
                    create_kwargs['tool_choice'] = {'type': 'tool', 'name': 'emit_structured_response'}
                else:
                    budget = getattr(self, "thinking_budget", None) or self.THINKING_BUDGETS.get(self.thinking_level, 4096)
                    create_kwargs['max_tokens'] = max(self.max_tokens, budget + output_headroom)
                    create_kwargs['thinking'] = {'type': 'enabled', 'budget_tokens': budget}
                    create_kwargs['temperature'] = 1.0
                    create_kwargs['messages'][0]['content'] = prompt + TELEGRAPHIC_DIRECTIVE
            else:
                create_kwargs['max_tokens'] = self.max_tokens
                create_kwargs['temperature'] = eff_temp
                create_kwargs['tool_choice'] = {'type': 'tool', 'name': 'emit_structured_response'}
            
            response = None
            provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get("anthropic", {})
            use_streaming = provider_cfg.get("streaming", {}).get("enabled", bool(self.settings))
            for attempt in range(2):
                try:
                    await ClaudeRateLimiter.acquire_session_slot(self.model)
                    if use_streaming:
                        response = await self._consume_anthropic_stream(create_kwargs)
                    else:
                        response = await self.client.messages.create(**create_kwargs)
                    break
                except (StreamTimeoutError, StreamSafetyTimeoutError) as e:
                    logger.warning(f"Anthropic classify_json streaming timeout on {self.model}: {e}")
                    raise
                except (AnthropicAPITimeoutError, AnthropicAPIConnectionError, AnthropicRateLimitError) as e:
                    if attempt == 0:
                        wait = 4.0 + random.uniform(0, 1.5)
                        logger.warning(f"Anthropic classify_json transient error with {self.model}: {e}. Retrying in {wait:.1f}s...")
                        await asyncio.sleep(wait)
                        continue
                    logger.warning(f"Anthropic structured classify_json failed with {self.model}: {e}")
                    return None
                except AnthropicAPIStatusError as e:
                    if e.status_code == 529 and attempt == 0:
                        wait = 6.0 + random.uniform(0, 2.0)
                        logger.warning(f"Anthropic classify_json 529 overloaded with {self.model}: {e}. Retrying in {wait:.1f}s...")
                        await asyncio.sleep(wait)
                        continue
                    logger.warning(f"Anthropic structured classify_json failed with {self.model}: {e}")
                    return None
                except Exception as e:
                    logger.warning(f'Anthropic structured classify_json failed with {self.model}: {e}')
                    return None

            if not response:
                return None

            if hasattr(response, 'usage') and response.usage:
                inp = getattr(response.usage, 'input_tokens', 0)
                outp = getattr(response.usage, 'output_tokens', 0)
                cached_in = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
                cache_create = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
                outp_details = getattr(response.usage, 'output_tokens_details', None)
                thinking = getattr(outp_details, 'thinking_tokens', 0) or 0 if outp_details else 0
                await self._save_token_usage(self.model, 'classify_json_structured', inp, outp,
                                             cached_tokens=cached_in, cache_creation_tokens=cache_create, thinking_tokens=thinking)

            for block in response.content:
                if block.type == 'tool_use':
                    return block.input
            if use_thinking:
                logger.warning(f'[{self.model}] classify_json+thinking produced no tool_use; retrying with forced tool_choice.')
                retry_kwargs = {
                    'model': self.model, 'max_tokens': self.max_tokens, 'temperature': eff_temp,
                    'system': system_prompt or '', 'tools': [tool_def],
                    'tool_choice': {'type': 'tool', 'name': 'emit_structured_response'},
                    'messages': [{'role': 'user', 'content': prompt}]
                }
                try:
                    if use_streaming:
                        response = await self._consume_anthropic_stream(retry_kwargs)
                    else:
                        response = await self.client.messages.create(**retry_kwargs)
                    for block in response.content:
                        if block.type == 'tool_use':
                            return block.input
                except Exception as re_err:
                    logger.warning(f"Anthropic classify_json forced retry failed with {self.model}: {re_err}")
            return None
                
        res = await self.generate_text(
            prompt + "\n\nRespond with ONLY valid JSON, no markdown, no explanation.",
            system_prompt=system_prompt or "",
            temperature=eff_temp
        )
        if not res or res.startswith("ERROR:"):
            return None
        from analysis.providers.base_provider import extract_and_parse_json
        parsed = extract_and_parse_json(res)
        if parsed is not None:
            return parsed
        logger.warning(f"JSON decode failed in Anthropic classify_json: {res[:200]}")
        return None



    async def run_tool_agent(self, messages: list, tools: list, system_prompt: str | tuple) -> Any:
        """Low-level multi-turn tool-calling. (Digunakan internal atau by agent_from_messages)."""
        if not self.client:
            raise Exception("Anthropic API client not initialized")
            
        ADAPTIVE_MODELS = ['sonnet-5', 'opus-5', 'opus-4-7', 'opus-4-8', 'sonnet-4-6', 'opus-4-6', 'adaptive']
        use_thinking = bool(self.thinking_level and str(self.thinking_level).lower() != "none" and any(x in self.model.lower() for x in self.THINKING_CAPABLE_MODELS))
        is_adaptive = use_thinking and any(x in self.model.lower() for x in ADAPTIVE_MODELS)
        
        thinking_budget = getattr(self, "thinking_budget", None) or self.THINKING_BUDGETS.get(self.thinking_level, 4096)
            
        system_block = _build_system_blocks(system_prompt)
        cached_tools = list(tools)
        if cached_tools:
            last = dict(cached_tools[-1])
            last["cache_control"] = {"type": "ephemeral"}
            cached_tools = cached_tools[:-1] + [last]

        normalized_messages = []
        for m in messages:
            if m.get("role") == "tool":
                tool_res_block = {
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": str(m.get("content", ""))
                }
                if normalized_messages and normalized_messages[-1].get("role") == "user" and isinstance(normalized_messages[-1].get("content"), list):
                    normalized_messages[-1]["content"].append(tool_res_block)
                else:
                    normalized_messages.append({
                        "role": "user",
                        "content": [tool_res_block]
                    })
            elif m.get("tool_calls"):
                content_blocks = []
                if m.get("content"):
                    content_blocks.append({"type": "text", "text": str(m["content"])})
                for tc in m["tool_calls"]:
                    fn = tc.get("function", {})
                    fn_name = fn.get("name", "")
                    fn_args = fn.get("arguments", {})
                    if isinstance(fn_args, str):
                        try:
                            fn_args = json.loads(fn_args)
                        except Exception:
                            fn_args = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"toolu_{fn_name}"),
                        "name": fn_name,
                        "input": fn_args
                    })
                normalized_messages.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            else:
                normalized_messages.append(m)

        from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
        cbm = CacheBreakpointManager()
        cached_messages = cbm.apply_to_messages(normalized_messages)

        create_kwargs = {
            'model': self.model,
            'system': system_block,
            'tools': cached_tools,
            'messages': cached_messages,
        }
        
        # Safe auto-ceiling for Anthropic to prevent token truncation
        is_haiku = "haiku" in self.model.lower()
        safe_max = min(max(self.max_tokens, 8192), 8192) if is_haiku else max(self.max_tokens, 64000)

        if use_thinking:
            if is_adaptive:
                create_kwargs['max_tokens'] = safe_max
                create_kwargs['thinking'] = {'type': 'adaptive'}
                effort_level = self.thinking_level if self.thinking_level in ['low', 'medium', 'high', 'xhigh', 'max'] else 'high'
                create_kwargs['output_config'] = {'effort': effort_level}
            else:
                create_kwargs['max_tokens'] = max(safe_max, thinking_budget + 4000)
                create_kwargs['temperature'] = 1.0
                create_kwargs['thinking'] = {
                    'type': 'enabled',
                    'budget_tokens': thinking_budget
                }
        else:
            create_kwargs['max_tokens'] = safe_max
            create_kwargs['temperature'] = self.default_temperature

        await ClaudeRateLimiter.acquire_session_slot(self.model)
        provider_cfg = (self.settings or {}).get("llm", {}).get("providers", {}).get("anthropic", {})
        use_streaming = provider_cfg.get("streaming", {}).get("enabled", bool(self.settings))
        if use_streaming:
            response = await self._consume_anthropic_stream(create_kwargs)
        else:
            response = await self.client.messages.create(**create_kwargs)
        
        return response

    async def run_chat_loop(
        self,
        system_prompt: str,
        conversation_history: list[dict],
        new_user_message: str,
        tools: list[dict],
        tool_executor=None,
    ) -> dict:
        if not self.client:
            return {"success": False, "reply": "Claude API not initialized.", "error": "Not initialized"}
        
        from database.db import get_session
        async with get_session() as session:
            executor = ToolExecutor(session, settings=self.settings, model_name=self.model)

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
            total_cache_read = 0
            total_cache_create = 0
            total_thinking = 0
            consecutive_chat_tool_sig = None
            repeated_chat_tool_count = 0

            from utils.llm.context_compaction import ContextCompactionEngine
            compactor = ContextCompactionEngine(self.settings)

            while turns < self.max_tool_turns:
                turns += 1

                # Cache-preserving proactive compaction gate: only mask when message volume threatens budget
                if len(messages) >= 8 and compactor.calculate_history_tokens(messages) >= 16000:
                    messages = compactor.mask_aged_observations(messages, keep_recent_turns=2)

                try:
                    response = await self.run_tool_agent(messages, tools, system_prompt)
                except Exception as e:
                    logger.error(f"Claude chat error: {e}")
                    return {"success": False, "reply": f"API error: {e}", "error": str(e)}

                if hasattr(response, 'usage') and response.usage:
                    total_input += getattr(response.usage, 'input_tokens', 0)
                    total_output += getattr(response.usage, 'output_tokens', 0)
                    total_cache_read += getattr(response.usage, 'cache_read_input_tokens', 0) or 0
                    total_cache_create += getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
                    outp_details = getattr(response.usage, 'output_tokens_details', None)
                    thinking = getattr(outp_details, 'thinking_tokens', 0) or 0 if outp_details else 0
                    total_thinking += thinking

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
                        logger.warning(f"[Anthropic][ChatLoop] Anti-Oscillation: Suppressing repeated tool call #{repeated_chat_tool_count} for {tool_name}")
                        suppressed_result = {
                            "status": "already_executed",
                            "notice": f"Tool '{tool_name}' with identical parameters was already executed in this conversation turn. Do not repeat identical calls. Use data already obtained."
                        }
                        tool_calls_made += 1
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(suppressed_result),
                        })
                        continue

                    tool_calls_made += 1

                    if tool_name == "propose_action":
                        proposed_action = tool_input
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps({"status": "proposed", "message": "Action proposed to user."})
                        })
                        continue

                    res = await executor.execute(tool_name, tool_input)
                    raw_res = json.dumps(res, default=str, ensure_ascii=False)
                    pruned_res = compactor.micro_prune(raw_res, tool_name=tool_name)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": pruned_res
                    })

                messages.append({"role": "user", "content": tool_results})

            await self._save_token_usage(self.model, "chat_telegram", total_input, total_output, cached_tokens=total_cache_read, cache_creation_tokens=total_cache_create, thinking_tokens=total_thinking)

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

    async def _log_tool_call(
        self,
        session: AsyncSession,
        stage_name: str,
        tool_name: str,
        tool_input: dict,
        result: dict,
    ) -> None:
        try:
            from database.db import get_session
            entry = ActivityLog(
                timestamp=datetime.now(timezone.utc),
                category="analysis",
                description=(
                    f"[{stage_name}] {tool_name}("
                    f"{json.dumps(tool_input, ensure_ascii=False)[:200]}) → "
                    f"{json.dumps(result, ensure_ascii=False, default=str)[:300]}"
                ),
                actor="claude",
            )
            async with get_session() as log_session:
                log_session.add(entry)
                await log_session.commit()
        except Exception as e:
            logger.debug(f"Failed to log tool call: {e}")
