# ==============================================================================
# File: analysis/providers/provider_profile.py
# ==============================================================================

"""
Provider Capability Profiles & Universal Normalized Response Abstraction.
Institutional-grade multi-model orchestration architecture.

Unifies disparate upstream LLM response signatures (OpenAI, Anthropic, Gemini,
DeepSeek, Groq, OpenRouter, Ollama) into a single, standardized NormalizedResponse.
Extracts native or tag-embedded reasoning tokens, normalizes tool calls, and provides
standardized usage and cost telemetry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class TokenUsage:
    """Standardized token usage across all providers."""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens or (self.input_tokens + self.output_tokens),
        }


@dataclass
class NormalizedToolCall:
    """Standardized representation of a tool call."""
    id: str
    name: str
    arguments: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": self.arguments,
        }


@dataclass
class NormalizedResponse:
    """
    Universal representation of an LLM completion output.
    """
    text: str
    reasoning_content: Optional[str] = None
    tool_calls: List[NormalizedToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    finish_reason: str = "stop"  # "stop", "tool_calls", "length", "content_filter"
    provider: str = "unknown"
    model: str = "unknown"
    raw_response: Optional[Any] = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "reasoning_content": self.reasoning_content,
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "usage": self.usage.to_dict(),
            "finish_reason": self.finish_reason,
            "provider": self.provider,
            "model": self.model,
        }


_THINK_TAG_REGEX = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


@dataclass
class ProviderProfile:
    """
    Defines capabilities, format conventions, and limits of an LLM provider.
    """
    provider_name: str
    supports_native_thinking: bool = False
    supports_prompt_caching: bool = False
    supports_native_tools: bool = True
    context_window_limit: int = 128000
    output_token_ceiling: int = 8192
    default_temperature: float = 0.2

    def normalize_response(
        self,
        raw: Any,
        model_name: str = "",
    ) -> NormalizedResponse:
        """
        Normalizes a raw provider response into a universal NormalizedResponse.
        """
        if isinstance(raw, NormalizedResponse):
            return raw

        text = ""
        reasoning: Optional[str] = None
        tool_calls: List[NormalizedToolCall] = []
        usage = TokenUsage()
        finish_reason = "stop"

        # Case 1: Simple string response
        if isinstance(raw, str):
            text = raw

        # Case 2: Dict response (e.g. OpenAI JSON-like dict)
        elif isinstance(raw, dict):
            choices = raw.get("choices", [])
            if choices and isinstance(choices, list):
                first_choice = choices[0]
                finish_reason = first_choice.get("finish_reason", "stop") or "stop"
                msg = first_choice.get("message", {})
                text = msg.get("content") or ""
                reasoning = msg.get("reasoning_content") or msg.get("reasoning")

                raw_tools = msg.get("tool_calls", [])
                for t in raw_tools:
                    func = t.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args_dict = json.loads(args)
                        except Exception:
                            args_dict = {"raw": args}
                    else:
                        args_dict = args
                    tool_calls.append(
                        NormalizedToolCall(
                            id=t.get("id", f"call_{len(tool_calls)}"),
                            name=func.get("name", "unknown"),
                            arguments=args_dict,
                        )
                    )

            # Usage extraction
            raw_usage = raw.get("usage", {})
            usage = TokenUsage(
                input_tokens=raw_usage.get("prompt_tokens", 0),
                output_tokens=raw_usage.get("completion_tokens", 0),
                cached_tokens=raw_usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
                reasoning_tokens=raw_usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0),
                total_tokens=raw_usage.get("total_tokens", 0),
            )

        # Case 3: Object with choices/message (OpenAI SDK ChatCompletion)
        elif hasattr(raw, "choices") and raw.choices:
            choice = raw.choices[0]
            finish_reason = getattr(choice, "finish_reason", "stop") or "stop"
            msg = getattr(choice, "message", None)
            if msg:
                text = getattr(msg, "content", "") or ""
                reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
                raw_tools = getattr(msg, "tool_calls", None) or []
                for t in raw_tools:
                    func = getattr(t, "function", None)
                    func_name = getattr(func, "name", "unknown") if func else "unknown"
                    raw_args = getattr(func, "arguments", "{}") if func else "{}"
                    if isinstance(raw_args, str):
                        try:
                            args_dict = json.loads(raw_args)
                        except Exception:
                            args_dict = {"raw": raw_args}
                    else:
                        args_dict = raw_args
                    tool_calls.append(
                        NormalizedToolCall(
                            id=getattr(t, "id", f"call_{len(tool_calls)}"),
                            name=func_name,
                            arguments=args_dict,
                        )
                    )

            raw_usage = getattr(raw, "usage", None)
            if raw_usage:
                prompt_details = getattr(raw_usage, "prompt_tokens_details", None)
                comp_details = getattr(raw_usage, "completion_tokens_details", None)
                cached = getattr(prompt_details, "cached_tokens", 0) if prompt_details else 0
                reason_tok = getattr(comp_details, "reasoning_tokens", 0) if comp_details else 0
                usage = TokenUsage(
                    input_tokens=getattr(raw_usage, "prompt_tokens", 0),
                    output_tokens=getattr(raw_usage, "completion_tokens", 0),
                    cached_tokens=cached,
                    reasoning_tokens=reason_tok,
                    total_tokens=getattr(raw_usage, "total_tokens", 0),
                )

        # Case 4: Anthropic Message object
        elif hasattr(raw, "content") and isinstance(getattr(raw, "content"), list):
            content_blocks = raw.content
            text_parts = []
            for block in content_blocks:
                b_type = getattr(block, "type", "")
                if b_type == "text":
                    text_parts.append(getattr(block, "text", ""))
                elif b_type == "thinking":
                    reasoning = getattr(block, "thinking", "")
                elif b_type == "tool_use":
                    tool_calls.append(
                        NormalizedToolCall(
                            id=getattr(block, "id", f"call_{len(tool_calls)}"),
                            name=getattr(block, "name", "unknown"),
                            arguments=getattr(block, "input", {}),
                        )
                    )
            text = "".join(text_parts)
            raw_usage = getattr(raw, "usage", None)
            if raw_usage:
                usage = TokenUsage(
                    input_tokens=getattr(raw_usage, "input_tokens", 0),
                    output_tokens=getattr(raw_usage, "output_tokens", 0),
                    cached_tokens=getattr(raw_usage, "cache_read_input_tokens", 0),
                    total_tokens=getattr(raw_usage, "input_tokens", 0) + getattr(raw_usage, "output_tokens", 0),
                )
            finish_reason = getattr(raw, "stop_reason", "stop") or "stop"

        # If reasoning not explicitly set, check for embedded <think> tags
        if not reasoning and text and "<think>" in text:
            match = _THINK_TAG_REGEX.search(text)
            if match:
                reasoning = match.group(1).strip()
                text = _THINK_TAG_REGEX.sub("", text).strip()

        return NormalizedResponse(
            text=text,
            reasoning_content=reasoning,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=finish_reason,
            provider=self.provider_name,
            model=model_name,
            raw_response=raw,
        )


# Global profile lookup
_PROVIDER_PROFILES: Dict[str, ProviderProfile] = {
    "anthropic": ProviderProfile(
        provider_name="anthropic",
        supports_native_thinking=True,
        supports_prompt_caching=True,
        supports_native_tools=True,
        context_window_limit=200000,
        output_token_ceiling=8192,
    ),
    "openai": ProviderProfile(
        provider_name="openai",
        supports_native_thinking=True,
        supports_prompt_caching=True,
        supports_native_tools=True,
        context_window_limit=128000,
        output_token_ceiling=16384,
    ),
    "gemini": ProviderProfile(
        provider_name="gemini",
        supports_native_thinking=True,
        supports_prompt_caching=True,
        supports_native_tools=True,
        context_window_limit=1000000,
        output_token_ceiling=8192,
    ),
    "deepseek": ProviderProfile(
        provider_name="deepseek",
        supports_native_thinking=True,
        supports_prompt_caching=True,
        supports_native_tools=True,
        context_window_limit=64000,
        output_token_ceiling=8192,
    ),
    "groq": ProviderProfile(
        provider_name="groq",
        supports_native_thinking=False,
        supports_prompt_caching=False,
        supports_native_tools=True,
        context_window_limit=128000,
        output_token_ceiling=8192,
    ),
    "openrouter": ProviderProfile(
        provider_name="openrouter",
        supports_native_thinking=True,
        supports_prompt_caching=True,
        supports_native_tools=True,
        context_window_limit=128000,
        output_token_ceiling=8192,
    ),
    "ollama": ProviderProfile(
        provider_name="ollama",
        supports_native_thinking=False,
        supports_prompt_caching=False,
        supports_native_tools=True,
        context_window_limit=32000,
        output_token_ceiling=4096,
    ),
}


def get_provider_profile(provider: str) -> ProviderProfile:
    """Retrieve capabilities profile for a provider with safe defaults."""
    clean_name = provider.strip().lower()
    return _PROVIDER_PROFILES.get(clean_name, ProviderProfile(provider_name=clean_name))
