# ==============================================================================
# Description: Backward-compatibility shim for monika.infrastructure.database.adapters
# ==============================================================================
"""Backward-compatibility shim. Canonical: monika.infrastructure.database.adapters"""

import sys
import monika.infrastructure.database.adapters as _canonical

from monika.infrastructure.database.adapters import (
    CURRENCY_KEYWORDS,
    CURRENCY_PATTERNS,
    _now_utc,
    batch_save_calendar,
    batch_save_fedwatch,
    batch_save_news,
    batch_save_tweets,
    calendar_event_to_model,
    extract_currency_tags,
    fed_meeting_to_models,
    logger,
    parse_timestamp,
    scraped_news_to_model,
    scraped_tweet_to_model,
)

sys.modules[__name__] = _canonical

__all__ = [
    "CURRENCY_KEYWORDS",
    "CURRENCY_PATTERNS",
    "_now_utc",
    "batch_save_calendar",
    "batch_save_fedwatch",
    "batch_save_news",
    "batch_save_tweets",
    "calendar_event_to_model",
    "extract_currency_tags",
    "fed_meeting_to_models",
    "logger",
    "parse_timestamp",
    "scraped_news_to_model",
    "scraped_tweet_to_model",
]
