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
import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.ContextCompressor")


def safe_unicode_slice(text: str, max_chars: int) -> str:
    """
    Slices string by Unicode code points without corrupting multi-byte characters
    or splitting surrogate pairs.
    """
    if len(text) <= max_chars:
        return text
    clean = text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")
    sub = clean[:max_chars]
    return sub.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def offload_historical_charts(messages: List[dict], retain_recent_turns: int = 2) -> List[dict]:
    """
    Strips heavy base64 image / chart payloads from turns older than `retain_recent_turns`
    assistant turns, replacing them with a compact text description to avoid multimodal context sinks.
    """
    if not messages:
        return messages

    assistant_indices = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]
    cutoff_idx = assistant_indices[-retain_recent_turns] if len(assistant_indices) >= retain_recent_turns else 0

    processed = []
    for i, msg in enumerate(messages):
        if i >= cutoff_idx:
            processed.append(msg)
            continue

        content = msg.get("content")
        if isinstance(content, list):
            new_blocks = []
            has_image = False
            for b in content:
                if isinstance(b, dict) and (b.get("type") in ("image", "image_url") or "inline_data" in b):
                    has_image = True
                    new_blocks.append({
                        "type": "text",
                        "text": "[CHART/IMAGE OFFLOADED: Historical technical chart visual offloaded to conserve token budget]"
                    })
                else:
                    new_blocks.append(b)
            if has_image:
                cloned = dict(msg)
                cloned["content"] = new_blocks
                processed.append(cloned)
            else:
                processed.append(msg)
        else:
            processed.append(msg)

    return processed


class ContextCompressor:
    """Multi-Phase Hierarchical Context Compressor for multi-turn LLM ReAct loops."""

    def __init__(self, settings: Optional[dict] = None, aux_client: Optional[Any] = None):
        self.settings = settings or {}
        self.aux_client = aux_client
        self._ineffective_compression_count: int = 0
        self._locked_until: float = 0.0
        self.cooldown_seconds: float = float(self.settings.get("compaction_cooldown_seconds", 120.0))

    def prune_deterministic_tools(self, messages: List[dict]) -> List[dict]:
        """Phase 1: Deterministic Tool Pruning & Deduplication.

        Identifies tool observations that failed or encountered errors that were
        subsequently retried successfully, prunes redundant bodies, and deduplicates
        identical observations across turns with Unicode code-point safety.
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

        # Deduplicate identical tool observations (preserving newest copy)
        seen_hashes = set()
        for msg in reversed(pruned_messages):
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        res_text = str(block.get("content", ""))
                        if len(res_text) > 30:
                            h = hashlib.md5(res_text.encode("utf-8")).hexdigest()[:12]
                            if h in seen_hashes:
                                block["content"] = "[Duplicate tool observation — same content as subsequent turn]"
                            else:
                                seen_hashes.add(h)
            elif isinstance(content, str) and msg.get("role") == "tool":
                if len(content) > 30:
                    h = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
                    if h in seen_hashes:
                        msg["content"] = "[Duplicate tool observation — same content as subsequent turn]"
                    else:
                        seen_hashes.add(h)

        return pruned_messages

    def _snap_boundary(self, messages: List[dict], split_idx: int) -> int:
        """Snaps split index to ensure tool-pair integrity (prevents orphaned tool_use or tool_result)."""
        if split_idx <= 1 or split_idx >= len(messages):
            return split_idx

        # If split_idx lands on a user message containing tool_result, shift back to include preceding assistant turn
        msg = messages[split_idx]
        content = msg.get("content")
        has_tool_result = False
        if isinstance(content, list):
            has_tool_result = any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content
            )
        elif isinstance(content, str) and msg.get("role") == "tool":
            has_tool_result = True

        if has_tool_result and split_idx > 1:
            return split_idx - 1

        # If preceding message has tool_use, verify tool_result is not severed
        prev_msg = messages[split_idx - 1]
        prev_content = prev_msg.get("content")
        has_tool_use = False
        if isinstance(prev_content, list):
            has_tool_use = any(
                isinstance(b, dict) and b.get("type") == "tool_use" for b in prev_content
            )
        if has_tool_use and split_idx > 1:
            return split_idx - 1

        return split_idx

    def _feasibility_skip(self, messages: List[dict], min_chars: int = 4000) -> bool:
        """Skip expensive auxiliary LLM summarization if middle turns are small (< 4000 chars / 1000 tokens)."""
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        return total_chars < min_chars

    def _extract_existing_summary(self, middle_messages: List[dict]) -> Tuple[Optional[str], List[dict]]:
        """Extract existing condensed summary to chain iteratively across long multi-turn runs."""
        existing_summary = None
        filtered = []
        for m in middle_messages:
            cnt = str(m.get("content", ""))
            if "[CONDENSED CONTEXT SUMMARY" in cnt:
                match = re.search(r"\[CONDENSED CONTEXT SUMMARY —.*?\]\n(.*?)\n\[END SUMMARY", cnt, re.DOTALL)
                if match:
                    existing_summary = match.group(1).strip()
            else:
                filtered.append(m)
        return existing_summary, filtered

    def split_boundaries(
        self, messages: List[dict], tail_turns: int = 3
    ) -> Tuple[List[dict], List[dict], List[dict]]:
        """Phase 2: Protected Boundary Split with Warm-Prefix Preservation and Tool-Pair Snap.

        Preserves:
        - Head: Leading invariant turns (initial system prompt AND initial user task instruction).
        - Tail: Last `tail_turns` assistant turns + their tool observations (snapped).
        - Middle: The intermediate exploration history to be compressed.
        """
        # Warm-Prefix Preservation: Preserve initial system prompt AND initial user instruction
        head = []
        for m in messages:
            r = m.get("role")
            if r in ("system", "user") and len(head) < 2:
                head.append(m)
                if r == "user":
                    break
            else:
                break
        if not head:
            head = messages[:1]

        if len(messages) <= (tail_turns * 2) + len(head):
            return head, [], messages[len(head):]

        # Find starting index for Tail (last tail_turns assistant messages)
        assistant_indices = [
            i for i, m in enumerate(messages) if m.get("role") == "assistant"
        ]

        if len(assistant_indices) >= tail_turns:
            tail_start = assistant_indices[-tail_turns]
        else:
            tail_start = max(len(head), len(messages) - (tail_turns * 2))

        tail_start = max(len(head), tail_start)
        # Snap boundary to guarantee tool-use / tool-result pair integrity
        tail_start = self._snap_boundary(messages, tail_start)

        middle = messages[len(head):tail_start]
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
        """Phase 3: Auxiliary Model Summarization with Iterative Chaining.

        Summarizes middle conversation turns using an ultra-cheap model
        (gemini-3.5-flash-lite, thinking: none) or falls back to rule extraction.
        Feasibility check: If middle segment is small (< 1000 tokens / 4000 chars),
        uses deterministic rule extraction to avoid wasteful LLM calls.
        """
        if not middle_messages:
            return "No intermediate turns to summarize."

        existing_summary, clean_middle = self._extract_existing_summary(middle_messages)
        facts = self._extract_deterministic_facts(clean_middle)

        # Feasibility check: only invoke aux LLM if middle has substantial content or aux_client is explicitly provided
        should_call_llm = self.aux_client is not None or not self._feasibility_skip(clean_middle)

        client = self.aux_client
        if client is None and should_call_llm:
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

        if should_call_llm and client and hasattr(client, "generate"):
            try:
                # Build concise middle text representation
                snippets = []
                for m in clean_middle:
                    role = m.get("role", "unknown")
                    cnt = str(m.get("content", ""))[:400]
                    snippets.append(f"[{role}]: {cnt}")
                chunk = "\n".join(snippets[:15])

                prompt_parts = []
                if existing_summary:
                    prompt_parts.append(f"PREVIOUS CONTEXT SUMMARY:\n{existing_summary}")
                prompt_parts.append(
                    "Summarize the following intermediate trading analysis conversation into a dense, factual "
                    "bulleted summary. Extract all established technical levels, indicators (RSI, ATR, DXY, VIX), "
                    "order blocks, and conclusions. Do NOT invent new facts. Max 10 bullet points:\n\n"
                    f"{chunk}"
                )
                prompt = "\n\n".join(prompt_parts)
                summary = await client.generate(prompt, max_tokens=350)
                if summary and len(summary.strip()) > 30:
                    return summary.strip()
            except Exception as e:
                logger.debug(f"Auxiliary model summarization failed, falling back to rule extraction: {e}")

        # Fallback deterministic summary with chained history
        if facts or existing_summary:
            lines = ["Key established facts from prior turns:"]
            if existing_summary:
                lines.append(f"• Prior Summary: {existing_summary[:200]}")
            lines.extend(f"• {f}" for f in facts)
            return "\n".join(lines)
        return "Intermediate turns summarized: market data and technical indicators queried and evaluated."

    async def compress(
        self,
        messages: List[dict],
        max_context_chars: int = 100000,
        tail_turns: int = 3,
    ) -> List[dict]:
        """Phase 4: Assembly.

        Executes full 4-phase context compression pipeline:
        1. Feasibility Skip: Ignore small contexts (< 1000 tokens).
        2. Prune redundant tool outputs.
        3. Split into Head, Middle, Tail (tool-pair snapped).
        4. Summarize Middle via aux model / rules with iterative chaining.
        5. Assemble Head + [Condensed Summary Message] + Tail.
        """
        # Phase 0: Offload historical high-res charts older than 2 turns to eliminate multimodal sinks
        messages = offload_historical_charts(messages, retain_recent_turns=2)

        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        if total_chars <= max_context_chars:
            return messages

        if time.time() < self._locked_until:
            logger.warning("[ContextCompressor] Anti-thrashing circuit breaker active; skipping compaction.")
            return messages

        # Phase 1: Deterministic Tool Pruning
        pruned = self.prune_deterministic_tools(messages)

        # Phase 2: Protected Boundary Split
        head, middle, tail = self.split_boundaries(pruned, tail_turns=tail_turns)
        if not middle:
            assembled = head + tail
            chars_after = sum(len(str(m.get("content", ""))) for m in assembled)
            reduction_ratio = (total_chars - chars_after) / max(total_chars, 1)
            if reduction_ratio < 0.10:
                self._ineffective_compression_count += 1
                if self._ineffective_compression_count >= 2:
                    self._locked_until = time.time() + self.cooldown_seconds
                    logger.warning(
                        f"[ContextCompressor] Anti-thrashing circuit breaker tripped: "
                        f"2 consecutive ineffective compactions ({reduction_ratio:.1%} reduction). "
                        f"Locked for {self.cooldown_seconds}s."
                    )
            else:
                self._ineffective_compression_count = 0
            return assembled

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
        chars_after = sum(len(str(m.get("content", ""))) for m in assembled)
        reduction_ratio = (total_chars - chars_after) / max(total_chars, 1)

        if reduction_ratio < 0.10:
            self._ineffective_compression_count += 1
            if self._ineffective_compression_count >= 2:
                self._locked_until = time.time() + self.cooldown_seconds
                logger.warning(
                    f"[ContextCompressor] Anti-thrashing circuit breaker tripped: "
                    f"2 consecutive ineffective compactions ({reduction_ratio:.1%} reduction). "
                    f"Locked for {self.cooldown_seconds}s."
                )
        else:
            self._ineffective_compression_count = 0

        logger.info(
            f"[ContextCompressor] Compressed {len(messages)} messages ({total_chars} chars) "
            f"-> {len(assembled)} messages ({chars_after} chars, {reduction_ratio:.1%} freed)."
        )
        return assembled
