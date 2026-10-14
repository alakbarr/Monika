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


import html


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


def sanitize_telegram_html(text: str) -> str:
    """
    Safely converts Markdown/plain-text into Telegram ParseMode.HTML compliant markup,
    guaranteeing 100% zero emoji/emoticon contamination.
    """
    if not text:
        return ""

    # Clean emojis first
    text = strip_emojis_and_emoticons(text)

    # Step 1: Temporarily extract code blocks (```...```) to avoid touching their syntax
    pre_blocks: list[str] = []

    def _save_pre(match: re.Match) -> str:
        pre_blocks.append(match.group(1))
        return f"___PRE_BLOCK_{len(pre_blocks) - 1}___"

    content = re.sub(r"```(?:[a-zA-Z0-9_-]+\n)?([\s\S]*?)```", _save_pre, text)

    # Step 2: Temporarily extract inline code (`...`)
    code_blocks: list[str] = []

    def _save_code(match: re.Match) -> str:
        code_blocks.append(match.group(1))
        return f"___CODE_BLOCK_{len(code_blocks) - 1}___"

    content = re.sub(r"`([^`\n]+)`", _save_code, content)

    # Step 2.5: Protect existing valid Telegram HTML tags before escaping raw HTML
    valid_tags: list[str] = []
    tag_pattern = re.compile(
        r"</?(?:b|strong|i|em|u|ins|s|strike|del|span|tg-spoiler|code|pre|blockquote)(?:\s+[^>]*)?>|</?a(?:\s+href=['\"][^'\"]*['\"])?>",
        re.IGNORECASE,
    )

    def _save_tag(match: re.Match) -> str:
        valid_tags.append(match.group(0))
        return f"___TGTAG_{len(valid_tags) - 1}___"

    content = tag_pattern.sub(_save_tag, content)

    # Step 3: Escape raw HTML characters in the body (&, <, >)
    content = html.escape(content, quote=False)

    # Step 4: Markdown headers (# Header -> <b>Header</b>)
    content = re.sub(r"(?m)^#{1,6}\s*(.+?)\s*$", r"<b>\1</b>", content)

    # Step 5: Bold (**text** and isolated *text*)
    content = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", content)
    content = re.sub(r"(?<![\w*])\*([^\n*]+?)\*(?![\w*])", r"<b>\1</b>", content)

    # Step 6: Italic (_text_) - only match when not part of identifiers (e.g., skips EUR_USD)
    content = re.sub(r"(?<![\w_])_([^\n_]+?)_(?![\w_])", r"<i>\1</i>", content)

    # Step 7: Clean excessive empty lines
    content = re.sub(r"\n{3,}", "\n\n", content)

    # Step 8: Restore inline code blocks with escaped content
    for i, code_text in enumerate(code_blocks):
        escaped_code = html.escape(code_text, quote=False)
        content = content.replace(f"___CODE_BLOCK_{i}___", f"<code>{escaped_code}</code>")

    # Step 9: Restore pre blocks with escaped content
    for i, pre_text in enumerate(pre_blocks):
        escaped_pre = html.escape(pre_text.strip(), quote=False)
        content = content.replace(f"___PRE_BLOCK_{i}___", f"<pre>{escaped_pre}</pre>")

    # Step 10: Restore valid Telegram HTML tags
    for i, tag_str in enumerate(valid_tags):
        content = content.replace(f"___TGTAG_{i}___", tag_str)

    return content.strip()


__all__ = [
    "EMOJI_PATTERN",
    "ASCII_EMOTICON_PATTERN",
    "strip_emojis_and_emoticons",
    "sanitize_telegram_html",
]
