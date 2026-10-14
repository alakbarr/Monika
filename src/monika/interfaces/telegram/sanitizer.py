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

from monika.core.streaming.sanitizer import (
    ASCII_EMOTICON_PATTERN,
    EMOJI_PATTERN,
    sanitize_telegram_html,
    strip_emojis_and_emoticons,
)

__all__ = [
    "ASCII_EMOTICON_PATTERN",
    "EMOJI_PATTERN",
    "strip_emojis_and_emoticons",
    "sanitize_telegram_html",
]
