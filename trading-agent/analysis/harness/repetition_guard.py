# ==============================================================================
# File: analysis/harness/repetition_guard.py
# Description: Degenerate Repetition Loop Guard for Assistant Text Generation
# ==============================================================================

"""
Monitors assistant text generation for degenerate repetition loops.
Detects when a model becomes stuck repeating identical sentence or paragraph fragments
(common in quant reasoning models when context limits or hallucination thresholds are reached).
"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger("TradingAgent.Harness.RepetitionGuard")


def detect_text_repetition(
    text: str,
    min_phrase_len: int = 60,
    min_repeats: int = 3,
    dominance_ratio: float = 0.50,
) -> Tuple[bool, Optional[str]]:
    """
    Detect degenerate repeating phrases in model output.

    Args:
        text: Raw text string from model assistant turn.
        min_phrase_len: Minimum substring length in characters to consider a repeating block.
        min_repeats: Minimum number of times the phrase must repeat.
        dominance_ratio: Fraction of total text occupied by repeating instances.

    Returns:
        (is_degenerate, repeated_snippet_or_none)
    """
    if not text or len(text) < min_phrase_len * min_repeats:
        return False, None

    text_len = len(text)
    # Check candidate slice windows
    max_scan_len = min(300, text_len // min_repeats)

    for win_len in range(min_phrase_len, max_scan_len + 1, 20):
        # Sample substrings across the text
        for start_idx in range(0, min(text_len - win_len, 500), 40):
            candidate = text[start_idx : start_idx + win_len]
            # Strip whitespace to avoid matching empty indentation blocks
            clean_cand = candidate.strip()
            if len(clean_cand) < min_phrase_len:
                continue

            count = text.count(clean_cand)
            if count >= min_repeats:
                covered_chars = count * len(clean_cand)
                if (covered_chars / text_len) >= dominance_ratio:
                    snippet = clean_cand[:80] + ("..." if len(clean_cand) > 80 else "")
                    logger.warning(
                        f"[RepetitionGuard] Degenerate loop detected! Phrase ({len(clean_cand)} chars) "
                        f"repeated {count}x, dominating {covered_chars/text_len:.1%} of response: '{snippet}'"
                    )
                    return True, snippet

    return False, None
