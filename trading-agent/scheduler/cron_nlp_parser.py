# ==============================================================================
# File: scheduler/cron_nlp_parser.py
# ==============================================================================

"""
Natural Language Schedule Parser.
Institutional-grade engine turn protection architecture.

Parses human natural language scheduling expressions ("every 5 minutes",
"every weekday at 8:30", "daily at 21:00 UTC", "hourly") into standard
5-field cron expressions or precise periodic intervals.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger("TradingAgent.Scheduler.CronNlpParser")

# Standard trading market session hours (UTC)
MARKET_SESSIONS_UTC = {
    "london_open": ("0 8 * * 1-5", "London Session Open (08:00 UTC)"),
    "ny_open": ("30 13 * * 1-5", "New York Session Open (13:30 UTC)"),
    "tokyo_open": ("0 0 * * 1-5", "Tokyo Session Open (00:00 UTC)"),
    "daily_close": ("0 22 * * 1-5", "Forex Daily Close (22:00 UTC)"),
}


def parse_natural_schedule(text: str) -> Tuple[Optional[str], Optional[float], str]:
    """
    Parse natural language schedule expression.
    
    Returns:
        (cron_expr, interval_seconds, human_description)
        Exactly one of cron_expr or interval_seconds will be set.
    """
    raw = text.strip().lower()

    # 1. Direct standard 5-part cron expression (e.g. "*/10 * * * *")
    cron_parts = raw.split()
    if len(cron_parts) == 5:
        pattern = r"^[\d*\/,-]+$"
        if all(re.match(pattern, part) for part in cron_parts):
            return " ".join(cron_parts), None, f"Custom Cron: {' '.join(cron_parts)}"

    # 2. Market session presets
    for key, (expr, desc) in MARKET_SESSIONS_UTC.items():
        if key in raw or key.replace("_", " ") in raw:
            return expr, None, desc

    # 3. Seconds interval ("every X seconds")
    sec_match = re.search(r"every\s+(\d+)\s*(?:seconds?|secs?|s)", raw)
    if sec_match:
        val = float(sec_match.group(1))
        return None, val, f"Every {int(val)} seconds"

    # 4. Minute intervals ("every X minutes")
    min_match = re.search(r"every\s+(\d+)\s*(?:minutes?|mins?|m)", raw)
    if min_match:
        mins = int(min_match.group(1))
        if mins in {1, 2, 3, 5, 10, 15, 20, 30}:
            return f"*/{mins} * * * *", None, f"Every {mins} minutes"
        else:
            return None, float(mins * 60), f"Every {mins} minutes"

    if raw in {"every minute", "minutely"}:
        return "* * * * *", None, "Every minute"

    # 5. Hour intervals ("every X hours", "hourly")
    hour_match = re.search(r"every\s+(\d+)\s*(?:hours?|hrs?|h)", raw)
    if hour_match:
        hrs = int(hour_match.group(1))
        if hrs in {1, 2, 3, 4, 6, 8, 12}:
            return f"0 */{hrs} * * *", None, f"Every {hrs} hours"
        else:
            return None, float(hrs * 3600), f"Every {hrs} hours"

    if raw in {"hourly", "every hour"}:
        return "0 * * * *", None, "Every hour"

    # 6. Daily at specific time ("daily at HH:MM", "every day at HH:MM")
    daily_time_match = re.search(r"(?:daily|every\s+day)\s+at\s+(\d{1,2}):(\d{2})", raw)
    if daily_time_match:
        h = int(daily_time_match.group(1))
        m = int(daily_time_match.group(2))
        return f"{m} {h} * * *", None, f"Daily at {h:02d}:{m:02d} UTC"

    # 7. Weekdays at specific time ("every weekday at HH:MM")
    weekday_time_match = re.search(r"every\s+weekday\s+at\s+(\d{1,2}):(\d{2})", raw)
    if weekday_time_match:
        h = int(weekday_time_match.group(1))
        m = int(weekday_time_match.group(2))
        return f"{m} {h} * * 1-5", None, f"Every weekday at {h:02d}:{m:02d} UTC"

    # Default fallback: 1 hour interval
    logger.warning(f"[CronNlpParser] Could not unambiguously parse '{text}', defaulting to 1-hour interval.")
    return "0 * * * *", None, f"Default 1-hour interval (unparsed: '{text}')"
