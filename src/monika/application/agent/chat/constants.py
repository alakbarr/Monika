# ==============================================================================
# File: application/agent/chat/constants.py
# ==============================================================================

"""
Constants, limits, and Markdown sanitization utilities for chat interactions.
"""

from __future__ import annotations

import re

# Telegram message character limit
TELEGRAM_MAX_CHARS = 4096
HISTORY_WINDOW = 50  # Max conversation turns to include in context
MAX_HISTORY_CHARS = 32000  # ~8k tokens at ~4 characters/token
SESSION_TIMEOUT_HOURS = 24  # Jeda >24 jam memutus rantai riwayat sesi lama


def _sanitize_chat_format(text: str) -> str:
    return _sanitize_telegram_format_impl(text)


def _sanitize_telegram_format_impl(text: str) -> str:
    """
    Sanitasi respon teks agar 100% bebas dari emoticon dan kompatibel dengan Telegram/Web Markdown:
    1. Konversi heading markdown (#, ##, ###, ####) menjadi *Judul* (Bold) untuk Telegram fallback.
    2. Hapus 100% seluruh karakter emoji Unicode dan ASCII emoticons.
    3. Hapus halusinasi footer model di badan teks.
    4. Bersihkan spasi dan baris kosong berlebih.
    """
    if not text:
        return text

    # 0. Saring blok thinking (<think>), context tags internal, dan rahasia
    try:
        from monika.core.streaming.stream_scrubber import StatefulStreamScrubber

        scrubber = StatefulStreamScrubber()
        text = scrubber.process_delta(text) + scrubber.flush()
    except Exception:
        pass

    # 1. Hapus emoji Unicode dan text emoticons secara mutlak
    try:
        from monika.core.streaming.sanitizer import strip_emojis_and_emoticons

        text = strip_emojis_and_emoticons(text)
    except Exception:
        pass

    # 2. Konversi heading markdown (#, ##, ###) menjadi *Judul* (Bold)
    text = re.sub(r"(?m)^#{1,6}\s*(.+?)\s*$", r"*\1*", text)

    # 3. Bersihkan tag model yang mungkin dihalusinasikan oleh LLM di akhir teks
    text = re.sub(
        r"(?m)^\s*\[?_?(?:gemini|claude|deepseek|qwen|gpt|llama|groq|minimax|glm)[-\w\.:]*(?:\s*\|\s*\d+\s*in,\s*\d+\s*out)?_?\]?\s*$",
        "",
        text,
    )

    # 3. Rapikan baris kosong berulang
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_sanitize_telegram_format = _sanitize_telegram_format_impl
