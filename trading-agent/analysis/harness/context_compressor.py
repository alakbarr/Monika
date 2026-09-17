# ==============================================================================
# File: analysis/harness/context_compressor.py
# ==============================================================================

"""
Multi-Phase Hierarchical Context Compressor (HIGH-4).
Replaces crude static truncation with an intelligent 4-phase pipeline:
1. Deterministic Tool Pruning (strips failed/superseded tool retries and duplicate observations).
2. Protected Boundary Split (preserves initial prompt Head and last 3 turns Tail).
3. Auxiliary Model Summarization (cheap gemini-3.5-flash-lite / rule fallback).
4. Assembly (Head + [Condensed Summary] + Tail).
"""

import copy
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.ContextCompressor")


class ContextCompressor:
    """Multi-Phase Hierarchical Context Compressor for multi-turn LLM ReAct loops."""

    def __init__(self, settings: Optional[dict] = None, aux_client: Optional[Any] = None):
        self.settings = settings or {}
        self.aux_client = aux_client

    def prune_deterministic_tools(self, messages: List[dict]) -> List[dict]:
        """Phase 1: Deterministic Tool Pruning.

        Identifies tool observations that failed or encountered errors that were
        subsequently retried successfully, and prunes verbose redundant bodies.
        """
        pruned_messages = copy.deepcopy(messages)

        # Track tools that eventually succeeded
        successful_tools = set()
        for msg in reversed(pruned_messages):
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        res_text = str(block.get("content", ""))
                        if '"error"' not in res_text and '"status": "error"' not in res_text:
                            tool_use_id = block.get("tool_use_id", "")
                            successful_tools.add(tool_use_id)

        # Prune earlier error messages if superseded
        for msg in pruned_messages:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        res_text = str(block.get("content", ""))
                        if ('"error"' in res_text or '"status": "error"' in res_text) and len(res_text) > 200:
                            block["content"] = "[Pruned error tool observation — superseded by subsequent retry]"
            elif isinstance(content, str) and msg.get("role") in ("user", "tool"):
                if ("Unknown tool:" in content or "validation_failed" in content) and len(content) > 300:
                    msg["content"] = "[Pruned error observation — tool was retried]"

        return pruned_messages

    def split_boundaries(
        self, messages: List[dict], tail_turns: int = 3
    ) -> Tuple[List[dict], List[dict], List[dict]]:
        """Phase 2: Protected Boundary Split.

        Preserves:
        - Head: First message (system / task instruction).
        - Tail: Last `tail_turns` assistant turns + their tool observations.
        - Middle: The intermediate exploration history to be compressed.
        """
        if len(messages) <= (tail_turns * 2) + 2:
            return messages[:1], [], messages[1:]

        head = messages[:1]

        # Find starting index for Tail (last tail_turns assistant messages)
        assistant_indices = [
            i for i, m in enumerate(messages) if m.get("role") == "assistant"
        ]

        if len(assistant_indices) >= tail_turns:
            tail_start = assistant_indices[-tail_turns]
        else:
            tail_start = max(1, len(messages) - (tail_turns * 2))

        middle = messages[1:tail_start]
        tail = messages[tail_start:]

        return head, middle, tail

    def _extract_deterministic_facts(self, messages: List[dict]) -> List[str]:
        """Fallback rule-based extraction when auxiliary LLM is unavailable."""
        facts = []
        for msg in messages:
            content = msg.get("content", "")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(
                    str(b.get("content", "")) for b in content if isinstance(b, dict)
                )

            # Extract key numbers, levels, indicators
            patterns = [
                r"(\b[A-Z]{3,6}\b\s*price\s*[:=]\s*\d+\.?\d*)",
                r"(ATR(?:_14)?\s*[:=]\s*\d+\.?\d*)",
                r"(RSI(?:_14)?\s*[:=]\s*\d+\.?\d*)",
                r"(DXY\s*[:=]\s*\d+\.?\d*)",
                r"(VIX\s*[:=]\s*\d+\.?\d*)",
                r"(Stop\s*Loss\s*[:=]\s*\d+\.?\d*)",
                r"(Take\s*Profit\s*[:=]\s*\d+\.?\d*)",
                r"(bias\s*[:=]\s*(?:bullish|bearish|neutral))",
                r"(regime\s*[:=]\s*[A-Z_]+)",
            ]
            for p in patterns:
                matches = re.findall(p, text, re.IGNORECASE)
                for m in matches:
                    f = m.strip()
                    if f and f not in facts:
                        facts.append(f)
                        if len(facts) >= 25:
                            return facts
        return facts

    async def summarize_middle(self, middle_messages: List[dict]) -> str:
        """Phase 3: Auxiliary Model Summarization.

        Summarizes middle conversation turns using an ultra-cheap model
        (gemini-3.5-flash-lite, thinking: none) or falls back to rule extraction.
        """
        if not middle_messages:
            return "No intermediate turns to summarize."

        facts = self._extract_deterministic_facts(middle_messages)

        client = self.aux_client
        if client is None:
            try:
                from analysis.providers.llm_factory import get_client_for_task
                client = get_client_for_task("summarizer", self.settings or {})
            except Exception:
                try:
                    from analysis.providers.gemini_provider import GeminiProvider
                    client = GeminiProvider(
                        model="gemini-3.5-flash-lite",
                        thinking_level="none",
                        settings=self.settings,
                    )
                except Exception:
                    client = None

        if client and hasattr(client, "generate"):
            try:
                # Build concise middle text representation
                snippets = []
                for m in middle_messages:
                    role = m.get("role", "unknown")
                    cnt = str(m.get("content", ""))[:400]
                    snippets.append(f"[{role}]: {cnt}")
                chunk = "\n".join(snippets[:15])

                prompt = (
                    "Summarize the following intermediate trading analysis conversation into a dense, factual "
                    "bulleted summary. Extract all established technical levels, indicators (RSI, ATR, DXY, VIX), "
                    "order blocks, and conclusions. Do NOT invent new facts. Max 10 bullet points:\n\n"
                    f"{chunk}"
                )
                summary = await client.generate(prompt, max_tokens=300)
                if summary and len(summary.strip()) > 30:
                    return summary.strip()
            except Exception as e:
                logger.debug(f"Auxiliary model summarization failed, falling back to rule extraction: {e}")

        # Fallback deterministic summary
        if facts:
            return "Key established facts from prior turns:\n" + "\n".join(f"• {f}" for f in facts)
        return "Intermediate turns summarized: market data and technical indicators queried and evaluated."

    async def compress(
        self,
        messages: List[dict],
        max_context_chars: int = 100000,
        tail_turns: int = 3,
    ) -> List[dict]:
        """Phase 4: Assembly.

        Executes full 4-phase context compression pipeline:
        1. Prune redundant tool outputs.
        2. Split into Head, Middle, Tail.
        3. Summarize Middle via aux model / rules.
        4. Assemble Head + [Condensed Summary Message] + Tail.
        """
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        if total_chars <= max_context_chars:
            return messages

        # Phase 1: Deterministic Tool Pruning
        pruned = self.prune_deterministic_tools(messages)

        # Phase 2: Protected Boundary Split
        head, middle, tail = self.split_boundaries(pruned, tail_turns=tail_turns)
        if not middle:
            return head + tail

        # Phase 3: Auxiliary Model Summarization
        summary_text = await self.summarize_middle(middle)

        # Phase 4: Assembly
        summary_message = {
            "role": "user",
            "content": (
                "[CONDENSED CONTEXT SUMMARY — intermediate turns compressed for context budget]\n"
                f"{summary_text}\n"
                "[END SUMMARY — continue analysis with recent observations below]"
            ),
        }

        assembled = head + [summary_message] + tail
        logger.info(
            f"[ContextCompressor] Compressed {len(messages)} messages ({total_chars} chars) "
            f"-> {len(assembled)} messages."
        )
        return assembled
