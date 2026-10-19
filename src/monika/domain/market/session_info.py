"""Market session tracking and timing rules utility with DST and weekend awareness."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import monika.core.primitives.clock as clock

TOKYO_TZ = ZoneInfo("Asia/Tokyo")
LONDON_TZ = ZoneInfo("Europe/London")
NY_TZ = ZoneInfo("America/New_York")
SYDNEY_TZ = ZoneInfo("Australia/Sydney")


def get_current_market_session(dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Mengembalikan sesi pasar yang sedang aktif, status overlap London-NY,
    deteksi akhir pekan (penutupan pasar FX), dan modifier confluence
    sesuai spesifikasi skills/trading/session_timing_rules.md dengan dukungan DST.
    """
    if dt is None:
        dt = clock.now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    # Convert to market local timezones
    ny_time = dt.astimezone(NY_TZ)
    london_time = dt.astimezone(LONDON_TZ)
    tokyo_time = dt.astimezone(TOKYO_TZ)
    sydney_time = dt.astimezone(SYDNEY_TZ)

    # Weekend check: FX markets close Friday 17:00 NY and reopen Sunday 17:00 NY
    weekday = ny_time.weekday()  # Monday is 0, Sunday is 6
    is_friday_after_close = weekday == 4 and (ny_time.hour > 17 or (ny_time.hour == 17 and ny_time.minute > 0))
    is_saturday = weekday == 5
    is_sunday_before_open = weekday == 6 and ny_time.hour < 17

    is_weekend = is_friday_after_close or is_saturday or is_sunday_before_open

    if is_weekend:
        return {
            "current_time_utc": dt.strftime("%H:%M:%S"),
            "active_sessions": ["Weekend"],
            "is_london_ny_overlap": False,
            "is_off_peak": True,
            "is_weekend": True,
            "session_modifier": -5,
            "status": "closed",
        }

    active_sessions: List[str] = []

    # Sydney: 07:00 - 16:00 Sydney local time
    if 7 <= sydney_time.hour < 16:
        active_sessions.append("Sydney")

    # Tokyo: 09:00 - 18:00 Tokyo local time
    if 9 <= tokyo_time.hour < 18:
        active_sessions.append("Tokyo")

    # London: 08:00 - 16:30 London local time
    if 8 <= london_time.hour < 16 or (london_time.hour == 16 and london_time.minute <= 30):
        active_sessions.append("London")

    # New York: 08:00 - 17:00 New York local time
    if 8 <= ny_time.hour < 17:
        active_sessions.append("New York")

    is_london_ny_overlap = "London" in active_sessions and "New York" in active_sessions
    is_off_peak = len(active_sessions) == 0 or (
        len(active_sessions) == 1 and "Sydney" in active_sessions and dt.hour >= 21
    )

    if is_off_peak and "Off-Peak" not in active_sessions:
        active_sessions.append("Off-Peak")

    confluence_mod = 1 if is_london_ny_overlap else (-2 if is_off_peak else 0)

    return {
        "utc_time": dt.strftime("%H:%M UTC"),
        "current_time_utc": dt.strftime("%H:%M:%S"),
        "active_sessions": active_sessions,
        "overlap": "London-NY" if is_london_ny_overlap else None,
        "is_london_ny_overlap": is_london_ny_overlap,
        "is_off_peak": is_off_peak,
        "is_weekend": False,
        "highest_liquidity": is_london_ny_overlap,
        "session_modifier": confluence_mod,
        "status": "active",
    }
