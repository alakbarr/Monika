# ==============================================================================
# File: tests/telegram_bot/test_sanitizer.py
# Description: Test suite for zero-emoticon sanitization and markdown/HTML formatting
# ==============================================================================

import pytest
from telegram_bot.sanitizer import strip_emojis_and_emoticons, sanitize_telegram_html


def test_strip_unicode_emojis():
    raw = "🚀 Halo Admin! 📊 PnL hari ini +$150.00 ⚠️ Risiko aman ✅"
    cleaned = strip_emojis_and_emoticons(raw)
    assert "🚀" not in cleaned
    assert "📊" not in cleaned
    assert "⚠️" not in cleaned
    assert "✅" not in cleaned
    assert "Halo Admin! PnL hari ini +$150.00 Risiko aman" in cleaned


def test_strip_ascii_emoticons():
    raw = "Analisis pasar selesai :) Target tercapai :D Harap pantau ;)"
    cleaned = strip_emojis_and_emoticons(raw)
    assert ":)" not in cleaned
    assert ":D" not in cleaned
    assert ";)" not in cleaned
    assert "Analisis pasar selesai Target tercapai Harap pantau" in cleaned


def test_preserve_math_and_trading_syntax():
    raw = "Order Buy 0.01 lot XAUUSD @ 2400.50 | SL < 2390.00 | TP >= 2420.00 (Risk: 1.5%)"
    cleaned = strip_emojis_and_emoticons(raw)
    assert "XAUUSD" in cleaned
    assert "SL < 2390.00" in cleaned
    assert "TP >= 2420.00" in cleaned
    assert "(Risk: 1.5%)" in cleaned


def test_sanitize_telegram_html_zero_emoji():
    raw = "### *Status Sistem* 🚀\n- Saldo: $1,000.00 :)\n- Posisi: `XAUUSD` 0.01 lot ✅"
    html_out = sanitize_telegram_html(raw)
    assert "🚀" not in html_out
    assert ":)" not in html_out
    assert "✅" not in html_out
    assert "<code>XAUUSD</code>" in html_out
    assert "<b>" in html_out
