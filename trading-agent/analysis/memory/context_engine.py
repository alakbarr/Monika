# ==============================================================================
# File: analysis/memory/context_engine.py
# ==============================================================================

"""
Adaptive Pluggable Context Engine.
Institutional-grade memory and context protection architecture.

Coordinates lifecycle context assembly:
  1. System identity & permanent rules (Layer 0)
  2. Mechanical numeric anchors (MechanicalAnchorIndex)
  3. Dynamic episodic memory & precedent retrieval
  4. Conversational trajectory with automatic compaction
Enforces deterministic token budgeting before dispatching to LLM providers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from analysis.memory.mechanical_anchor_index import MechanicalAnchorIndex
from analysis.providers.trajectory_compressor import TrajectoryCompressor
from utils.llm.prompt_compressor import estimate_tokens

logger = logging.getLogger("TradingAgent.Memory.ContextEngine")

DEFAULT_MAX_CONTEXT_TOKENS = 16000


class ContextEngine:
    """Adaptive lifecycle coordinator for model context compilation."""

    def __init__(
        self,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        compressor: Optional[TrajectoryCompressor] = None,
    ):
        self.max_context_tokens = max_context_tokens
        self.anchor_index = MechanicalAnchorIndex()
        self.compressor = compressor or TrajectoryCompressor()

    def process_incoming_turn(self, user_text: str) -> Dict[str, Any]:
        """Hook called before LLM invocation: extracts numeric facts into anchor index."""
        return self.anchor_index.extract_anchors(user_text)

    def assemble_context(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        episodic_context: Optional[str] = None,
        tool_definitions_schema: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Assembles balanced, token-budgeted messages payload for LLM invocation.
        Applies mechanical anchor injection and trajectory compaction if budget exceeded.
        """
        # 1. Build authoritative system message
        anchors_block = self.anchor_index.render_anchor_block()
        sys_parts = [system_prompt.strip()]
        if anchors_block:
            sys_parts.append(anchors_block)
        if episodic_context and episodic_context.strip():
            sys_parts.append(f"<episodic-memory>\n{episodic_context.strip()}\n</episodic-memory>")

        full_system_text = "\n\n".join(sys_parts)
        system_msg = {"role": "system", "content": full_system_text}

        # 2. Check total token consumption
        sys_tokens = estimate_tokens(full_system_text)
        avail_for_history = max(1000, self.max_context_tokens - sys_tokens - 1000)

        # 3. Estimate history tokens
        raw_history_text = " ".join(str(m.get("content", "")) for m in messages)
        history_tokens = estimate_tokens(raw_history_text)

        if history_tokens > avail_for_history:
            logger.info(
                f"[ContextEngine] History tokens ({history_tokens}) exceeds available budget "
                f"({avail_for_history}). Triggering trajectory compression."
            )
            processed_messages = self.compressor.compress_trajectory(messages)
        else:
            processed_messages = list(messages)

        return [system_msg] + processed_messages

    def clear(self) -> None:
        self.anchor_index.clear()
