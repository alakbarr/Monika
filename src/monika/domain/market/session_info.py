"""Market session tracking and timing rules utility."""
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import utils.clock as clock


def get_current_market_session(dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Mengembalikan sesi pasar yang sedang aktif, status overlap London-NY,
    dan modifier confluence sesuai spesifikasi skills/trading/session_timing_rules.md.
    """
    if dt is None:
        dt = clock.now()
    hour = dt.hour
    minute = dt.minute
    time_val = hour + minute / 60.0

    active_sessions = []
    if 0 <= time_val < 8:
        active_sessions.append("Tokyo")
    if 8 <= time_val < 16:
        active_sessions.append("London")
    if 13 <= time_val < 21:
        active_sessions.append("New York")
    if 21 <= time_val <= 24:
        active_sessions.append("Off-Peak")

    is_london_ny_overlap = (13 <= time_val < 16)
    is_off_peak = (21 <= time_val <= 24)
    confluence_mod = 1 if is_london_ny_overlap else (-2 if is_off_peak else 0)

    return {
        "current_time_utc": dt.strftime("%H:%M:%S"),
        "active_sessions": active_sessions,
        "is_london_ny_overlap": is_london_ny_overlap,
        "is_off_peak": is_off_peak,
        "session_modifier": confluence_mod,
        "status": "active"
    }
