import logging
import os
import json
import asyncio
import time
import re
import hashlib
from typing import Optional, Literal, ClassVar, Any

from dotenv import load_dotenv

from utils.api.http_retry import fetch_with_retry, RateLimitError
from utils.api.streaming import streaming_request, StreamConfig, StreamResult, StreamTimeoutError, StreamSafetyTimeoutError
from analysis.tools.tool_executor import ToolExecutor
from database.db import get_session
from database.models import TokenUsageLog
from utils.api.gemini_rate_limiter import GeminiRateLimiter
from analysis.providers.base_provider import BaseLLMClient, MockBlock, MockResponse, _flatten_system_prompt

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
            elif "text" in part:
                result.text += part.get("text", "")
            elif "functionCall" in part:
                fc = part["functionCall"]
                ts = part.get("thoughtSignature") or part.get("thought_signature") or fc.get("id")
                result.tool_calls.append({
                    "name": fc.get("name", ""),
                    "args": fc.get("args", {}),
                    "thoughtSignature": ts
                })
        finish = cand.get("finishReason", "")
        if finish:
            result.finish_reason = finish

    if "usageMetadata" in chunk:
        result.usage = chunk["usageMetadata"]

    return bool(result.finish_reason)

def _sanitize_schema_for_gemini(schema: dict) -> dict:
    if not isinstance(schema, dict):
        return schema
    
    sanitized = {}
    for k, v in schema.items():
        if k == "additionalProperties":
            continue
        if k == "anyOf" and isinstance(v, list):
            non_null_items = [
                item for item in v
                if isinstance(item, dict) and str(item.get("type", "")).lower() != "null"
            ]
            has_null = any(
                isinstance(item, dict) and str(item.get("type", "")).lower() == "null"
                for item in v
            )
            if has_null and len(non_null_items) == 1:
                inner = _sanitize_schema_for_gemini(non_null_items[0])
                for ik, iv in inner.items():
                    sanitized[ik] = iv
                sanitized["nullable"] = True
                continue
        if k == "type" and isinstance(v, list):
            valid_types = [t for t in v if t != "null"]
            sanitized[k] = valid_types[0].upper() if valid_types else "STRING"
            if "null" in v:
                sanitized["nullable"] = True
            continue
        if k == "type" and isinstance(v, str):
            sanitized[k] = v.upper()
            continue
            
        if isinstance(v, dict):
            sanitized[k] = _sanitize_schema_for_gemini(v)
        elif isinstance(v, list):
            sanitized[k] = [_sanitize_schema_for_gemini(item) if isinstance(item, dict) else item for item in v]
        else:
            sanitized[k] = v
            
    return sanitized

GEMINI_MODEL_ALIASES = {
    "gemini-3.5-flash-lite": "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite": "gemini-3.1-flash-lite",
    "gemini-3.5-flash": "gemini-3.5-flash",
    "gemini-3.6-flash": "gemini-3.6-flash",
    "gemini-3.7-flash": "gemini-3.7-flash",
    "gemini-3-pro": "gemini-2.5-pro",
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
    
    def __init__(self, model: str, max_tokens: int = 65536, max_tool_turns: int = 15,
                 thinking_level: str = "none", settings: Optional[dict] = None, temperature: float = 0.0, **kwargs):
        super().__init__(model, max_tokens, max_tool_turns, thinking_level, settings, temperature, **kwargs)
        self.resolved_model = GEMINI_MODEL_ALIASES.get(model, model)
        self.thinking_level = thinking_level or "none"
        self.resolved_thinking_level = GEMINI_THINKING_LEVEL_MAP.get(str(self.thinking_level).lower(), "MINIMAL")

        api_keys_raw = os.getenv("GEMINI_API_KEYS", "")
        self.free_api_keys = [k.strip() for k in api_keys_raw.split(",") if k.strip()]
        cfg_api_key = (self.settings or {}).get("llm", {}).get("providers", {}).get("gemini", {}).get("api_key", "")
        self.paid_api_key = os.getenv("GEMINI_PAID_API_KEY", os.getenv("GEMINI_API_KEY", cfg_api_key))
        self.api_key: Optional[str] = kwargs.get("api_key") or cfg_api_key or None
        
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

    def _is_paid_key(self, api_key: Optional[str]) -> bool:
        """Menentukan apakah API key yang digunakan adalah GEMINI_PAID_API_KEY (berbayar)."""
        if not api_key:
            return False
        if self.paid_api_key and api_key == self.paid_api_key:
            return api_key not in self.free_api_keys
        return False

    def _get_api_key(self) -> Optional[str]:
        if self.api_key:
            return self.api_key
        if "pro" in self.model.lower():
            if self.paid_api_key:
                return self.paid_api_key
            else:
                logger.warning(f"Model {self.model} called but GEMINI_PAID_API_KEY is empty. Fallback to free key.")
                
        if not self.free_api_keys:
            return self.paid_api_key if self.paid_api_key else None

        now = time.time()
        
        for _ in range(len(self.free_api_keys)):
            key = self.free_api_keys[GeminiProvider._key_index % len(self.free_api_keys)]
            GeminiProvider._key_index += 1
            if key not in self.__class__._key_cooldowns or self.__class__._key_cooldowns[key] <= now:
                return key
                
        return None

    @classmethod
    def _handle_rate_limit_error(cls, api_key: str, error: Exception, method_name: str = "generate") -> None:
        """
        Klasifikasi rate limit Google Gemini API:
        - RPD (24h): Hanya jika respon eksplisit memuat indikator limit/kuota harian.
        - Retry-After header / body delay hint: Cooldown dinamis + 2.0s buffer.
        - RPM / TPM / Burst / Capacity Overload (65s): Default untuk seluruh HTTP 429 / RESOURCE_EXHAUSTED.
        """
        body = getattr(error, "body", "") or str(error)
        body_lower = body.lower()
        is_rpd = any(k in body_lower for k in [
            "requests per day", "per day", "rpd", "daily quota", "daily limit",
            "generatecontent requests per day", "exceeded your daily"
        ])
        if is_rpd:
            cls._key_cooldowns[api_key] = time.time() + 86400
            logger.error(f"Gemini key hit RPD quota in {method_name} ({api_key[:8]}...). Cooldown 24h.")
            return

        retry_after = getattr(error, "retry_after", None)
        if retry_after is not None and retry_after > 0:
            cooldown_sec = float(retry_after) + 2.0
        else:
            m = re.search(r"try again in ([\d\.]+)s", body_lower) or re.search(r"retry after (\d+)", body_lower)
            if m:
                try:
                    cooldown_sec = float(m.group(1)) + 2.0
                except (ValueError, TypeError):
                    cooldown_sec = 65.0
            else:
                cooldown_sec = 65.0

        cls._key_cooldowns[api_key] = time.time() + cooldown_sec
        logger.warning(f"Gemini key hit RPM/TPM limit or transient overload in {method_name} ({api_key[:8]}...). Cooldown {cooldown_sec:.1f}s.")

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
                from utils.llm.adaptive_thinking import QuantizedThinkingAllocator
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

    def _build_thinking_config(self) -> dict:
        """
        Builds model-compatible thinkingConfig for Google Gemini API.
        - Gemini 2.5 series models use 'thinkingBudget' (integer).
        - Gemini 3.x / Flash series models use 'thinkingLevel' (Enum: LOW/MEDIUM/HIGH/MINIMAL).
        """
        model_name = str(self.model).lower()
        if "2.5" in model_name:
            if self.thinking_level and str(self.thinking_level).lower() == "none":
                return {"thinkingBudget": 0}
            return {"thinkingBudget": max(0, self.thinking_budget or 0)}
        return {"thinkingLevel": self.resolved_thinking_level}

    async def generate(self, prompt: str, system: Any = "", temperature: Optional[float] = None, max_tokens: Optional[int] = None, response_schema: Optional[dict] = None, **kwargs: Any) -> Optional[str]:
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
                tb = getattr(self, 'thinking_budget', None)
                if getattr(self, 'resolved_thinking_level', '') in ("HIGH", "XHIGH", "MAX"):
                    actual_budget = max(tb if tb is not None else 0, 8192)
                elif getattr(self, 'resolved_thinking_level', '') == "MEDIUM":
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
                tb = getattr(self, 'thinking_budget', None)
                if getattr(self, 'resolved_thinking_level', '') in ("HIGH", "XHIGH", "MAX"):
                    actual_budget = max(tb if tb is not None else 0, 8192)
                elif getattr(self, 'resolved_thinking_level', '') == "MEDIUM":
                    actual_budget = max(tb if tb is not None else 0, 4096)
                else:
                    actual_budget = max(tb if tb is not None else 0, 2048)
                eff_max_tokens = max(eff_max_tokens, actual_budget + 8192, 16384)

        eff_temp = temperature if temperature is not None else self.default_temperature
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": eff_max_tokens,
                "temperature": eff_temp,
                "thinkingConfig": self._build_thinking_config()
            },
        }

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
        max_attempts = min(len(self.free_api_keys) if self.free_api_keys else 1, 2)
        for attempt in range(max_attempts):
            api_key = self._get_api_key()
            if not api_key:
                logger.error("No Gemini API key available.")
                return None
                
            headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
            
            try:
                is_paid_attempt = self._is_paid_key(api_key)
                is_free_attempt = not is_paid_attempt
                if use_streaming:
                    stream_res = await streaming_request(
                        url, payload=payload, headers=headers,
                        config=stream_config, parser=_gemini_stream_parser,
                        model_name=self.model
                    )
                    usage = stream_res.usage or {}
                    inp = usage.get("promptTokenCount", 0)
                    outp = usage.get("candidatesTokenCount", 0)
                    cached = usage.get("cachedContentTokenCount", 0) or 0
                    thoughts = usage.get("thoughtsTokenCount", 0) or 0
                    if inp > 0 or outp > 0:
                        await self._save_token_usage(self.model, "generate", inp, outp, cached_tokens=cached, thinking_tokens=thoughts, is_direct_free_tier=is_free_attempt)
                    
                    if stream_res.finish_reason == "MAX_TOKENS":
                        logger.warning(f"Gemini {self.model} output truncated by token limit (finishReason=MAX_TOKENS, maxOutputTokens={eff_max_tokens}, outp={outp}, think={thoughts})")
                        if self.resolved_thinking_level != "MINIMAL":
                            logger.info(f"Gemini {self.model} attempting auto-recovery retry with thinkingLevel=MINIMAL (output truncated by token limit)...")
                            recovery_payload = dict(payload)
                            recovery_payload["generationConfig"] = dict(payload["generationConfig"])
                            recovery_payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}
                            recovery_payload["generationConfig"]["maxOutputTokens"] = 65536  # Max capacity saat recovery
                            try:
                                rec_res = await streaming_request(
                                    url, payload=recovery_payload, headers=headers,
                                    config=stream_config, parser=_gemini_stream_parser,
                                    model_name=self.model
                                )
                                if rec_res and rec_res.text:
                                    rec_usage = rec_res.usage or {}
                                    rec_inp = rec_usage.get("promptTokenCount", 0)
                                    rec_outp = rec_usage.get("candidatesTokenCount", 0)
                                    rec_cached = rec_usage.get("cachedContentTokenCount", 0) or 0
                                    rec_thoughts = rec_usage.get("thoughtsTokenCount", 0) or 0
                                    if rec_inp > 0 or rec_outp > 0:
                                        await self._save_token_usage(self.model, "generate", rec_inp, rec_outp, cached_tokens=rec_cached, thinking_tokens=rec_thoughts, is_direct_free_tier=is_free_attempt)
                                    return rec_res.text
                            except Exception as rec_err:
                                logger.warning(f"Gemini auto-recovery failed: {rec_err}")
                        elif outp > 0 and stream_res.text:
                            # Output terpotong tapi thinking kecil → kembalikan partial agar tidak semua hilang
                            logger.warning(f"Gemini {self.model} partial output returned (think={thoughts}, outp={outp}). Recovery not applicable.")
                            return stream_res.text

                    if stream_res.text:
                        return stream_res.text
                else:
                    data = await fetch_with_retry(
                        url, method="POST", json=payload, headers=headers,
                        timeout=int(timeout_sec), max_retries=1, raise_on_429=True, use_circuit_breaker=False
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
                            await self._save_token_usage(self.model, "generate", inp, outp, cached_tokens=cached, thinking_tokens=thoughts, is_direct_free_tier=is_free_attempt)

                        candidates = data.get("candidates", [])
                        if candidates:
                            finish_reason = candidates[0].get("finishReason", "")
                            if finish_reason == "MAX_TOKENS":
                                logger.warning(f"Gemini {self.model} output truncated by token limit (finishReason=MAX_TOKENS, maxOutputTokens={eff_max_tokens}, outp={outp}, think={thoughts})")
                                if self.resolved_thinking_level != "MINIMAL":
                                    logger.info(f"Gemini {self.model} attempting auto-recovery retry with thinkingLevel=MINIMAL...")
                                    recovery_payload = dict(payload)
                                    recovery_payload["generationConfig"] = dict(payload["generationConfig"])
                                    recovery_payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}
                                    recovery_payload["generationConfig"]["maxOutputTokens"] = 65536
                                    try:
                                        rec_data = await fetch_with_retry(
                                            url, method="POST", json=recovery_payload, headers=headers,
                                            timeout=int(timeout_sec), max_retries=1, raise_on_429=True, use_circuit_breaker=False
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
                raise
            except Exception as e:
                logger.warning(f"Gemini generate attempt {attempt+1} failed with key ({api_key[:8]}...): {e}")
        
        return None

    async def classify_json(self, prompt: str, system_prompt: Optional[str] = None, schema: Optional[dict] = None, temperature: Optional[float] = None, max_tokens: Optional[int] = None, **kwargs: Any) -> Optional[dict]:
        from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
        anchored_sys = CacheBreakpointManager.pad_system_prompt_to_threshold(
            system_prompt or "", model_name=self.model, provider_name="gemini"
        )
        full_prompt = prompt if schema else f"{prompt}\n\nRespond with ONLY valid JSON, no markdown, no explanation."
        result = await self.generate(full_prompt, system=anchored_sys, response_schema=schema, temperature=temperature, max_tokens=max_tokens, **kwargs)
        if not result:
            return None
        from analysis.providers.base_provider import extract_and_parse_json
        parsed = extract_and_parse_json(result)
        if parsed is not None:
            return parsed
        logger.warning(f'Gemini classify_json: parse failed (schema={bool(schema)}): {result[:200]}')
        return None

    async def run_tool_agent(self, messages: list, tools: list, system_prompt: Any) -> MockResponse:
        gemini_tools = []
        if tools:
            from analysis.providers.openai_provider import _canonicalize_schema
            sorted_tools = sorted(tools, key=lambda t: t.get("name", "") if isinstance(t, dict) else "")
            declarations = []
            for t in sorted_tools:
                if "input_schema" not in t: continue
                decl = {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": _canonicalize_schema(_sanitize_schema_for_gemini(t["input_schema"]))
                }
                declarations.append(decl)
            if declarations:
                gemini_tools = [{"functionDeclarations": declarations}]

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
                parts.append({
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"name": tool_name, "content": parsed_content}
                    }
                })
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
                    parts.append({
                        "functionCall": {
                            "name": fn_name,
                            "args": fn_args
                        }
                    })
                if m.get("content"):
                    parts.insert(0, {"text": str(m["content"])})
            else:
                raw_blocks = m.get("content")
                blocks = raw_blocks if isinstance(raw_blocks, list) else ([{"type": "text", "text": str(raw_blocks)}] if raw_blocks is not None else [])
                for block in blocks:
                    b_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", "text")
                    if b_type == "tool_result":
                        content_val = block.get("content", "") if isinstance(block, dict) else getattr(block, "content", "")
                        tool_use_id = block.get("tool_use_id") if isinstance(block, dict) else getattr(block, "tool_use_id", None)
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
                                "response": {"name": tool_name, "content": parsed_content}
                            }
                        }
                        if tool_use_id:
                            str_id = str(tool_use_id)
                            # thoughtSignature harus dari Gemini model response (bukan ID buatan kita).
                            # Gemini native signature: tidak memiliki prefix "call_", "toolu_", atau "gemini_tool_fallback_".
                            # ID "call_" = OpenAI format, "toolu_" = Anthropic format — keduanya bukan Gemini thought_signature.
                            # Tanpa thought_signature yang valid, Gemini 3.x akan return 400 pada multi-turn tool calling.
                            is_synthetic_id = (
                                str_id.startswith("gemini_tool_fallback_") or
                                str_id.startswith("call_") or
                                str_id.startswith("toolu_")
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
                        part_dict: dict[str, Any] = {
                            "functionCall": {
                                "name": name_val,
                                "args": input_val
                            }
                        }
                        if tool_id:
                            str_id = str(tool_id)
                            # Sama seperti tool_result: hanya pass thought_signature jika ID adalah Gemini native signature
                            is_synthetic_id = (
                                str_id.startswith("gemini_tool_fallback_") or
                                str_id.startswith("call_") or
                                str_id.startswith("toolu_")
                            )
                            if not is_synthetic_id:
                                part_dict["thoughtSignature"] = str_id
                        parts.append(part_dict)
                    elif b_type == "text":
                        text_val = block.get("text") if isinstance(block, dict) else getattr(block, "text", "")
                        parts.append({"text": text_val})
            if parts:
                gemini_contents.append({"role": role, "parts": parts})
            
        if dynamic_note:
            injected = False
            for gc in gemini_contents:
                if gc.get("role") == "user":
                    for p in gc.get("parts", []):
                        if "text" in p:
                            p["text"] = f"{p['text']}\n\n{dynamic_note}"
                            injected = True
                            break
                    if injected:
                        break
            if not injected and gemini_contents:
                gemini_contents[0]["parts"].append({"text": dynamic_note})

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

        payload = {
            "contents": gemini_contents, 
            "generationConfig": {
                "temperature": self.default_temperature,
                "maxOutputTokens": eff_max_tokens,
                "thinkingConfig": self._build_thinking_config()
            }
        }
        if flat_sys:
            from utils.llm.cache_breakpoint_manager import CacheBreakpointManager
            anchored_sys = CacheBreakpointManager.pad_system_prompt_to_threshold(
                flat_sys,
                model_name=self.model,
                provider_name="gemini"
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
        timeout_sec = float(provider_cfg.get("timeout_seconds", 120.0))
        max_attempts = min(len(self.free_api_keys) if self.free_api_keys else 1, 2)
        for attempt in range(max_attempts):
            api_key = self._get_api_key()
            if not api_key:
                break
            
            try:
                headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
                if use_streaming:
                    stream_res = await streaming_request(
                        url, payload=payload, headers=headers,
                        config=stream_config, parser=_gemini_stream_parser,
                        model_name=self.model
                    )
                    break
                else:
                    data = await fetch_with_retry(
                        url, method="POST", json=payload, headers=headers, timeout=int(timeout_sec),
                        max_retries=1, raise_on_429=True, use_circuit_breaker=False
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
                raise
            except Exception as e:
                last_req_err = e
                logger.warning(f"Gemini run_tool_agent attempt {attempt+1} failed with key ({api_key[:8]}...): {e}")
        
        if use_streaming:
            if stream_res is None:
                raise Exception(f"Gemini API streaming request failed for {self.model}: {last_req_err or 'all attempts failed'}")
            
            blocks = []
            stop_reason = "end_turn"
            if stream_res.finish_reason == "MAX_TOKENS":
                logger.warning(f"Gemini {self.model} run_tool_agent output truncated by token limit (finishReason=MAX_TOKENS, maxOutputTokens={eff_max_tokens})")
                stop_reason = "max_tokens"
            
            if stream_res.text:
                blocks.append(MockBlock(type="text", text=stream_res.text))
            
            import uuid
            for tc in stream_res.tool_calls:
                ts = tc.get("thoughtSignature") or f"gemini_tool_fallback_{uuid.uuid4().hex[:8]}"
                blocks.append(MockBlock(
                    type="tool_use", name=tc["name"], input=tc.get("args", {}),
                    id=ts
                ))
                stop_reason = "tool_use"
            
            usage = stream_res.usage or {}
            thoughts = usage.get("thoughtsTokenCount", 0) or 0
            resp = MockResponse(
                content=blocks, stop_reason=stop_reason,
                input_tokens=usage.get("promptTokenCount", 0),
                output_tokens=usage.get("candidatesTokenCount", 0),
                thinking_tokens=thoughts,
                cached_tokens=usage.get("cachedContentTokenCount", 0) or 0
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
                logger.warning(f"Gemini {self.model} run_tool_agent output truncated by token limit (finishReason=MAX_TOKENS, maxOutputTokens={eff_max_tokens})")
                stop_reason = "max_tokens"
            
            for part in parts:
                if "text" in part:
                    is_thought = part.get("thought") is True
                    if not is_thought:
                        blocks.append(MockBlock(type="text", text=part["text"]))
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    import uuid
                    ts = part.get("thoughtSignature") or part.get("thought_signature") or fc.get("id") or f"gemini_tool_fallback_{uuid.uuid4().hex[:8]}"
                    blocks.append(MockBlock(
                        type="tool_use", name=fc["name"], input=fc.get("args", {}), 
                        id=ts
                    ))
                    stop_reason = "tool_use"
                    
            usage = data.get("usageMetadata", {})
            thoughts = usage.get("thoughtsTokenCount", 0) or 0
            resp = MockResponse(
                content=blocks, stop_reason=stop_reason,
                input_tokens=usage.get("promptTokenCount", 0),
                output_tokens=usage.get("candidatesTokenCount", 0),
                thinking_tokens=thoughts,
                cached_tokens=usage.get("cachedContentTokenCount", 0) or 0
            )
            resp.is_paid = self._is_paid_key(api_key)
            return resp

    async def run_chat_loop(self, system_prompt: str, conversation_history: list, new_user_message: str, tools: list, tool_executor=None) -> dict:
        messages = [{"role": h["role"], "content": h["content"]} for h in conversation_history]
        messages.append({"role": "user", "content": new_user_message})

        from utils.llm.context_compaction import ContextCompactionEngine
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
                return {"reply": f"API error: {e}", "success": False, "error": str(e)}

            if getattr(response, "is_paid", False):
                any_turn_paid = True

            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens
            total_cached_tokens += getattr(response, "cached_tokens", 0) or 0
            total_thinking_tokens += getattr(response, "thinking_tokens", 0) or 0
            
            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            for block in assistant_content:
                if block.type == "text": final_text = block.text

            if response.stop_reason == "end_turn": break
            if response.stop_reason != "tool_use": break

            tool_results = []
            for block in assistant_content:
                if block.type != "tool_use": continue
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
                    logger.warning(f"[Gemini][ChatLoop] Anti-Oscillation: Suppressing repeated tool call #{repeated_chat_tool_count} for {tool_name}")
                    suppressed_result = {
                        "status": "already_executed",
                        "notice": f"Tool '{tool_name}' with identical parameters was already executed in this conversation turn. Do not repeat identical calls. Use data already obtained."
                    }
                    tool_calls_made += 1
                    tool_results.append({"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps(suppressed_result)})
                    continue

                tool_calls_made += 1

                if tool_name == "propose_action":
                    proposed_action = tool_input
                    tool_results.append({"type": "tool_result", "tool_use_id": tool_use_id, "content": json.dumps({"status": "proposed", "message": "Action proposed."})})
                    continue

                from database.db import get_session as _gs
                async with _gs() as session:
                    bound_executor = tool_executor or ToolExecutor(session, settings=self.settings, model_name=self.model)
                    result = await bound_executor.execute(tool_name, tool_input)
                raw_payload = json.dumps(result, ensure_ascii=False, default=str)
                pruned_payload = compactor.micro_prune(raw_payload, tool_name=tool_name)
                tool_results.append({"type": "tool_result", "tool_use_id": tool_use_id, "content": pruned_payload})

            messages.append({"role": "user", "content": tool_results})

        if total_input_tokens > 0 or total_output_tokens > 0:
            from database.db import get_session as _gs
            async with _gs() as session:
                await self._save_token_usage(self.model, "chat_telegram", total_input_tokens, total_output_tokens, session, cached_tokens=total_cached_tokens, thinking_tokens=total_thinking_tokens, is_direct_free_tier=not any_turn_paid)

        return {
            "reply": final_text or "Maaf, tidak ada respons teks.",
            "tool_calls_made": tool_calls_made,
            "turns": turns,
            "proposed_action": proposed_action,
            "success": True,
            "error": None,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "thinking_tokens": total_thinking_tokens
        }
