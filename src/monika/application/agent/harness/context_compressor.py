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
import inspect
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.ContextCompressor")

# 8-section standardized trading domain summary schema (PR-06)
TRADING_SUMMARY_SECTIONS: List[str] = [
    "market_regime",
    "technical_structure",
    "liquidity_pois",
    "intermarket_sentiment",
    "active_hypotheses",
    "established_levels",
    "risk_constraints",
    "completed_actions_evidence",
]


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


TOOL_PRUNE_MARKER: str = "\n\n[... tool result middle pruned ...]\n\n"


def safe_unicode_tail(text: str, max_chars: int) -> str:
    """
    Slices string tail by Unicode code points without corrupting multi-byte characters
    or splitting surrogate pairs.
    """
    if len(text) <= max_chars:
        return text
    clean = text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="replace")
    sub = clean[-max_chars:]
    return sub.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def prune_tool_result_content(
    text: str,
    threshold_chars: int = 8192,
    head_chars: int = 4096,
    tail_chars: int = 1024,
) -> str:
    """
    Deterministic head/tail code-point-safe pruning for individual oversized tool outputs.
    Preserves setup context at head and conclusion/status at tail while trimming verbose intermediate output.
    """
    if len(text) <= threshold_chars:
        return text
    head = safe_unicode_slice(text, head_chars)
    tail = safe_unicode_tail(text, tail_chars)
    return f"{head}{TOOL_PRUNE_MARKER}{tail}"


def prune_oversized_tool_results(
    messages: List[dict],
    threshold_chars: int = 8192,
    head_chars: int = 4096,
    tail_chars: int = 1024,
) -> List[dict]:
    """
    Scans conversation messages and deterministically prunes tool results that exceed threshold_chars
    without an LLM invocation.
    """
    if not messages:
        return messages

    processed = []
    for msg in messages:
        content = msg.get("content")
        role = msg.get("role")

        if isinstance(content, list):
            new_blocks = []
            modified = False
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    res_text = str(b.get("content", ""))
                    if len(res_text) > threshold_chars:
                        pruned_text = prune_tool_result_content(
                            res_text,
                            threshold_chars=threshold_chars,
                            head_chars=head_chars,
                            tail_chars=tail_chars,
                        )
                        cloned_block = dict(b)
                        cloned_block["content"] = pruned_text
                        new_blocks.append(cloned_block)
                        modified = True
                        continue
                new_blocks.append(b)
            if modified:
                cloned_msg = dict(msg)
                cloned_msg["content"] = new_blocks
                processed.append(cloned_msg)
            else:
                processed.append(msg)
        elif isinstance(content, str) and role in ("tool", "user"):
            if role == "tool" and len(content) > threshold_chars:
                pruned_text = prune_tool_result_content(
                    content,
                    threshold_chars=threshold_chars,
                    head_chars=head_chars,
                    tail_chars=tail_chars,
                )
                cloned_msg = dict(msg)
                cloned_msg["content"] = pruned_text
                processed.append(cloned_msg)
            else:
                processed.append(msg)
        else:
            processed.append(msg)

    return processed


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
                    new_blocks.append(
                        {
                            "type": "text",
                            "text": "[CHART/IMAGE OFFLOADED: Historical technical chart visual offloaded to conserve token budget]",
                        }
                    )
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

    def prune_oversized_tool_results(
        self,
        messages: List[dict],
        threshold_chars: int = 8192,
        head_chars: int = 4096,
        tail_chars: int = 1024,
    ) -> List[dict]:
        """Stage 0: Deterministic model-free pruning of individual oversized tool results."""
        return prune_oversized_tool_results(
            messages,
            threshold_chars=threshold_chars,
            head_chars=head_chars,
            tail_chars=tail_chars,
        )

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

        # Deduplicate identical tool observations (preserving newest copy, stubbing older duplicates)
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

    @classmethod
    def distill_initial_bundle_after_turn_1(cls, messages: List[dict]) -> List[dict]:
        """
        P0 Token Optimization: Prunes the verbose 50k character raw prefetch bundle
        from messages[0] once Turn 1 has completed.
        Retains core anchors, regime, and macro bias while compressing thousands of raw candle rows.
        """
        if not messages or len(messages) < 3:
            return messages

        first_msg = messages[0]
        if first_msg.get("role") != "user":
            return messages

        content = first_msg.get("content")
        if not isinstance(content, str) or "[PRE-FETCHED DATA]" not in content:
            return messages

        if "[PRE-FETCHED DATA DISTILLED]" in content:
            return messages

        # Split before and after [PRE-FETCHED DATA]
        parts = content.split("[PRE-FETCHED DATA]")
        prefix = parts[0]
        bundle_body = parts[1]

        # Extract essential summary lines (regime, bias, ATR, fundamental brief)
        lines = bundle_body.strip().split("\n")
        retained_lines = []
        for line in lines:
            l_lower = line.lower()
            if any(
                k in l_lower
                for k in (
                    "regime",
                    "vix",
                    "dxy",
                    "bias",
                    "fundamental",
                    "atr",
                    "confluence",
                    "economic calendar",
                    "order block",
                    "fvg",
                    "support",
                    "resistance",
                )
            ):
                retained_lines.append(line)
            if len(retained_lines) >= 30:
                break

        distilled_bundle = "\n".join(retained_lines)
        new_content = (
            f"{prefix}\n\n[PRE-FETCHED DATA DISTILLED]\n"
            f"[Turn 1 ingestion complete. Detailed candlestick history & raw indicator tables pruned for token efficiency.]\n"
            f"{distilled_bundle}\n"
            f"[... Remaining raw candle arrays truncated ...]"
        )

        messages_copy = list(messages)
        new_first = dict(first_msg)
        new_first["content"] = new_content
        messages_copy[0] = new_first
        return messages_copy

    @staticmethod
    def is_balanced_tool_boundary(messages: List[dict], split_idx: int) -> bool:
        """
        Verifies whether splitting messages at split_idx keeps all tool-use/tool-result pairs balanced.
        Returns True if no step is severed across the boundary.
        """
        if split_idx <= 0 or split_idx >= len(messages):
            return True

        # Preceding message has open tool_calls/tool_use but next message is not yet included
        prev_msg = messages[split_idx - 1]
        p_calls = prev_msg.get("tool_calls") or []
        p_content = prev_msg.get("content")
        has_tool_use = bool(p_calls)
        if not has_tool_use and isinstance(p_content, list):
            has_tool_use = any(isinstance(b, dict) and b.get("type") in ("tool_use", "tool_call") for b in p_content)

        if has_tool_use:
            return False

        # Current message is a tool result, which means preceding assistant was before the split
        curr_msg = messages[split_idx]
        c_role = curr_msg.get("role")
        c_content = curr_msg.get("content")
        if c_role == "tool":
            return False
        if isinstance(c_content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in c_content
        ):
            return False

        return True

    def _snap_boundary(self, messages: List[dict], split_idx: int) -> int:
        """Snaps split index to ensure tool-pair integrity (prevents orphaned tool_use or tool_result)."""
        if split_idx <= 1 or split_idx >= len(messages):
            return split_idx

        # If split_idx lands on a message containing tool_result or role=="tool",
        # walk back to include the initiating assistant turn
        msg = messages[split_idx]
        content = msg.get("content")
        role = msg.get("role")
        has_tool_result = False
        if role == "tool":
            has_tool_result = True
        elif isinstance(content, list):
            has_tool_result = any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)
        elif isinstance(content, str) and role in ("tool", "user") and "tool_result" in content:
            has_tool_result = True

        if has_tool_result and split_idx > 1:
            curr = split_idx
            while curr > 1:
                prev_msg = messages[curr - 1]
                prev_role = prev_msg.get("role")
                if prev_role == "assistant":
                    res_idx = curr - 1
                    return res_idx if self.is_balanced_tool_boundary(messages, res_idx) else max(1, res_idx - 1)
                elif prev_role in ("tool", "user"):
                    curr -= 1
                else:
                    break
            res_idx = max(1, curr - 1)
            return res_idx if self.is_balanced_tool_boundary(messages, res_idx) else max(1, res_idx - 1)

        # If preceding message has tool_use or tool_calls, shift back to keep pair intact
        prev_msg = messages[split_idx - 1]
        prev_content = prev_msg.get("content")
        has_tool_use = False
        if "tool_calls" in prev_msg and prev_msg["tool_calls"]:
            has_tool_use = True
        elif isinstance(prev_content, list):
            has_tool_use = any(isinstance(b, dict) and b.get("type") in ("tool_use", "tool_call") for b in prev_content)
        if has_tool_use and split_idx > 1:
            res_idx = split_idx - 1
            return res_idx if self.is_balanced_tool_boundary(messages, res_idx) else max(1, res_idx - 1)

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
            if "<compacted-summary>" in cnt:
                match = re.search(r"<compacted-summary>(.*?)</compacted-summary>", cnt, re.DOTALL)
                if match:
                    existing_summary = match.group(1).strip()
                else:
                    filtered.append(m)
            elif "[CONDENSED CONTEXT SUMMARY" in cnt:
                match = re.search(r"\[CONDENSED CONTEXT SUMMARY —.*?\]\n(.*?)\n\[END SUMMARY", cnt, re.DOTALL)
                if match:
                    existing_summary = match.group(1).strip()
                else:
                    filtered.append(m)
            else:
                filtered.append(m)
        return existing_summary, filtered

    def split_boundaries(self, messages: List[dict], tail_turns: int = 3) -> Tuple[List[dict], List[dict], List[dict]]:
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
            return head, [], messages[len(head) :]

        # Find starting index for Tail (last tail_turns assistant messages)
        assistant_indices = [i for i, m in enumerate(messages) if m.get("role") == "assistant"]

        if len(assistant_indices) >= tail_turns:
            tail_start = assistant_indices[-tail_turns]
        else:
            tail_start = max(len(head), len(messages) - (tail_turns * 2))

        tail_start = max(len(head), tail_start)
        # Snap boundary to guarantee tool-use / tool-result pair integrity
        tail_start = self._snap_boundary(messages, tail_start)

        middle = messages[len(head) : tail_start]
        tail = messages[tail_start:]

        return head, middle, tail

    def _extract_structured_trading_sections(self, messages: List[dict]) -> Dict[str, List[str]]:
        """Extract facts classified into 8 standardized trading domain sections."""
        categorized: Dict[str, List[str]] = {sec: [] for sec in TRADING_SUMMARY_SECTIONS}
        seen: set = set()

        for msg in messages:
            content = msg.get("content", "")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(str(b.get("content", "")) for b in content if isinstance(b, dict))

            # Rule patterns mapped to sections
            section_patterns = [
                # 1. Market Regime
                ("market_regime", r"(DXY\s*[:=]\s*\d+\.?\d*)"),
                ("market_regime", r"(VIX\s*[:=]\s*\d+\.?\d*)"),
                ("market_regime", r"(regime\s*[:=]\s*[A-Z_]+)"),
                ("market_regime", r"(macro\s*[:=]\s*[^,\n\.]+)"),
                # 2. Technical Structure
                ("technical_structure", r"(ATR(?:_14)?\s*[:=]\s*\d+\.?\d*)"),
                ("technical_structure", r"(RSI(?:_14)?\s*[:=]\s*\d+\.?\d*)"),
                ("technical_structure", r"(BOS\s*[:=]\s*[^,\n\.]+)"),
                ("technical_structure", r"(ChoCH\s*[:=]\s*[^,\n\.]+)"),
                ("technical_structure", r"(trend\s*[:=]\s*(?:bullish|bearish|neutral|ranging))"),
                # 3. Liquidity POIs
                ("liquidity_pois", r"((?:order\s*block|OB)\s*[:=]\s*[^,\n\.]+)"),
                ("liquidity_pois", r"((?:FVG|fair\s*value\s*gap)\s*[:=]\s*[^,\n\.]+)"),
                ("liquidity_pois", r"((?:liquidity|sweep)\s*[:=]\s*[^,\n\.]+)"),
                ("liquidity_pois", r"(Asian\s*(?:range|high|low)\s*[:=]\s*[^,\n\.]+)"),
                # 4. Intermarket Sentiment
                ("intermarket_sentiment", r"((?:yield|10Y|treasury)\s*[:=]\s*[^,\n\.]+)"),
                ("intermarket_sentiment", r"(COT\s*[:=]\s*[^,\n\.]+)"),
                ("intermarket_sentiment", r"(sentiment\s*[:=]\s*[^,\n\.]+)"),
                # 5. Active Hypotheses
                ("active_hypotheses", r"(bias\s*[:=]\s*(?:bullish|bearish|neutral))"),
                ("active_hypotheses", r"(confluence(?:\s*score)?\s*[:=]\s*[^,\n\.]+)"),
                ("active_hypotheses", r"(thesis\s*[:=]\s*[^,\n\.]+)"),
                # 6. Established Levels
                ("established_levels", r"(\b[A-Z]{3,6}\b\s*price\s*[:=]\s*\d+\.?\d*)"),
                ("established_levels", r"(Stop\s*Loss\s*[:=]\s*\d+\.?\d*)"),
                ("established_levels", r"(Take\s*Profit\s*[:=]\s*\d+\.?\d*)"),
                ("established_levels", r"(invalidation\s*[:=]\s*[^,\n\.]+)"),
                ("established_levels", r"(entry\s*[:=]\s*\d+\.?\d*)"),
                # 7. Risk Constraints
                ("risk_constraints", r"((?:lot\s*size|lots)\s*[:=]\s*\d+\.?\d*)"),
                ("risk_constraints", r"(R:R\s*[:=]\s*\d+\.?\d*)"),
                ("risk_constraints", r"(ADR\s*[:=]\s*[^,\n\.]+)"),
                ("risk_constraints", r"(max\s*risk\s*[:=]\s*[^,\n\.]+)"),
                # 8. Completed Actions Evidence
                ("completed_actions_evidence", r"((?:action|verified|tool)\s*[:=]\s*[^,\n\.]+)"),
            ]

            for sec, pat in section_patterns:
                matches = re.findall(pat, text, re.IGNORECASE)
                for m in matches:
                    f = m.strip()
                    if f and f.lower() not in seen:
                        seen.add(f.lower())
                        categorized[sec].append(f)

        return categorized

    def _extract_deterministic_facts(self, messages: List[dict]) -> List[str]:
        """Fallback rule-based extraction when auxiliary LLM is unavailable."""
        facts = []
        for msg in messages:
            content = msg.get("content", "")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = " ".join(str(b.get("content", "")) for b in content if isinstance(b, dict))

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

    def _extract_read_files(self, messages: List[dict]) -> List[str]:
        """Extract files read from tool arguments or text."""
        read_set = set()
        for m in messages:
            content = m.get("content", "")
            tcs = m.get("tool_calls") or []
            for tc in tcs:
                fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", None)
                fn_name = fn.get("name", "") if isinstance(fn, dict) else getattr(fn, "name", "")
                if "read" in fn_name.lower() or "view" in fn_name.lower():
                    args = fn.get("arguments", "{}") if isinstance(fn, dict) else getattr(fn, "arguments", "{}")
                    try:
                        parsed = json.loads(args) if isinstance(args, str) else args
                        p = parsed.get("Path") or parsed.get("path") or parsed.get("file_path")
                        if p:
                            read_set.add(str(p))
                    except Exception:
                        pass
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        nm = str(b.get("name", "")).lower()
                        if "read" in nm or "view" in nm:
                            inp = b.get("input", {})
                            if isinstance(inp, dict):
                                p = inp.get("Path") or inp.get("path") or inp.get("file_path")
                                if p:
                                    read_set.add(str(p))
            text_str = str(content)
            for m_path in re.findall(
                r"(?:read|opened|reading|viewed)\s+[`'\"]?([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]{1,6})[`'\"]?",
                text_str,
                re.IGNORECASE,
            ):
                read_set.add(m_path.strip())
        return sorted(read_set)

    def _extract_modified_files(self, messages: List[dict]) -> List[str]:
        """Extract files modified or written from tool arguments or text."""
        mod_set = set()
        for m in messages:
            content = m.get("content", "")
            tcs = m.get("tool_calls") or []
            for tc in tcs:
                fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", None)
                fn_name = fn.get("name", "") if isinstance(fn, dict) else getattr(fn, "name", "")
                if any(k in fn_name.lower() for k in ("edit", "write", "patch", "modify")):
                    args = fn.get("arguments", "{}") if isinstance(fn, dict) else getattr(fn, "arguments", "{}")
                    try:
                        parsed = json.loads(args) if isinstance(args, str) else args
                        p = parsed.get("Path") or parsed.get("path") or parsed.get("file_path")
                        if p:
                            mod_set.add(str(p))
                    except Exception:
                        pass
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        nm = str(b.get("name", "")).lower()
                        if any(k in nm for k in ("edit", "write", "patch", "modify")):
                            inp = b.get("input", {})
                            if isinstance(inp, dict):
                                p = inp.get("Path") or inp.get("path") or inp.get("file_path")
                                if p:
                                    mod_set.add(str(p))
            text_str = str(content)
            for m_path in re.findall(
                r"(?:edited|modified|written|patched)\s+[`'\"]?([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]{1,6})[`'\"]?",
                text_str,
                re.IGNORECASE,
            ):
                mod_set.add(m_path.strip())
        return sorted(mod_set)

    async def summarize_middle(self, middle_messages: List[dict]) -> str:
        """Phase 3: Auxiliary Model Summarization with Iterative Chaining.

        Summarizes middle conversation turns into the 8-section structured schema
        using an ultra-cheap model (gemini-3.5-flash-lite, thinking: none)
        or falls back to rule extraction structured into the 8 trading sections.
        """
        if not middle_messages:
            return "No intermediate turns to summarize."

        existing_summary, clean_middle = self._extract_existing_summary(middle_messages)
        facts = self._extract_deterministic_facts(clean_middle)
        categorized = self._extract_structured_trading_sections(clean_middle)

        read_files = self._extract_read_files(clean_middle)
        modified_files = self._extract_modified_files(clean_middle)
        established_levels = categorized.get("established_levels", [])

        # Feasibility check: only invoke aux LLM if middle has substantial content or aux_client is explicitly provided
        should_call_llm = self.aux_client is not None or not self._feasibility_skip(clean_middle)

        client = self.aux_client
        if client is None and should_call_llm:
            try:
                from monika.infrastructure.providers.llm_factory import get_client_for_task

                client = get_client_for_task("summarizer", self.settings or {})
            except Exception:
                try:
                    from monika.infrastructure.providers.llm_factory import get_client_for_task

                    client = get_client_for_task("context_compaction", self.settings or {})
                except Exception:
                    client = None

        if should_call_llm and client and hasattr(client, "generate"):
            try:
                # Build concise middle text representation (up to 2,000 chars per message, up to 40 messages)
                snippets = []
                for m in clean_middle:
                    role = m.get("role", "unknown")
                    cnt = str(m.get("content", ""))[:2000]
                    snippets.append(f"[{role}]: {cnt}")
                chunk = "\n".join(snippets[:40])

                prompt_parts = []
                if existing_summary:
                    prompt_parts.append(f"PREVIOUS CONTEXT SUMMARY:\n{existing_summary}")
                prompt_parts.append(
                    "You are an expert quantitative trading context compactor. Summarize the following intermediate "
                    "trading analysis conversation into the 8 standardized trading sections: <market_regime>, "
                    "<technical_structure>, <liquidity_pois>, <intermarket_sentiment>, <active_hypotheses>, "
                    "<established_levels>, <risk_constraints>, <completed_actions_evidence>.\n"
                    "Enclose the output within <compacted-summary>...</compacted-summary>:\n\n"
                    f"{chunk}"
                )
                prompt = "\n\n".join(prompt_parts)
                summary = await client.generate(prompt, max_tokens=450)
                if summary and len(summary.strip()) > 30:
                    sum_clean = summary.strip()
                    if "<compacted-summary>" not in sum_clean:
                        sum_clean = f"<compacted-summary>\n{sum_clean}\n</compacted-summary>"

                    # Append deterministic meta-blocks if not already present
                    extra_blocks = []
                    if read_files and "<read-files>" not in sum_clean:
                        extra_blocks.append(
                            "<read-files>\n" + "\n".join(f"- {f}" for f in read_files) + "\n</read-files>"
                        )
                    if modified_files and "<modified-files>" not in sum_clean:
                        extra_blocks.append(
                            "<modified-files>\n" + "\n".join(f"- {f}" for f in modified_files) + "\n</modified-files>"
                        )
                    if established_levels and "<established_levels>" not in sum_clean:
                        extra_blocks.append(
                            "<established_levels>\n"
                            + "\n".join(f"- {lvl}" for lvl in established_levels)
                            + "\n</established_levels>"
                        )
                    if extra_blocks:
                        sum_clean = f"{sum_clean}\n" + "\n".join(extra_blocks)

                    return sum_clean
            except Exception as e:
                logger.debug(f"Auxiliary model summarization failed, falling back to rule extraction: {e}")

        # Fallback deterministic summary with 8-section structured format + read/modified files
        lines = [
            "Key established facts from prior turns:",
            "<compacted-summary>",
        ]
        if existing_summary:
            lines.append(f"  • Prior Summary: {existing_summary[:200]}")
        for sec in TRADING_SUMMARY_SECTIONS:
            items = categorized.get(sec, [])
            if items:
                lines.append(f"  <{sec}>")
                for item in items:
                    lines.append(f"    • {item}")
                lines.append(f"  </{sec}>")
            elif sec == "established_levels" and established_levels:
                lines.append(f"  <established_levels>")
                for lvl in established_levels:
                    lines.append(f"    • {lvl}")
                lines.append(f"  </established_levels>")

        # If any unclassified flat facts remain, include them
        classified_items = {item for sublist in categorized.values() for item in sublist}
        unclassified = [f for f in facts if f not in classified_items]
        if unclassified:
            lines.extend(f"  • {f}" for f in unclassified)
        lines.append("</compacted-summary>")

        if read_files:
            lines.append("<read-files>\n" + "\n".join(f"- {f}" for f in read_files) + "\n</read-files>")
        if modified_files:
            lines.append("<modified-files>\n" + "\n".join(f"- {f}" for f in modified_files) + "\n</modified-files>")

        return "\n".join(lines)

    async def summarize_with_replay_prefix(
        self,
        head: List[dict],
        middle: List[dict],
        client: Optional[Any] = None,
    ) -> str:
        """
        Phase 3 (Optimized): Replay-Prefix KV-Cache Preserving Summarization.
        Structures compaction as an append-only extension of the active conversation prefix (Head + Middle),
        achieving maximum KV-cache hit rate on primary models.
        Falls back cleanly to summarize_middle if client does not support message replay or fails.
        """
        if not client:
            return await self.summarize_middle(middle)

        from collections.abc import Callable

        generate_fn: Optional[Callable[..., Any]] = getattr(client, "generate_from_messages", None) or getattr(
            client, "run_agent_from_messages", None
        )
        if not callable(generate_fn):
            return await self.summarize_middle(middle)

        _existing_summary, clean_middle = self._extract_existing_summary(middle)
        read_files = self._extract_read_files(clean_middle)
        modified_files = self._extract_modified_files(clean_middle)
        categorized = self._extract_structured_trading_sections(clean_middle)
        established_levels = categorized.get("established_levels", [])

        compaction_directive = (
            "You are an expert quantitative trading context compactor. Condense the conversation ABOVE into "
            "the 8 standardized trading sections: <market_regime>, <technical_structure>, <liquidity_pois>, "
            "<intermarket_sentiment>, <active_hypotheses>, <established_levels>, <risk_constraints>, "
            "<completed_actions_evidence>.\n"
            "Enclose the output within <compacted-summary>...</compacted-summary>."
        )

        replay_messages = list(head) + list(clean_middle) + [{"role": "user", "content": compaction_directive}]
        try:
            resp = await generate_fn(messages=replay_messages, max_tokens=450)
            summary_text = getattr(resp, "content", str(resp))
            if isinstance(summary_text, list):
                summary_text = " ".join(
                    str(b.get("text", "")) for b in summary_text if isinstance(b, dict) and b.get("type") == "text"
                )
            summary_str = str(summary_text).strip()
            if len(summary_str) > 30:
                if "<compacted-summary>" not in summary_str:
                    summary_str = f"<compacted-summary>\n{summary_str}\n</compacted-summary>"
                extra_blocks = []
                if read_files and "<read-files>" not in summary_str:
                    extra_blocks.append("<read-files>\n" + "\n".join(f"- {f}" for f in read_files) + "\n</read-files>")
                if modified_files and "<modified-files>" not in summary_str:
                    extra_blocks.append(
                        "<modified-files>\n" + "\n".join(f"- {f}" for f in modified_files) + "\n</modified-files>"
                    )
                if established_levels and "<established_levels>" not in summary_str:
                    extra_blocks.append(
                        "<established_levels>\n"
                        + "\n".join(f"- {lvl}" for lvl in established_levels)
                        + "\n</established_levels>"
                    )
                if extra_blocks:
                    summary_str = f"{summary_str}\n" + "\n".join(extra_blocks)
                return summary_str
        except Exception as e:
            logger.debug(
                f"[ContextCompressor] Replay prefix summarization failed, falling back to modular summarizer: {e}"
            )

        return await self.summarize_middle(middle)

    async def compress(
        self,
        messages: List[dict],
        max_context_chars: int = 100000,
        tail_turns: int = 3,
        primary_client: Optional[Any] = None,
    ) -> List[dict]:
        """Phase 4: Assembly.

        Executes full 4-phase context compression pipeline:
        1. Feasibility Skip: Ignore small contexts (< 1000 tokens / max_context_chars).
        2. Prune redundant tool outputs.
        3. Split into Head, Middle, Tail (tool-pair snapped).
        4. Summarize Middle via aux model / rules with iterative chaining (or replay-prefix).
        5. Assemble Head + [Condensed Summary Message] + Tail.
        """
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        if total_chars <= max_context_chars:
            return messages

        # Phase 0: Offload historical high-res charts older than 2 turns to eliminate multimodal sinks
        messages = offload_historical_charts(messages, retain_recent_turns=2)

        # Stage 0: Deterministic model-free pruning of oversized tool results (> 8192 chars)
        messages = prune_oversized_tool_results(messages)

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

        # Phase 3: Auxiliary Model Summarization (with Replay-Prefix KV-Cache Optimization)
        if primary_client:
            summary_text = await self.summarize_with_replay_prefix(head, middle, client=primary_client)
        else:
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


is_balanced_tool_boundary = ContextCompressor.is_balanced_tool_boundary
