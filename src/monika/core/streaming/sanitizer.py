"""
Text Sanitizer and Unicode/Emoji Stripper.
Canonical pure regex patterns for stripping emojis, emoticons, and whitespace artifacts.
"""

from __future__ import annotations

import re

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # Emoticons
    "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
    "\U0001F680-\U0001F6FF"  # Transport & Map
    "\U0001F700-\U0001F77F"  # Alchemical Symbols
    "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
    "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols
    "\U0001FA00-\U0001FA6F"  # Chess / Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "\U00002700-\U000027BF"  # Dingbats
    "\U00002600-\U000026FF"  # Miscellaneous Symbols
    "\U00002300-\U000023FF"  # Misc Technical
    "\U00002B50-\U00002B55"  # Stars / Circles
    "\U0001F1E6-\U0001F1FF"  # Flags
    "\U0000FE00-\U0000FE0F"  # Variation Selectors
    "]+",
    flags=re.UNICODE,
)

ASCII_EMOTICON_PATTERN = re.compile(
    r'(?:(?<=^)|(?<=\s))(?:[:;=8]-?[)D(\]pP3/\\oO@*sS]|\^_\^|\^\^|-_-|[xX]_[xX]|<3|XD|xd)(?:(?=$)|(?=[\s.,!?]))'
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
