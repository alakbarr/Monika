# ==============================================================================
# File: agent/trajectory_compressor.py
# ==============================================================================

"""
Trajectory Compressor & Context Compaction Engine for Monika.
Implements dual-mode trajectory compression with Semantic LLM summarization as default,
deterministic mechanical fallback, and strict preservation of mechanical invariants
and tool-call pairing integrity.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.three_part_context_compressor import ThreePartContextCompressor

logger = logging.getLogger("TradingAgent.Agent.TrajectoryCompressor")

INVARIANT_PATTERN = re.compile(r"<mechanical-invariants>.*?</mechanical-invariants>", re.DOTALL | re.IGNORECASE)


class TrajectoryCompressor:
    """
    Unified Trajectory Compression Engine.
    
    Modes:
      - 'semantic' (Default): Uses an auxiliary lightweight LLM to summarize middle conversation turns
        while preserving technical precision, trading thesis, and mechanical invariants.
      - 'fast': Purely mechanical/deterministic truncation of historical tool outputs without LLM overhead.
    """

    def __init__(
        self,
        default_mode: str = "semantic",
        threshold_tokens: int = 32000,
        protect_first_n: int = 2,
        protect_last_n: int = 8,
        max_tool_chars: int = 600,
    ):
        self.default_mode = default_mode
        self.threshold_tokens = threshold_tokens
        self.protect_first_n = protect_first_n
        self.protect_last_n = protect_last_n
        self.max_tool_chars = max_tool_chars
        self._inner_compressor = ThreePartContextCompressor(
            protect_first_n=protect_first_n,
            protect_last_n=protect_last_n,
            max_tool_output_chars=max_tool_chars,
            compression_threshold_tokens=threshold_tokens,
        )

    def extract_mechanical_invariants(self, messages: List[Dict[str, Any]]) -> List[str]:
        """Extracts any protected <mechanical-invariants> tags found across messages."""
        invariants: List[str] = []
        for m in messages:
            content = m.get("content")
            if isinstance(content, str):
                matches = INVARIANT_PATTERN.findall(content)
                invariants.extend(matches)
        return list(dict.fromkeys(invariants))  # Preserve order, unique

    def compress(
        self,
        messages: List[Dict[str, Any]],
        mode: Optional[str] = None,
        summarizer_fn: Optional[Callable[[str], str]] = None,
        force: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Compresses conversation trajectory.
        
        Args:
            messages: Full list of message dictionaries.
            mode: 'semantic' (default) or 'fast'.
            summarizer_fn: Callable auxiliary summarizer for semantic mode.
            force: Force compaction regardless of token threshold.
            
        Returns:
            Compacted list of messages conforming to provider schema requirements.
        """
        selected_mode = (mode or self.default_mode).lower().strip()
        extracted_invariants = self.extract_mechanical_invariants(messages)

        if selected_mode == "semantic" and summarizer_fn is not None:
            # Semantic Mode: Wrap summarizer to ensure mechanical invariants are never lost
            def protected_summarizer(corpus: str) -> str:
                base_summary = summarizer_fn(corpus)
                if extracted_invariants:
                    inv_block = "\n".join(extracted_invariants)
                    if "<mechanical-invariants>" not in base_summary:
                        base_summary += f"\n\n[Preserved Mechanical Invariants]:\n{inv_block}"
                return base_summary

            compacted = self._inner_compressor.compact(
                messages=messages,
                summarizer_fn=protected_summarizer,
                force=force,
            )
        else:
            # Fast Mode: Deterministic pruning only
            compacted = self._inner_compressor.compact(
                messages=messages,
                summarizer_fn=None,
                force=force,
            )

        # Enforce Tool Call / Tool Result Pairing Integrity
        return self._sanitize_tool_pairing(compacted)

    def _sanitize_tool_pairing(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Ensures that assistant messages with tool_calls have corresponding tool response messages,
        and that orphaned tool responses without prior assistant tool_calls are removed.
        Prevents API 400 Bad Request errors from Anthropic and OpenAI.
        """
        sanitized: List[Dict[str, Any]] = []
        registered_call_ids = set()

        for msg in messages:
            msg_copy = dict(msg)
            role = msg_copy.get("role")

            if role == "assistant" and msg_copy.get("tool_calls"):
                for tc in msg_copy["tool_calls"]:
                    if isinstance(tc, dict) and "id" in tc:
                        registered_call_ids.add(tc["id"])
                sanitized.append(msg_copy)
            elif role == "tool" or msg_copy.get("tool_call_id"):
                tc_id = msg_copy.get("tool_call_id")
                # If tool response references a known call, or no id check possible, keep it
                if not tc_id or tc_id in registered_call_ids:
                    sanitized.append(msg_copy)
                else:
                    logger.debug(f"[TrajectoryCompressor] Evicted orphaned tool response: {tc_id}")
            else:
                sanitized.append(msg_copy)

        return sanitized
