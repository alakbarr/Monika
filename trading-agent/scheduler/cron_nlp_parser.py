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

    # 3. Indonesian & English Day-of-week with specific time & timezone
    # e.g., "setiap Senin jam 8 pagi WIB", "every monday at 8:00 WIB", "setiap hari jam 06:00"
    day_map = {
        "senin": 1, "monday": 1, "mon": 1,
        "selasa": 2, "tuesday": 2, "tue": 2,
        "rabu": 3, "wednesday": 3, "wed": 3,
        "kamis": 4, "thursday": 4, "thu": 4,
        "jumat": 5, "friday": 5, "fri": 5,
        "sabtu": 6, "saturday": 6, "sat": 6,
        "minggu": 0, "ahad": 0, "sunday": 0, "sun": 0,
    }

    # Detect timezone offset
    tz_offset_hours = 0
    tz_name = "UTC"
    if "wib" in raw:
        tz_offset_hours = 7
        tz_name = "WIB"
    elif "wita" in raw:
        tz_offset_hours = 8
        tz_name = "WITA"
    elif "wit" in raw:
        tz_offset_hours = 9
        tz_name = "WIT"

    # Match Day + Time pattern
    # e.g., "setiap senin jam 8", "every monday at 08:00", "setiap senin jam 8:30 pagi"
    dow_match = re.search(r"(?:setiap|every|tiap)\s+([a-zA-Z]+)\s+(?:jam|pukul|at)\s+(\d{1,2})(?::(\d{2}))?", raw)
    if dow_match:
        day_word = dow_match.group(1).lower()
        if day_word in day_map:
            target_dow = day_map[day_word]
            h = int(dow_match.group(2))
            m = int(dow_match.group(3) or 0)
            if ("sore" in raw or "malam" in raw or "pm" in raw) and h < 12:
                h += 12
            elif ("pagi" in raw or "am" in raw) and h == 12:
                h = 0

            # Convert to UTC
            utc_h = (h - tz_offset_hours) % 24
            # Day might shift if crossing midnight UTC
            shift_days = (h - tz_offset_hours) // 24
            utc_dow = (target_dow + shift_days) % 7 if target_dow != 0 else (7 + shift_days) % 7

            desc = f"Every {day_word.title()} at {h:02d}:{m:02d} {tz_name} ({utc_h:02d}:{m:02d} UTC)"
            return f"{m} {utc_h} * * {utc_dow}", None, desc

    # 4. Seconds interval ("every X seconds" or "setiap X detik")
    sec_match = re.search(r"(?:every|setiap|tiap)\s+(\d+)\s*(?:seconds?|secs?|detik|s)", raw)
    if sec_match:
        val = float(sec_match.group(1))
        return None, val, f"Every {int(val)} seconds"

    # 5. Minute intervals ("every X minutes" or "setiap X menit")
    min_match = re.search(r"(?:every|setiap|tiap)\s+(\d+)\s*(?:minutes?|mins?|menit|m)", raw)
    if min_match:
        mins = int(min_match.group(1))
        if mins in {1, 2, 3, 5, 10, 15, 20, 30}:
            return f"*/{mins} * * * *", None, f"Every {mins} minutes"
        else:
            return None, float(mins * 60), f"Every {mins} minutes"

    if raw in {"every minute", "minutely", "setiap menit", "tiap menit"}:
        return "* * * * *", None, "Every minute"

    # 6. Hour intervals ("every X hours" or "setiap X jam")
    hour_match = re.search(r"(?:every|setiap|tiap)\s+(\d+)\s*(?:hours?|hrs?|jam|h)", raw)
    if hour_match:
        hrs = int(hour_match.group(1))
        if hrs in {1, 2, 3, 4, 6, 8, 12}:
            return f"0 */{hrs} * * *", None, f"Every {hrs} hours"
        else:
            return None, float(hrs * 3600), f"Every {hrs} hours"

    if raw in {"hourly", "every hour", "setiap jam", "tiap jam"}:
        return "0 * * * *", None, "Every hour"

    # 7. Daily at specific time ("daily at HH:MM", "every day at HH:MM", "setiap hari jam HH:MM")
    daily_time_match = re.search(r"(?:daily|every\s+day|setiap\s+hari|tiap\s+hari)\s+(?:at|jam|pukul)\s+(\d{1,2})(?::(\d{2}))?", raw)
    if daily_time_match:
        h = int(daily_time_match.group(1))
        m = int(daily_time_match.group(2) or 0)
        if ("sore" in raw or "malam" in raw or "pm" in raw) and h < 12:
            h += 12
        elif ("pagi" in raw or "am" in raw) and h == 12:
            h = 0
        utc_h = (h - tz_offset_hours) % 24
        return f"{m} {utc_h} * * *", None, f"Daily at {h:02d}:{m:02d} {tz_name} ({utc_h:02d}:{m:02d} UTC)"

    # 8. Weekdays at specific time ("every weekday at HH:MM", "hari kerja jam HH:MM")
    weekday_time_match = re.search(r"(?:every\s+weekday|hari\s+kerja)\s+(?:at|jam|pukul)\s+(\d{1,2})(?::(\d{2}))?", raw)
    if weekday_time_match:
        h = int(weekday_time_match.group(1))
        m = int(weekday_time_match.group(2) or 0)
        if ("sore" in raw or "malam" in raw or "pm" in raw) and h < 12:
            h += 12
        utc_h = (h - tz_offset_hours) % 24
        return f"{m} {utc_h} * * 1-5", None, f"Every weekday at {h:02d}:{m:02d} {tz_name} ({utc_h:02d}:{m:02d} UTC)"

    # Default fallback: 1 hour interval
    logger.warning(f"[CronNlpParser] Could not unambiguously parse '{text}', defaulting to 1-hour interval.")
    return "0 * * * *", None, f"Default 1-hour interval (unparsed: '{text}')"
