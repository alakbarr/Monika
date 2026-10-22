"""
Model-Free Deterministic Tool Result Pruner.
Reclaims 30-70% of context window tokens at zero LLM cost across multi-turn reasoning loops
by deterministically pruning massive terminal, shell, file, and raw JSON outputs.
Maintains critical initiation metadata at the head and decisive exit codes/errors at the tail.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("TradingAgent.Harness.GeneralToolPruner")

DEFAULT_MAX_CHARS = 2500  # ~600 tokens per tool output threshold


class GeneralToolPruner:
    """
    Deterministic Zero-Cost Tool Output Pruner.
    Splits long textual and JSON payloads into a 40% Head / 60% Tail representation,
    preserving execution commands at the top and stack traces / exit codes at the bottom.
    """

    @staticmethod
    def safe_unicode_slice(text: str, start: Optional[int] = None, end: Optional[int] = None) -> str:
        """Slices string safely without splitting surrogate pairs or multibyte characters."""
        if not text:
            return ""
        return text[start:end]

    @classmethod
    def prune_text(
        cls,
        text: str,
        max_chars: int = DEFAULT_MAX_CHARS,
        tool_name: str = "tool",
        head_ratio: float = 0.40,
    ) -> str:
        """
        Prunes arbitrary plain-text output (e.g. bash stdout/stderr, file reads, logs)
        to within max_chars. Preserves head and tail, removing the noisy middle.
        """
        if not text or len(text) <= max_chars:
            return text or ""

        head_len = int(max_chars * head_ratio)
        tail_len = max_chars - head_len

        head_part = cls.safe_unicode_slice(text, 0, head_len)
        tail_part = cls.safe_unicode_slice(text, -tail_len, None)

        omitted_chars = len(text) - (len(head_part) + len(tail_part))
        omitted_lines = text[len(head_part) : -len(tail_part)].count("\n")

        marker = (
            f"\n\n[... {omitted_chars} characters ({omitted_lines} lines) omitted by "
            f"GeneralToolPruner from tool '{tool_name}' ...]\n\n"
        )
        return f"{head_part}{marker}{tail_part}"

    @classmethod
    def prune_json(
        cls,
        data: Union[Dict[str, Any], List[Any], str],
        max_chars: int = DEFAULT_MAX_CHARS,
        tool_name: str = "tool",
    ) -> str:
        """
        Prunes JSON structures. If the payload is JSON-serializable and exceeds max_chars,
        structures a valid JSON preview with head/tail items to prevent breaking upstream LLM parsers.
        """
        raw_str = json.dumps(data, default=str) if not isinstance(data, str) else data
        if len(raw_str) <= max_chars:
            return raw_str

        # Attempt to parse into structured preview if valid JSON
        try:
            parsed = json.loads(raw_str) if isinstance(data, str) else data
            if isinstance(parsed, list):
                if len(parsed) > 8:
                    head_items = parsed[:4]
                    tail_items = parsed[-3:]
                    preview_payload: Dict[str, Any] = {
                        "_pruned_status": "truncated_list",
                        "tool_name": tool_name,
                        "total_items": len(parsed),
                        "head_items": head_items,
                        "tail_items": tail_items,
                        "notice": f"List truncated by GeneralToolPruner: showing first 4 and last 3 of {len(parsed)} items.",
                    }
                    res_str = json.dumps(preview_payload, indent=2, default=str)
                    if len(res_str) <= max_chars:
                        return res_str
                    # Fallback to compact JSON
                    compact_str = json.dumps(preview_payload, default=str)
                    if len(compact_str) <= max_chars:
                        return compact_str
                    # Ultra-compact list preview
                    preview_payload["head_items"] = parsed[:2]
                    preview_payload["tail_items"] = parsed[-1:]
                    ultra_compact = json.dumps(preview_payload, default=str)
                    if len(ultra_compact) <= max_chars:
                        return ultra_compact

            elif isinstance(parsed, dict):
                keys = list(parsed.keys())
                if len(keys) > 10:
                    subset: Dict[str, Any] = {}
                    for k in keys[:6]:
                        v = parsed[k]
                        subset[k] = (
                            (v[:3] if isinstance(v, list) else v)
                            if not isinstance(v, dict)
                            else {sk: v[sk] for sk in list(v.keys())[:3]}
                        )
                    for k in keys[-3:]:
                        if k not in subset:
                            subset[k] = parsed[k]
                    subset["_pruned_notice"] = f"Dictionary truncated: showing key subset of {len(keys)} total keys."
                    res_str = json.dumps(subset, indent=2, default=str)
                    if len(res_str) <= max_chars:
                        return res_str
                    compact_str = json.dumps(subset, default=str)
                    if len(compact_str) <= max_chars:
                        return compact_str
                    # Ultra-compact dict preview
                    minimal_subset = {k: parsed[k] for k in keys[:2]}
                    minimal_subset["_pruned_notice"] = f"Dictionary truncated to 2 of {len(keys)} keys."
                    ultra_compact = json.dumps(minimal_subset, default=str)
                    if len(ultra_compact) <= max_chars:
                        return ultra_compact
        except Exception:
            pass

        # Safe valid JSON envelope fallback
        fallback_payload = {
            "_pruned_status": "truncated_json",
            "tool_name": tool_name,
            "raw_snippet": cls.prune_text(raw_str, max_chars=max(max_chars - 120, 50), tool_name=tool_name),
        }
        return json.dumps(fallback_payload, default=str)
