import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from analysis.prefetch.news_digest import (
    generate_deterministic_macro_summary,
    generate_deterministic_currency_summary,
)


class DummyNewsItem:
    def __init__(self, title, impact, published_at=None, sentiment=None, currency_tags=None):
        self.title = title
        self.impact = impact
        self.published_at = published_at or datetime.now(timezone.utc)
        self.sentiment = sentiment or ""
        self.currency_tags = currency_tags or ""


def test_generate_deterministic_macro_summary_high_vix():
    news = [
        DummyNewsItem("US CPI jumps to 4.5% year-over-year", "BREAKING", currency_tags="USD"),
        DummyNewsItem("Fed signals emergency policy meeting", "HIGH", currency_tags="USD"),
        DummyNewsItem("Oil prices spike on supply disruption", "HIGH", currency_tags="XTI"),
    ]
    signals_table = "| USD | BULLISH | HIGH | +5 | CPI beat |"
    market_ctx = {
        "vix": {"value": 28.5, "regime": "high_fear"},
        "dxy": {"latest": 106.2, "trend_5d": "strengthening"},
    }

    summary = generate_deterministic_macro_summary(
        all_news=news,
        currency_signals_table=signals_table,
        market_ctx=market_ctx,
    )

    assert "**[MACRO REGIME]**" in summary
    assert "Risk-Off / High Volatility" in summary
    assert "VIX at 28.5" in summary
    assert "**[KEY DRIVERS]**" in summary
    assert "US CPI jumps to 4.5%" in summary
    assert "[deterministic_fallback: true]" in summary


def test_generate_deterministic_macro_summary_low_vix():
    news = [
        DummyNewsItem("Markets extend quiet summer consolidation", "LOW", currency_tags="EUR"),
    ]
    market_ctx = {
        "vix": {"value": 13.2, "regime": "complacent"},
        "dxy": {"latest": 102.1, "trend_5d": "weakening"},
    }

    summary = generate_deterministic_macro_summary(
        all_news=news,
        currency_signals_table="",
        market_ctx=market_ctx,
    )

    assert "Risk-On / Complacent" in summary
    assert "VIX at 13.2" in summary


def test_generate_deterministic_currency_summary_bullish_bias():
    items = [
        DummyNewsItem("ECB signals rate hike pause ending", "HIGH", sentiment="BULLISH_EUR"),
        DummyNewsItem("German factory orders surge unexpectedly", "MEDIUM", sentiment="BULLISH_EUR"),
        DummyNewsItem("Minor retail sales dip in Greece", "LOW", sentiment="BEARISH_EUR"),
    ]

    res = generate_deterministic_currency_summary("EUR", items)

    assert "### EUR Nuances" in res
    assert "Current Bias**: BULLISH" in res
    assert "ECB signals rate hike pause" in res
    assert "[deterministic_fallback: true]" in res


def test_generate_deterministic_currency_summary_empty():
    res = generate_deterministic_currency_summary("GBP", [])
    assert "### GBP Nuances" in res
    assert "No significant news for GBP" in res
    assert "[deterministic_fallback: true]" in res
