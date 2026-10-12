# ==============================================================================
# File: telegram_bot/sanitizer.py
# Description: Message Sanitizer and HTML Formatter (Zero-Emoji & Clean Markdown)
# ==============================================================================

"""
Message Sanitizer and Telegram HTML Formatter.

1. Converts markdown-formatted text and raw content into compliant, error-free HTML
   for Telegram's ParseMode.HTML.
2. Unconditionally strips all Unicode emojis and ASCII emoticons across all messages.
3. Cleans whitespace and protects against malformed HTML tags.
"""

import html
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
    # Clean up double spaces left behind on lines
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Clean up spaces before newlines or at start of lines
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
        return f"___PRE_BLOCK_{len(pre_blocks)-1}___"

    content = re.sub(r"```(?:[a-zA-Z0-9_-]+\n)?([\s\S]*?)```", _save_pre, text)

    # Step 2: Temporarily extract inline code (`...`)
    code_blocks: list[str] = []

    def _save_code(match: re.Match) -> str:
        code_blocks.append(match.group(1))
        return f"___CODE_BLOCK_{len(code_blocks)-1}___"

    content = re.sub(r"`([^`\n]+)`", _save_code, content)

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

    return content.strip()
