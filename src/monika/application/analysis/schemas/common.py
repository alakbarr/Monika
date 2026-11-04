# ==============================================================================
# File: application/analysis/schemas/common.py
# ==============================================================================

"""
Common Enums and Coercion Utilities for Analysis Schemas.
"""

from __future__ import annotations

import logging
import math
import re
from enum import Enum
from typing import Any, List, Optional

logger = logging.getLogger("TradingAgent.Schemas")


class TradeDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    WAIT = "wait"
    AVOID = "avoid"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SentimentBand(str, Enum):
    BULLISH = "Bullish"
    MILDLY_BULLISH = "Mildly Bullish"
    NEUTRAL = "Neutral"
    MIXED = "Mixed"
    MILDLY_BEARISH = "Mildly Bearish"
    BEARISH = "Bearish"


class MacroRegime(str, Enum):
    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    STAGFLATION = "stagflation"
    DISINFLATION = "disinflation"
    TRANSITION = "transition"
    MIXED = "mixed"


def coerce_str(v: Any, default: str = "") -> str:
    """
    Safely coerces any value (dict, list, int, float, string, None) into a clean string.
    If dict, extracts substantive fields ('detail', 'condition', 'event', 'title', etc.)
    or formats key-values.
    """
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for field in (
            "condition",
            "detail",
            "summary",
            "event",
            "event_name",
            "title",
            "headline",
            "name",
            "reason",
            "justification",
            "narrative",
            "text",
        ):
            if field in v and v[field]:
                return str(v[field]).strip()
        parts = [f"{k}: {val}" for k, val in v.items() if val is not None and str(val).strip()]
        return "; ".join(parts) if parts else str(v)
    if isinstance(v, (list, tuple, set)):
        return "; ".join(coerce_str(item) for item in v if item is not None and str(item).strip())
    return str(v).strip()


def coerce_string_list(v: Any, default: Optional[List[str]] = None) -> Optional[List[str]]:
    """
    Safely coerces any value (list, tuple, set, dict, single string, numbers, None)
    into a clean List[str] where every item is guaranteed to be a non-empty string.
    Dictionaries inside lists (e.g. from get_economic_calendar or get_news_items)
    are gracefully extracted into human-readable strings like 'CPI (USD, high, 14:00)'.
    """
    if v is None:
        return default
    if isinstance(v, str):
        s = v.strip()
        if not s or s.lower() in ("none", "null", "n/a", "[]", "{}"):
            return default if default is not None else []
        if "\n" in s or "," in s:
            raw_items = re.split(r"[\n,]+", s)
            items = []
            for item in raw_items:
                clean_item = item.strip()
                # Strip only bullet / numbered prefixes (e.g. '1. ', '- ', 'â€¢ ') preserving numeric dates/prices
                clean_item = re.sub(r"^(?:[-*â€¢]|\d+[.)])\s+", "", clean_item).strip()
                if clean_item:
                    items.append(clean_item)
            return items
        return [re.sub(r"^(?:[-*â€¢]|\d+[.)])\s+", "", s).strip()]
    if isinstance(v, (list, tuple, set)):
        result = []
        for item in v:
            if item is None:
                continue
            if isinstance(item, str):
                s = item.strip()
                if s and s.lower() not in ("none", "null", "n/a"):
                    result.append(s)
            elif isinstance(item, dict):
                name = (
                    item.get("event_name")
                    or item.get("event")
                    or item.get("title")
                    or item.get("headline")
                    or item.get("name")
                    or item.get("driver")
                    or ""
                )
                impact = item.get("impact") or item.get("expected_impact") or ""
                currency = item.get("currency") or ""
                time_val = item.get("time") or item.get("event_time") or ""

                parts = [str(name).strip()] if name else []
                meta = [str(p).strip() for p in (currency, impact, time_val) if p and str(p).strip()]
                if meta:
                    parts.append(f"({', '.join(meta)})")

                if parts:
                    result.append(" ".join(parts).strip())
                else:
                    kv = [f"{k}: {val}" for k, val in item.items() if val is not None and str(val).strip()]
                    if kv:
                        result.append(", ".join(kv))
            else:
                s = str(item).strip()
                if s:
                    result.append(s)
        return result
    if isinstance(v, dict):
        return [f"{k}: {val}" for k, val in v.items() if val is not None and str(val).strip()]
    return [str(v).strip()]


def coerce_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely coerces strings, percentages, numbers, and common LLM non-numeric strings
    (e.g., '58.4%', '+12.5%', '~4.25', 'N/A', 'none', 'null', 'not quoted') into float or None.
    Rejects descriptive strings containing ambiguous text (e.g. 'target near 1.0850 or 1.0900').
    """
    if v is None or isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv):
            return default
        return fv
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s or s.lower() in (
            "none",
            "null",
            "n/a",
            "na",
            "nan",
            "nil",
            "unknown",
            "not_applicable",
            "not applicable",
            "not quoted",
            "not_quoted",
            "-",
            "--",
        ):
            return default
        clean_s = re.sub(r"^[~><$â‚¬Â£Â¥\s]+|(?:%|\s+|pts|bps|pips|long|short)+$", "", s, flags=re.IGNORECASE).strip()
        # Supports standard decimals and scientific notation (e.g. 1e-4)
        if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", clean_s):
            try:
                return float(clean_s)
            except ValueError:
                return default
    return default


def coerce_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Safely coerces strings (e.g. '8', '8/10', '8.0', 'N/A') into int or None.
    Rejects descriptive strings to prevent extraction of arbitrary numbers.
    """
    if v is None or isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return default
        return int(round(v))
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s or s.lower() in ("none", "null", "n/a", "na", "nan", "nil", "unknown", "not_applicable", "-", "--"):
            return default
        # Strip score denominator like '/10' or '/ 10' or '%', 'pts'
        clean_s = re.sub(r"/\s*\d+$", "", s).strip()
        clean_s = re.sub(r"^[~><$â‚¬Â£Â¥\s]+|(?:%|\s+|pts|bps|pips)+$", "", clean_s, flags=re.IGNORECASE).strip()
        if re.fullmatch(r"[-+]?\d+(?:\.0+)?", clean_s):
            try:
                fv = float(clean_s)
                if math.isnan(fv) or math.isinf(fv):
                    return default
                return int(fv)
            except ValueError, OverflowError:
                return default
    return default
