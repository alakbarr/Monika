"""
Base LLM Client — interface abstrak yang WAJIB diimplementasikan oleh setiap provider.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any, Dict
import json
import logging

logger = logging.getLogger(__name__)


import re

def extract_and_parse_json(text: str) -> Optional[dict]:
    """
    Robust extraction and parsing of JSON from LLM responses.
    Handles:
    - Raw JSON dict/array
    - Markdown code blocks (```json ... ```, ``` ... ```)
    - Thought blocks (<think>...</think>, <thought>...</thought>)
    - Preamble/postamble conversational text
    """
    if not text or not isinstance(text, str):
        return None
    
    clean = text.strip()
    # Strip <think>...</think> and <thought>...</thought> blocks from reasoning models
    clean = re.sub(r"<(?:think|thought)>[\s\S]*?</(?:think|thought)>", "", clean, flags=re.IGNORECASE).strip()
    
    # 1. Try direct parse first
    try:
        res = json.loads(clean, strict=False)
        if isinstance(res, dict):
            return res
        if isinstance(res, list):
            return {"items": res}
    except (json.JSONDecodeError, ValueError):
        pass
    
    # 2. Try markdown code block extraction
    md_matches = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", clean, flags=re.IGNORECASE)
    for block in md_matches:
        try:
            res = json.loads(block.strip(), strict=False)
            if isinstance(res, dict):
                return res
            if isinstance(res, list):
                return {"items": res}
        except (json.JSONDecodeError, ValueError):
            # Try raw_decode on the block content
            b_clean = block.strip()
            sb = b_clean.find("{")
            if sb != -1:
                try:
                    obj, _ = json.JSONDecoder(strict=False).raw_decode(b_clean[sb:])
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    pass
            continue
            
    # 3. Try progressive raw_decode from first '{' or '['
    decoder = json.JSONDecoder(strict=False)
    
    start_brace = clean.find("{")
    if start_brace != -1:
        try:
            obj, _ = decoder.raw_decode(clean[start_brace:])
            if isinstance(obj, dict):
                return obj
            if isinstance(obj, list):
                return {"items": obj}
        except Exception:
            pass

    start_bracket = clean.find("[")
    if start_bracket != -1:
        try:
            obj, _ = decoder.raw_decode(clean[start_bracket:])
            if isinstance(obj, list):
                return {"items": obj}
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    # 3b. Python-literal repair: True/False/None + trailing commas (common LLM output)
    def _py_literal_safe(s: str) -> str:
        # Strip trailing commas before } or ] (incl. whitespace/newlines)
        s = re.sub(r",\s*(?=[\}\]])", "", s)
        # Quote bare Python literals outside of strings
        out, in_str, escape = [], False, False
        i = 0
        while i < len(s):
            ch = s[i]
            if in_str:
                out.append(ch)
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                i += 1
                continue
            if ch == '"':
                in_str = True
                out.append(ch)
                i += 1
                continue
            for lit, repl in (("True", "true"), ("False", "false"), ("None", "null")):
                if s.startswith(lit, i):
                    before = s[i - 1] if i > 0 else ""
                    after = s[i + len(lit)] if i + len(lit) < len(s) else ""
                    if not (before.isalnum() or before == "_") and not (after.isalnum() or after == "_"):
                        out.append(repl)
                        i += len(lit)
                        break
            else:
                out.append(ch)
                i += 1
        return "".join(out)

    for candidate in (clean, _py_literal_safe(clean)):
        try:
            res = json.loads(candidate, strict=False)
            if isinstance(res, dict):
                return res
            if isinstance(res, list):
                return {"items": res}
        except (json.JSONDecodeError, ValueError):
            pass
        # Preamble before JSON: raw_decode from first '{' or '['
        for opener, wrap in (("{", "dict"), ("[", "list")):
            idx = candidate.find(opener)
            if idx == -1:
                continue
            try:
                obj, _ = decoder.raw_decode(candidate[idx:])
                if wrap == "dict" and isinstance(obj, dict):
                    return obj
                if wrap == "list" and isinstance(obj, list):
                    return {"items": obj}
                if isinstance(obj, dict):
                    return obj
                if isinstance(obj, list):
                    return {"items": obj}
            except Exception:
                continue

    # 4. Fallback to regex outermost slice (for non-standard edge cases)
    end_brace = clean.rfind("}")
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        try:
            res = json.loads(clean[start_brace:end_brace + 1], strict=False)
            if isinstance(res, dict):
                return res
        except (json.JSONDecodeError, ValueError):
            pass
    end_bracket = clean.rfind("]")
    if start_bracket != -1 and end_bracket != -1 and end_bracket > start_bracket:
        try:
            res = json.loads(clean[start_bracket:end_bracket + 1], strict=False)
            if isinstance(res, list):
                return {"items": res}
        except (json.JSONDecodeError, ValueError):
            pass

    # 5. Fallback with JSON quote repair / sanitization (e.g. unescaped nested quotes "")
    try:
        repaired = re.sub(r':\s*""', r': "', clean)
        repaired = re.sub(r'""(\s*[,\]\}])', r'"\1', repaired)
        repaired = re.sub(r'""+', r'\"', repaired)
        
        try:
            res = json.loads(repaired, strict=False)
            if isinstance(res, dict):
                return res
            if isinstance(res, list):
                return {"items": res}
        except Exception:
            pass

        sb = repaired.find("{")
        if sb != -1:
            try:
                obj, _ = decoder.raw_decode(repaired[sb:])
                if isinstance(obj, dict):
                    return obj
                if isinstance(obj, list):
                    return {"items": obj}
            except Exception:
                pass
    except Exception:
        pass

    # 6. Fallback auto-repair for truncated streaming / token limit cutoff (unclosed strings, braces, brackets)
    try:
        # Strip unclosed markdown fence if present
        clean_stripped = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE).strip()
        clean_stripped = re.sub(r"\s*```$", "", clean_stripped, flags=re.IGNORECASE).strip()

        sb = clean_stripped.find("{")
        sbr = clean_stripped.find("[")
        start_idx = -1
        if sb != -1 and sbr != -1:
            start_idx = min(sb, sbr)
        elif sb != -1:
            start_idx = sb
        elif sbr != -1:
            start_idx = sbr

        if start_idx != -1:
            candidate = clean_stripped[start_idx:]

            def _repair_containers(s: str) -> Optional[dict]:
                stack = []
                in_str = False
                esc = False
                for ch in s:
                    if esc:
                        esc = False
                        continue
                    if ch == '\\' and in_str:
                        esc = True
                        continue
                    if ch == '"':
                        in_str = not in_str
                        continue
                    if not in_str:
                        if ch in ('{', '['):
                            stack.append(ch)
                        elif ch in ('}', ']'):
                            if stack:
                                top = stack[-1]
                                if (ch == '}' and top == '{') or (ch == ']' and top == '['):
                                    stack.pop()

                rep = s.rstrip()
                if in_str:
                    rep += '"'
                rep = re.sub(r",\s*$", "", rep)
                if re.search(r':\s*$', rep):
                    rep += 'null'
                for d in reversed(stack):
                    rep += '}' if d == '{' else ']'
                try:
                    r = json.loads(rep, strict=False)
                    if isinstance(r, dict):
                        return r
                    if isinstance(r, list):
                        return {"items": r}
                except Exception:
                    return None

            repaired_candidate = _repair_containers(candidate)
            if repaired_candidate is not None:
                return repaired_candidate

            # Progressive line-trimming recovery for truncated inner objects
            lines = candidate.splitlines()
            while len(lines) > 1:
                lines.pop()
                trimmed = "\n".join(lines)
                r = _repair_containers(trimmed)
                if r is not None:
                    return r
    except Exception:
        pass
            
    return None


def _flatten_system_prompt(system_prompt: Any) -> str:
    """
    Safely convert str, tuple, list, or dict-blocks system prompts into a single clean string.
    Useful for providers that only accept plain string system prompts.
    """
    if system_prompt is None:
        return ""
    if isinstance(system_prompt, (tuple, list)):
        parts = []
        for p in system_prompt:
            if isinstance(p, dict):
                parts.append(str(p.get("text", "")).strip())
            elif p:
                parts.append(str(p).strip())
        return "\n\n".join(part for part in parts if part)
    if isinstance(system_prompt, dict):
        return str(system_prompt.get("text", "")).strip()
    return str(system_prompt)


class MockBlock(dict):
    """
    Blok konten respons yang kompatibel dengan format Anthropic.
    DIPINDAHKAN dari gemini_client.py
    """
    def __init__(self, type, text=None, name=None, input=None, id=None):
        super().__init__()
        self["type"] = type
        if text is not None: self["text"] = text
        if name is not None: self["name"] = name
        if input is not None: self["input"] = input
        if id is not None: self["id"] = id

    @property
    def type(self): return self.get("type")
    @property
    def text(self): return self.get("text")
    @property
    def name(self): return self.get("name")
    @property
    def input(self): return self.get("input")
    @property
    def id(self): return self.get("id")


class MockResponse:
    """
    Response wrapper yang kompatibel dengan format Anthropic.
    DIPINDAHKAN dari gemini_client.py
    """
    is_paid: bool = False

    def __init__(self, content, stop_reason, input_tokens, output_tokens, thinking_tokens: int = 0, cached_tokens: int = 0, cache_creation_tokens: int = 0):
        self.content = content
        self.stop_reason = stop_reason
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.thinking_tokens = thinking_tokens
        self.cached_tokens = cached_tokens
        self.cache_creation_tokens = cache_creation_tokens
        self.is_paid = False
        class Usage:
            input_tokens: int = 0
            output_tokens: int = 0
            thinking_tokens: int = 0
            cache_creation_input_tokens: int = 0
            cache_read_input_tokens: int = 0
        self.usage = Usage()
        self.usage.input_tokens = input_tokens
        self.usage.output_tokens = output_tokens
        self.usage.thinking_tokens = thinking_tokens
        self.usage.cache_creation_input_tokens = cache_creation_tokens
        self.usage.cache_read_input_tokens = cached_tokens


class BaseLLMClient(ABC):
    """Abstract base — setiap provider WAJIB implement SEMUA method ini."""

    def __init__(self, model: str, max_tokens: int = 8192, max_tool_turns: int = 15,
                 thinking_level: str = "none", settings: Optional[dict] = None, temperature: float = 0.0, **kwargs):
        self.model = model
        self.max_tokens = max_tokens
        self.max_tool_turns = max_tool_turns
        self.thinking_level = thinking_level
        self.settings = settings or {}
        self.default_temperature = temperature
        self.role = kwargs.get('role', kwargs.get('task_role', model))
        self.task_role = self.role
        self.subsystem = kwargs.get('subsystem', None)
        self.symbol = kwargs.get('symbol', None)
        self.cycle_id = kwargs.get('cycle_id', None)
        self.thinking_budget: Optional[int] = kwargs.get('thinking_budget', None)
        from analysis.providers.capabilities import get_model_capabilities
        self.capabilities = get_model_capabilities(model)

    def set_thinking_budget(self, budget: int) -> None:
        """Set dynamic reasoning/thinking token budget for this client instance."""
        self.thinking_budget = budget

    @staticmethod
    def _infer_subsystem(task_role: Optional[str], task_name: Optional[str]) -> str:
        """Infers high-level subsystem category from role or task name."""
        txt = f"{task_role or ''} {task_name or ''}".lower()
        if "stage1" in txt or "fundamental" in txt:
            return "stage1"
        if "stage2" in txt or "per_asset" in txt or "session_trigger" in txt:
            return "stage2"
        if "debate" in txt:
            return "debate"
        if "news" in txt or "digest" in txt:
            return "news"
        if "risk" in txt or "adversarial" in txt or "adjudicat" in txt:
            return "risk_gate"
        if "specialist" in txt:
            return "specialist"
        if "telegram" in txt or "chat" in txt:
            return "telegram"
        if "reflection" in txt or "memory" in txt or "chronicle" in txt or "lesson" in txt:
            return "memory"
        return "system"

    # --- Core generation methods ---

    @abstractmethod
    async def generate(self, prompt: str, system: str = "", temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[str]:
        """Single-turn text generation. Returns plain text or None."""
        pass

    async def generate_content(self, system_prompt: str = "", user_message: str = "",
                                response_schema: Optional[dict] = None, temperature: Optional[float] = None,
                                max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[str]:
        """
        Generate content with optional JSON schema enforcement.
        DEFAULT implementation delegates ke generate() + classify_json().
        Providers boleh override untuk native schema support.
        """
        if response_schema:
            result = await self.classify_json(
                user_message,
                system_prompt=system_prompt,
                schema=response_schema,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            return json.dumps(result) if result else None
        return await self.generate(user_message, system=system_prompt, temperature=temperature, max_tokens=max_tokens, **kwargs)

    async def generate_content_stream(self, system_prompt: str = "", user_message: str = "", conversation_history: Optional[list] = None, **kwargs: Any):
        """
        Stream content generation token-by-token or chunk-by-chunk.
        Default implementation delegates to generate_content and yields chunks.
        """
        prompt = user_message
        if conversation_history:
            history_lines = []
            for m in conversation_history:
                role = m.get("role", "user").capitalize()
                content = m.get("content", "")
                if content:
                    history_lines.append(f"{role}: {content}")
            if history_lines:
                prompt = f"Konversasi Sebelumnya:\n" + "\n".join(history_lines) + f"\n\nUser: {user_message}"
        full_text = await self.generate_content(system_prompt=system_prompt, user_message=prompt, **kwargs)
        if full_text:
            chunk_size = 20
            for i in range(0, len(full_text), chunk_size):
                yield full_text[i:i + chunk_size]

    @abstractmethod
    async def classify_json(self, prompt: str, system_prompt: Optional[str] = None, schema: Optional[dict] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[dict]:
        """Generate + parse JSON response."""
        pass

    # --- Compatibility wrappers (generasi lama) ---

    async def generate_text(self, user_prompt: str, system_prompt: str = "",
                            max_tokens: Optional[int] = 1024, temperature: Optional[float] = 0.0,
                            is_chat: bool = False) -> str:
        """Single-turn text generation (ClaudeClient compatibility)."""
        old_max = self.max_tokens
        if max_tokens and max_tokens != self.max_tokens:
            self.max_tokens = max_tokens
        try:
            result = await self.generate(user_prompt, system=system_prompt, temperature=temperature)
            return result or "ERROR: Generation failed"
        finally:
            self.max_tokens = old_max

    async def ask(self, prompt: str, system: str = "") -> str:
        """Alias for generate_text (ClaudeClient compatibility)."""
        return await self.generate_text(user_prompt=prompt, system_prompt=system)

    # --- Agent/Tool methods ---

    @abstractmethod
    async def run_tool_agent(self, messages: list, tools: list,
                              system_prompt: Any) -> Any:
        """Low-level multi-turn tool-calling. Returns MockResponse or native Message."""
        pass

    async def run_agent(self, session, system_prompt: str | tuple[str, str] | Any, user_message: str,
                        tools: list, stage_name: str = "unknown",
                        extra_context: Optional[str] = None,
                        prefetch_satisfied_tools: Optional[set] = None,
                        **kwargs) -> dict:
        """
        Full agent loop with tool execution + logging via AgentHarness (Pi Pattern).
        Returns: {"success": bool, "final_text": str, "tool_calls_made": int,
                  "turns": int, "input_tokens": int, "output_tokens": int,
                  "error": str|None, "context_messages": list|None,
                  "is_billing_error": bool|None}
        """
        from analysis.harness.agent_harness import AgentHarness
        harness = AgentHarness(
            llm_client=self,
            settings=self.settings,
            max_tool_turns=kwargs.get("max_tool_turns", self.max_tool_turns),
        )
        return await harness.run_agent(
            session=session,
            system_prompt=system_prompt,
            user_message=user_message,
            tools=tools,
            stage_name=stage_name,
            extra_context=extra_context,
            prefetch_satisfied_tools=prefetch_satisfied_tools,
            **kwargs,
        )

    @abstractmethod
    async def run_chat_loop(self, system_prompt: str, conversation_history: list,
                             new_user_message: str, tools: list,
                             tool_executor=None) -> dict:
        """
        Chat loop (Telegram).
        Returns: {"reply": str, "tool_calls_made": int, "turns": int,
                  "proposed_action": dict|None, "success": bool, "error": str|None}
        """
        pass

    async def run_agent_from_messages(self, session, system_prompt: str | tuple[str, str] | Any,
                                       messages: list, tools: list,
                                       max_tool_turns: int = 15,
                                       stage_name: str = "unknown",
                                       prefetch_satisfied_tools: Optional[set] = None,
                                       **kwargs) -> dict:
        """Continue agent from existing messages via AgentHarness (Pi Pattern)."""
        from analysis.harness.agent_harness import AgentHarness
        harness = AgentHarness(
            llm_client=self,
            settings=self.settings,
            max_tool_turns=max_tool_turns or self.max_tool_turns,
        )
        return await harness.run_agent_from_messages(
            session=session,
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            max_tool_turns=max_tool_turns,
            stage_name=stage_name,
            prefetch_satisfied_tools=prefetch_satisfied_tools,
            **kwargs,
        )

    def _get_session_affinity_headers(self) -> Dict[str, str]:
        """Generate session affinity headers to pin requests to the same GPU replica.
        Increases prompt cache hit rate across consecutive calls.
        Adopted from Pi's session routing pattern.
        """
        session_id = getattr(self, "_session_affinity_id", None)
        if not session_id:
            import hashlib
            role = getattr(self, "role", None) or getattr(self, "task_role", "default")
            session_id = hashlib.sha256(f"tradeagent_{role}".encode("utf-8")).hexdigest()[:32]
            self._session_affinity_id = session_id

        provider = getattr(self, "provider_name", "").lower()
        if "openrouter" in provider:
            return {"X-Session-ID": session_id}
        elif "openai" in provider:
            return {"X-Client-Request-ID": session_id}
        return {}

    def _preserve_reasoning_signatures(self, messages: list, target_provider: str) -> list:
        """Preserve opaque reasoning signatures for multi-turn replay.
        
        Models emit encrypted/opaque signatures (Anthropic redacted_thinking,
        Gemini thoughtSignature) that must be preserved when replaying the same model,
        but stripped when switching models to avoid schema errors.
        Adopted from Pi's transformMessages() pattern.
        """
        if not messages or not isinstance(messages, list):
            return messages

        target_prov = (target_provider or "").lower()
        sanitized = []
        for msg in messages:
            if not isinstance(msg, dict):
                sanitized.append(msg)
                continue

            msg_copy = dict(msg)
            content = msg_copy.get("content")

            if msg_copy.get("role") == "assistant" and isinstance(content, list):
                filtered_content = []
                for block in content:
                    if not isinstance(block, dict):
                        filtered_content.append(block)
                        continue

                    block_type = block.get("type", "")
                    # Anthropic redacted_thinking: preserve only for Anthropic replay
                    if block_type == "redacted_thinking":
                        if "anthropic" in target_prov:
                            filtered_content.append(block)
                        continue  # Strip for other providers

                    # Gemini thoughtSignature
                    if "thoughtSignature" in block and "gemini" not in target_prov:
                        block_clean = {k: v for k, v in block.items() if k != "thoughtSignature"}
                        filtered_content.append(block_clean)
                        continue

                    filtered_content.append(block)
                msg_copy["content"] = filtered_content

            sanitized.append(msg_copy)
        return sanitized

    # --- Tool Call logging (shared) ---

    async def _log_tool_call(self, session, stage_name: str, tool_name: str, tool_input: dict, result: dict) -> None:
        """Save tool call audit trail to ActivityLog using an isolated session."""
        try:
            from database.db import get_session
            from database.models import ActivityLog
            from datetime import datetime, timezone
            actor_name = getattr(self, "role", getattr(self, "model", "llm"))
            entry = ActivityLog(
                timestamp=datetime.now(timezone.utc),
                category="analysis",
                description=f"[{stage_name}] {tool_name}({json.dumps(tool_input, ensure_ascii=False, default=str)[:200]}) → {json.dumps(result, ensure_ascii=False, default=str)[:300]}",
                actor=actor_name
            )
            async with get_session() as log_session:
                log_session.add(entry)
                await log_session.commit()
        except Exception as e:
            logger.debug(f"Failed to log tool call: {e}")

    # --- Token logging (shared) ---

    async def _save_token_usage(
        self,
        model_name: str,
        task_name: str,
        input_tokens: int,
        output_tokens: int,
        session=None,
        task_role: Optional[str] = None,
        subsystem: Optional[str] = None,
        symbol: Optional[str] = None,
        cycle_id: Optional[str] = None,
        cached_tokens: int = 0,
        cache_creation_tokens: int = 0,
        thinking_tokens: int = 0,
        execution_time_ms: Optional[int] = None,
        status: str = "success",
        slot_name: str = "primary",
        exact_cost: Optional[float] = None,
        is_direct_free_tier: Optional[bool] = None,
    ) -> None:
        """Save comprehensive token usage to DB. Shared implementation for all providers."""
        if input_tokens == 0 and output_tokens == 0:
            return
        try:
            from database.models import TokenUsageLog
            from database.db import get_session

            resolved_role = task_role or getattr(self, "role", None) or getattr(self, "task_role", None)
            resolved_subsystem = subsystem or getattr(self, "subsystem", None) or self._infer_subsystem(resolved_role, task_name)
            resolved_symbol = symbol or getattr(self, "symbol", None)
            resolved_cycle_id = cycle_id or getattr(self, "cycle_id", None)

            provider_name = getattr(self, "provider_name", None)
            if not provider_name:
                cls_name = self.__class__.__name__.replace("Provider", "").replace("Client", "").replace("Wrapper", "").lower()
                provider_name = cls_name or "llm"

            cost_estimate = None
            if exact_cost is not None and isinstance(exact_cost, (int, float)) and exact_cost >= 0:
                cost_estimate = round(float(exact_cost), 6)
            else:
                try:
                    from utils.analytics.pricing import cost_usd
                    kwargs = {"cached_tokens": cached_tokens, "provider": provider_name}
                    if is_direct_free_tier is not None:
                        kwargs["is_direct_free_tier"] = is_direct_free_tier
                    cost_estimate = cost_usd(
                        model_name,
                        input_tokens,
                        output_tokens,
                        **kwargs
                    )
                except Exception:
                    pass

            # Track cache miss diagnostics (Pi pattern)
            try:
                from utils.llm.cache_miss_detector import global_cache_miss_detector
                global_cache_miss_detector.check(
                    cached_tokens=cached_tokens,
                    cache_creation_tokens=cache_creation_tokens,
                    model=model_name,
                    input_tokens=input_tokens,
                )
            except Exception:
                pass

            try:
                from utils.llm.cycle_budget_guard import get_cycle_budget_guard
                guard = get_cycle_budget_guard(self.settings)
                guard.record(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    thinking_tokens=thinking_tokens,
                    cached_tokens=cached_tokens,
                    cost_usd=cost_estimate or 0.0,
                )
            except Exception:
                pass

            try:
                from utils.llm.context_tracker import get_context_tracker
                tracker = get_context_tracker()
                tracker.record_usage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_tokens,
                    model=model_name,
                    step=task_name or resolved_role or "general",
                )
            except Exception:
                pass

            log_entry = TokenUsageLog(
                provider=provider_name,
                model_name=model_name,
                task_name=task_name,
                task_role=resolved_role,
                subsystem=resolved_subsystem,
                symbol=resolved_symbol,
                cycle_id=resolved_cycle_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                thinking_tokens=thinking_tokens,
                total_tokens=input_tokens + output_tokens,
                cached_tokens=cached_tokens,
                cache_creation_tokens=cache_creation_tokens,
                cost_estimate=cost_estimate,
                execution_time_ms=execution_time_ms,
                status=status,
                slot_name=slot_name,
            )

            # CRITICAL FIX (Phase 1):
            # If caller explicitly provided a session (e.g. test mock or direct session),
            # add record but NEVER call commit on caller's session! Caller owns transaction lifecycle.
            # When session is None (standard for background LLM calls), write via an isolated session and commit.
            if session is not None:
                session.add(log_entry)
            else:
                async with get_session() as s:
                    s.add(log_entry)
                    await s.commit()
        except Exception as e:
            logger.debug(f"Failed to log token usage: {e}")

