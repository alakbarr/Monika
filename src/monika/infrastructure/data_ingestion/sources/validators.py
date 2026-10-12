# ==============================================================================
# File: data_sources/validators.py
# ==============================================================================

"""
Market Data & OHLCV Validation Engine.
Guarantees chronological monotonicity, prevents stale OHLCV feed leakage,
and enforces intraday candle cache TTL.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Union
import logging

logger = logging.getLogger("TradingAgent.DataSources.Validators")

MAX_OHLCV_STALE_DAYS = 5
INTRADAY_CACHE_TTL_SECONDS = 900  # 15 minutes


class NoMarketDataError(Exception):
    """Raised when market data is completely absent or empty."""
    pass


class StaleDataError(Exception):
    """Raised when market data exceeds the maximum permissible staleness."""
    pass


class NonMonotonicDataError(Exception):
    """Raised when OHLCV time series is not chronologically ordered."""
    pass


def _parse_timestamp(ts: Union[datetime, str, int, float]) -> datetime:
    """Helper to convert any timestamp format to timezone-aware UTC datetime."""
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    if isinstance(ts, (int, float)):
        # Check if milliseconds or seconds
        if ts > 1e11:
            return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    raise ValueError(f"Cannot parse timestamp: {ts}")


def validate_ohlcv_freshness(
    data: List[Dict[str, Any]],
    symbol: str,
    reference_date: Optional[datetime] = None,
    max_stale_days: int = MAX_OHLCV_STALE_DAYS,
    require_monotonic: bool = True,
) -> List[Dict[str, Any]]:
    """
    Validates:
    1. Data non-empty (raises NoMarketDataError)
    2. Chronological monotonicity (raises NonMonotonicDataError if enabled)
    3. Freshness against reference date (raises StaleDataError if staleness > max_stale_days)

    Returns the validated data.
    """
    if not data:
        raise NoMarketDataError(f"No OHLCV data available for symbol '{symbol}'")

    ref_dt = reference_date if reference_date is not None else datetime.now(timezone.utc)
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)

    prev_dt = None
    latest_dt = None

    for idx, bar in enumerate(data):
        raw_ts = bar.get("timestamp") or bar.get("time") or bar.get("date")
        if raw_ts is None:
            continue
        bar_dt = _parse_timestamp(raw_ts)

        if require_monotonic and prev_dt is not None:
            if bar_dt < prev_dt:
                raise NonMonotonicDataError(
                    f"Non-monotonic timestamps detected in {symbol} at bar {idx}: {bar_dt} < {prev_dt}"
                )
        prev_dt = bar_dt
        if latest_dt is None or bar_dt > latest_dt:
            latest_dt = bar_dt

    if latest_dt is None:
        raise NoMarketDataError(f"No valid timestamps found in OHLCV data for '{symbol}'")

    staleness_delta = ref_dt - latest_dt
    staleness_days = staleness_delta.total_seconds() / 86400.0

    if staleness_days > max_stale_days:
        raise StaleDataError(
            f"{symbol}: OHLCV data is {staleness_days:.1f} days stale (latest bar: {latest_dt.isoformat()}, "
            f"ref: {ref_dt.isoformat()}, max allowed: {max_stale_days} days)"
        )

    return data


def is_intraday_cache_expired(
    last_cached_at: Union[datetime, str, int, float],
    ttl_seconds: int = INTRADAY_CACHE_TTL_SECONDS,
    now: Optional[datetime] = None,
) -> bool:
    """
    Checks whether intraday candle cache is expired based on TTL.
    Supports datetime, ISO string, or numeric timestamp.
    """
    try:
        dt = _parse_timestamp(last_cached_at)
    except Exception:
        return True

    curr = _parse_timestamp(now) if now is not None else datetime.now(timezone.utc)
    age_seconds = (curr - dt).total_seconds()
    return age_seconds >= ttl_seconds
