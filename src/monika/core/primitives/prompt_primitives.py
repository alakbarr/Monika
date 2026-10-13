# ==============================================================================
# Package: monika.core.primitives
# File: prompt_primitives.py
# Description: Pure core prompt formatting and token estimation primitives.
# ==============================================================================

from __future__ import annotations

from typing import Any


def _flatten_system_prompt(sp: Any) -> str:
    """Flatten string, tuple, list, or dict-block system prompt into a clean canonical string."""
    if sp is None:
        return ""
    if isinstance(sp, (tuple, list)):
        parts = []
        for p in sp:
            if isinstance(p, dict):
                parts.append(str(p.get("text", "")).strip())
            elif p:
                parts.append(str(p).strip())
        return "\n\n".join(part for part in parts if part)
    if isinstance(sp, dict):
        return str(sp.get("text", "")).strip()
    return str(sp)


def estimate_tokens(text: str) -> int:
    """Estimate token count based on standard ~4 chars per token heuristic."""
    if not text:
        return 0
    return max(1, len(text) // 4)


__all__ = ["_flatten_system_prompt", "estimate_tokens"]
