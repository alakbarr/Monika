# ==============================================================================
# File: agent/scratchpad_guard.py
# ==============================================================================

"""
Scratchpad Guard & Incomplete Reasoning Tag Recovery.
Institutional-grade engine turn protection architecture.

When reasoning models (DeepSeek-R1, Qwen-2.5, Claude 3.7 with extended thinking,
GPT-6 reasoning modes) run out of output token budget while thinking, the
<REASONING_SCRATCHPAD>, <think>, or <thought> tag is opened but never closed.

This guard detects truncated reasoning streams, tracks attempt retries (up to 2),
and if exhausted, gracefully preserves the partial thought chain and finalizes the turn.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger("TradingAgent.Agent.ScratchpadGuard")

# Recognized reasoning block tags
SCRATCHPAD_TAGS = [
    (r"<REASONING_SCRATCHPAD>", r"</REASONING_SCRATCHPAD>"),
    (r"<think>", r"</think>"),
    (r"<thought>", r"</thought>"),
]


def has_incomplete_scratchpad(content: Optional[str]) -> bool:
    """
    Checks if a reasoning tag was opened but never closed.
    Indicates model ran out of max output tokens mid-reasoning.
    """
    if not content:
        return False

    for open_tag, close_tag in SCRATCHPAD_TAGS:
        open_matches = list(re.finditer(open_tag, content, re.IGNORECASE))
        close_matches = list(re.finditer(close_tag, content, re.IGNORECASE))

        # Opened more times than closed, or opened at end with no closing tag
        if len(open_matches) > len(close_matches):
            logger.warning(
                f"[ScratchpadGuard] Incomplete reasoning tag detected: "
                f"'{open_tag}' opened ({len(open_matches)}x) but closed only ({len(close_matches)}x)."
            )
            return True

    return False


def extract_reasoning_and_content(content: str) -> Tuple[Optional[str], str, bool]:
    """
    Extracts reasoning thinking content and visible assistant content.
    Returns: (reasoning_text, visible_text, is_incomplete)
    """
    if not content:
        return None, "", False

    is_incomplete = has_incomplete_scratchpad(content)
    visible_text = content
    reasoning_parts = []

    for open_tag, close_tag in SCRATCHPAD_TAGS:
        pattern = f"{open_tag}(.*?)(?:{close_tag}|$)"
        for match in re.finditer(pattern, visible_text, re.DOTALL | re.IGNORECASE):
            reasoning_parts.append(match.group(1).strip())
        # Strip all reasoning blocks from visible text
        visible_text = re.sub(f"{open_tag}.*?(?:{close_tag}|$)", "", visible_text, flags=re.DOTALL | re.IGNORECASE)

    extracted_reasoning = "\n\n".join(reasoning_parts) if reasoning_parts else None
    return extracted_reasoning, visible_text.strip(), is_incomplete


def close_dangling_scratchpad(content: str) -> str:
    """
    If a reasoning tag is unclosed, synthetically append the appropriate closing tag
    so markdown and downstream XML/tag parsers do not break.
    """
    if not content:
        return content

    for open_tag, close_tag in SCRATCHPAD_TAGS:
        open_matches = list(re.finditer(open_tag, content, re.IGNORECASE))
        close_matches = list(re.finditer(close_tag, content, re.IGNORECASE))
        if len(open_matches) > len(close_matches):
            raw_close = close_tag.replace("\\", "")
            content = content.rstrip() + f"\n{raw_close}\n"
            logger.info(f"[ScratchpadGuard] Synthetically closed dangling reasoning tag with {raw_close}")

    return content
