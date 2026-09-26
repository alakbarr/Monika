# ==============================================================================
# File: agent/repetition_guard.py
# ==============================================================================

"""
Repetition Guard & Degenerative Loop Immunizer.
Institutional-grade engine turn protection architecture.

Detects degenerative sliding window repetitions (60-char window dominating >= 50%
of a text fragment >= 400 chars) while discriminating against legitimate structured
outputs (SQL inserts, market quote tables) via unique line ratio analysis.

Immunizes the conversation transcript upon interruption by substituting the runaway
loop text with REPETITION_LOOP_INTERRUPTED marker.
"""

from __future__ import annotations

import logging
import re
import math
from collections import Counter
from typing import Optional

logger = logging.getLogger("TradingAgent.Agent.RepetitionGuard")

MIN_FRAGMENT_LENGTH = 400
_REPEAT_WINDOW = 60
_MIN_REPEAT_COUNT = 5
_DOMINANCE_RATIO = 0.5
_RUNAWAY_DISTINCT_LINE_RATIO = 0.5

REPETITION_LOOP_INTERRUPTED = "[the reply degenerated into a repetition loop and was interrupted]"


def _line_repetition_dominated(text: str, n: int) -> bool:
    """True when a single normalized line covers half the fragment via repeats."""
    counts = Counter(norm for norm in (line.strip() for line in text.splitlines()) if norm)
    return any(c >= _MIN_REPEAT_COUNT and c * len(line) >= n * _DOMINANCE_RATIO for line, c in counts.items())


def is_repetition_dominated(text: str) -> bool:
    """
    True when a single 60+ char substring recurs often enough to cover at least half
    of ``text`` — the signature of a repetition loop. Fail-open for non-string/short input.
    """
    if not isinstance(text, str):
        return False
    n = len(text)
    if n < MIN_FRAGMENT_LENGTH:
        return False

    # Fast path: one normalized line duplicated enough to cover half the fragment
    if _line_repetition_dominated(text, n):
        return True

    # General path: fixed-size windows sliding one char at a time
    window = _REPEAT_WINDOW
    needed = max(_MIN_REPEAT_COUNT, math.ceil(n * _DOMINANCE_RATIO / window))
    counts: dict[str, int] = {}
    for i in range(n - window + 1):
        key = text[i : i + window]
        c = counts.get(key, 0) + 1
        if c >= needed:
            return True
        counts[key] = c
    return False


def is_runaway_repetition(text: str) -> bool:
    """
    Stricter than is_repetition_dominated: also require the runaway shape.
    Legitimate structured outputs (e.g. SQL batches, table rows) have varied lines,
    whereas runaway loops repeat the exact same line or character fragment.
    """
    if not is_repetition_dominated(text):
        return False
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if len(lines) < _MIN_REPEAT_COUNT:
        return True  # no line structure to judge by: a dominated single-line loop
    return len(set(lines)) <= len(lines) * _RUNAWAY_DISTINCT_LINE_RATIO


def sanitize_repetition_in_transcript(messages: list[dict], interrupted_turn_content: str) -> list[dict]:
    """
    Immunize transcript: if the last message degenerated into a loop, substitute
    it with REPETITION_LOOP_INTERRUPTED so that downstream prompt context does not
    re-feed the toxic loop back into the model.
    """
    if not messages:
        return messages

    if is_runaway_repetition(interrupted_turn_content):
        if messages[-1].get("role") == "assistant":
            messages[-1]["content"] = REPETITION_LOOP_INTERRUPTED
            logger.info("[RepetitionGuard] Transcript immunized with REPETITION_LOOP_INTERRUPTED marker.")
    return messages
