"""
Text Sanitizer and Unicode/Emoji Stripper.
Canonical pure regex patterns for stripping emojis, emoticons, and whitespace artifacts.
"""

from __future__ import annotations

import re

EMOJI_PATTERN = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # Emoticons
    "\U0001f300-\U0001f5ff"  # Symbols & Pictographs
    "\U0001f680-\U0001f6ff"  # Transport & Map
    "\U0001f700-\U0001f77f"  # Alchemical Symbols
    "\U0001f780-\U0001f7ff"  # Geometric Shapes Extended
    "\U0001f800-\U0001f8ff"  # Supplemental Arrows-C
    "\U0001f900-\U0001f9ff"  # Supplemental Symbols
    "\U0001fa00-\U0001fa6f"  # Chess / Symbols
    "\U0001fa70-\U0001faff"  # Symbols and Pictographs Extended-A
    "\U00002700-\U000027bf"  # Dingbats
    "\U00002600-\U000026ff"  # Miscellaneous Symbols
    "\U00002300-\U000023ff"  # Misc Technical
    "\U00002b50-\U00002b55"  # Stars / Circles
    "\U0001f1e6-\U0001f1ff"  # Flags
    "\U0000fe00-\U0000fe0f"  # Variation Selectors
    "]+",
    flags=re.UNICODE,
)

ASCII_EMOTICON_PATTERN = re.compile(
    r"(?:(?<=^)|(?<=\s))(?:[:;=8]-?[)D(\]pP3/\\oO@*sS]|\^_\^|\^\^|-_-|[xX]_[xX]|<3|XD|xd)(?:(?=$)|(?=[\s.,!?]))"
)


def strip_emojis_and_emoticons(text: str) -> str:
    """
    Remove all Unicode emojis and text-based ASCII emoticons from text.
    Preserves all numbers, math operators, prices, and punctuation.
    """
    if not text:
        return ""
    text = EMOJI_PATTERN.sub("", text)
    text = ASCII_EMOTICON_PATTERN.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +(?=\n)", "", text)
    text = re.sub(r"(?<=\n) +", "", text)
    return text.strip()
