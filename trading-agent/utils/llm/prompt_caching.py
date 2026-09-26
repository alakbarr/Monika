# ==============================================================================
# File: utils/llm/prompt_caching.py
# ==============================================================================

import logging
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("TradingAgent.PromptCaching")


class PromptCacheTracker:
    """Tracks prompt cache hit/miss/creation statistics across LLM turns."""

    def __init__(self):
        self.total_cache_read_tokens: int = 0
        self.total_cache_creation_tokens: int = 0
        self.total_input_tokens: int = 0
        self.total_turns: int = 0

    def record_turn(
        self,
        input_tokens: int,
        cached_tokens: int,
        cache_creation_tokens: int = 0,
        model_name: str = "",
    ):
        self.total_turns += 1
        self.total_input_tokens += input_tokens
        self.total_cache_read_tokens += cached_tokens
        self.total_cache_creation_tokens += cache_creation_tokens

        hit_rate = self.get_hit_rate()
        logger.debug(
            f"[PromptCacheTracker] Turn {self.total_turns} ({model_name}): "
            f"cached={cached_tokens}, created={cache_creation_tokens}, input={input_tokens}, "
            f"cumulative_hit_rate={hit_rate:.1%}"
        )

    def get_hit_rate(self) -> float:
        total_eligible = self.total_input_tokens + self.total_cache_read_tokens
        if total_eligible <= 0:
            return 0.0
        return self.total_cache_read_tokens / total_eligible

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_turns": self.total_turns,
            "total_input_tokens": self.total_input_tokens,
            "total_cache_read_tokens": self.total_cache_read_tokens,
            "total_cache_creation_tokens": self.total_cache_creation_tokens,
            "cache_hit_rate": round(self.get_hit_rate(), 4),
        }


# Global cache tracker singleton
global_cache_tracker = PromptCacheTracker()


class PromptCacheManager:
    """Applies provider-aware prompt caching strategies and breakpoints.
    
    Adheres to strict prompt prefix invariance and provider ephemeral caching standards.
    """

    @staticmethod
    def apply_anthropic_cache(
        system_prompt: Union[str, List[Union[Dict[str, Any], str]]],
        tools: Optional[List[Dict[str, Any]]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        ttl: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """Place up to 4 cache_control breakpoints on stable prefix boundaries for Anthropic.
        
        Breakpoint 1: End of stable system prompt (with 1h TTL)
        Breakpoint 2: End of tool definitions (canonically sorted)
        Breakpoint 3/4: End of initial conversation turns
        """
        cache_marker: Dict[str, Any] = {"type": "ephemeral"}
        if ttl:
            cache_marker["ttl"] = ttl

        # 1. System blocks with ephemeral cache control
        system_blocks: List[Dict[str, Any]] = []
        if isinstance(system_prompt, str) and system_prompt:
            system_blocks.append({
                "type": "text",
                "text": system_prompt,
                "cache_control": dict(cache_marker),
            })
        elif isinstance(system_prompt, list):
            for item in system_prompt:
                if isinstance(item, dict):
                    system_blocks.append(dict(item))
                elif isinstance(item, str):
                    system_blocks.append({"type": "text", "text": item})
            if system_blocks:
                system_blocks[-1]["cache_control"] = dict(cache_marker)

        # 2. Canonical alphabetical sorting & tool definitions cache breakpoint
        cached_tools = None
        if tools:
            sorted_tools = sorted(
                tools,
                key=lambda t: str(t.get("name") or (t.get("function", {}).get("name") if isinstance(t.get("function"), dict) else "") or "")
            )
            cached_tools = []
            for i, tool in enumerate(sorted_tools):
                t_copy = dict(tool)
                if i == len(sorted_tools) - 1:
                    t_copy["cache_control"] = dict(cache_marker)
                cached_tools.append(t_copy)

        # 3. Messages copy
        cached_messages = list(messages or [])
        return system_blocks, cached_tools, cached_messages
    @staticmethod
    def find_stable_prefix(text: str, split_marker: str = "\n---\n") -> Tuple[str, str]:
        """
        Splits text into (stable_scaffold, volatile_payload) based on split_marker.
        If marker not found, searches for last major section boundary.
        """
        if not text:
            return "", ""
        if split_marker in text:
            parts = text.split(split_marker, 1)
            return parts[0].strip(), parts[1].strip()

        # Fallback: check for double newline after 500 chars
        if len(text) > 800 and "\n\n" in text[400:]:
            idx = text.find("\n\n", 400)
            return text[:idx].strip(), text[idx:].strip()

        return text, ""

    @staticmethod
    def apply_4breakpoint_cache(
        system_prompt: Union[str, List[Union[Dict[str, Any], str]]],
        tools: Optional[List[Dict[str, Any]]] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        is_subagent: bool = False,
        explicit_ttl: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[List[Dict[str, Any]]], List[Dict[str, Any]]]:
        """
        Monika 4-Breakpoint Prompt Caching Strategy:
        Breakpoint 1: Static system prompt prefix (core rules & identity)
        Breakpoint 2: Full system prompt / environment snapshot / tools boundary
        Breakpoint 3: Penultimate non-system message boundary
        Breakpoint 4: Final user message scaffold boundary

        Subagent Demotion: If is_subagent=True, sets ttl='5m' instead of 1h
        to avoid wasting cache write costs on short-lived worker turns.
        """
        effective_ttl = explicit_ttl or ("5m" if is_subagent else "1h")
        cache_marker: Dict[str, Any] = {"type": "ephemeral", "ttl": effective_ttl}

        # 1. System blocks
        system_blocks: List[Dict[str, Any]] = []
        if isinstance(system_prompt, str) and system_prompt:
            prefix, volatile = PromptCacheManager.find_stable_prefix(system_prompt)
            if prefix and volatile:
                system_blocks.append({
                    "type": "text",
                    "text": prefix,
                    "cache_control": dict(cache_marker),  # Breakpoint 1
                })
                system_blocks.append({
                    "type": "text",
                    "text": volatile,
                    "cache_control": dict(cache_marker),  # Breakpoint 2
                })
            else:
                system_blocks.append({
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": dict(cache_marker),  # Breakpoint 1
                })
        elif isinstance(system_prompt, list):
            for item in system_prompt:
                if isinstance(item, dict):
                    system_blocks.append(dict(item))
                elif isinstance(item, str):
                    system_blocks.append({"type": "text", "text": item})
            if system_blocks:
                system_blocks[-1]["cache_control"] = dict(cache_marker)

        # 2. Tools sorted canonically with Breakpoint on last tool if present
        cached_tools = None
        if tools:
            sorted_tools = sorted(
                tools,
                key=lambda t: str(t.get("name") or (t.get("function", {}).get("name") if isinstance(t.get("function"), dict) else "") or "")
            )
            cached_tools = []
            for i, tool in enumerate(sorted_tools):
                t_copy = dict(tool)
                if i == len(sorted_tools) - 1:
                    t_copy["cache_control"] = dict(cache_marker)
                cached_tools.append(t_copy)

        # 3. Messages: add breakpoints on the 2 most recent non-system messages
        cached_messages = list(messages or [])
        non_system_indices = [
            i for i, m in enumerate(cached_messages)
            if isinstance(m, dict) and m.get("role") != "system"
        ]

        if len(non_system_indices) >= 2:
            # Place breakpoint on penultimate and last
            for idx in non_system_indices[-2:]:
                msg = dict(cached_messages[idx])
                content = msg.get("content")
                if isinstance(content, list):
                    content_list = list(content)
                    if content_list and isinstance(content_list[-1], dict):
                        content_list[-1] = dict(content_list[-1])
                        content_list[-1]["cache_control"] = dict(cache_marker)
                        msg["content"] = content_list
                elif isinstance(content, str):
                    msg["content"] = [
                        {"type": "text", "text": content, "cache_control": dict(cache_marker)}
                    ]
                cached_messages[idx] = msg

        return system_blocks, cached_tools, cached_messages

    @staticmethod
    def partition_3tier_prompt(
        identity_soul: str,
        instructions_guidelines: str,
        dynamic_context: str,
    ) -> Tuple[str, str]:
        """Split prompt into Hermetic stable cacheable prefix and volatile suffix."""
        prefix_parts = []
        if identity_soul:
            prefix_parts.append(identity_soul.strip())
        if instructions_guidelines:
            prefix_parts.append(instructions_guidelines.strip())

        cacheable_prefix = "\n\n".join(prefix_parts)
        dynamic_suffix = dynamic_context.strip() if dynamic_context else ""
        return cacheable_prefix, dynamic_suffix

    @staticmethod
    def extract_cache_metrics(response: Any) -> Dict[str, int]:
        """Extract cached_tokens and creation tokens from raw provider response."""
        cached_tokens = 0
        creation_tokens = 0

        # Anthropic response.usage
        usage = getattr(response, "usage", None)
        if usage:
            cached_tokens = getattr(usage, "cache_read_input_tokens", 0) or 0
            creation_tokens = getattr(usage, "cache_creation_input_tokens", 0) or 0

        # Gemini / OpenAI usage metadata
        if not cached_tokens and hasattr(response, "usage_metadata"):
            meta = getattr(response, "usage_metadata", {})
            if isinstance(meta, dict):
                cached_tokens = meta.get("cached_content_token_count", 0)
            elif hasattr(meta, "cached_content_token_count"):
                cached_tokens = getattr(meta, "cached_content_token_count", 0)

        return {
            "cached_tokens": cached_tokens,
            "creation_tokens": creation_tokens,
        }

