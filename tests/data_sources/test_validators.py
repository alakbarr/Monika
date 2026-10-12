import pytest
from datetime import datetime, timezone, timedelta
from data_sources.validators import (
    validate_ohlcv_freshness,
    is_intraday_cache_expired,
    NoMarketDataError,
    StaleDataError,
    NonMonotonicDataError,
)


def test_validate_ohlcv_freshness_success():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    bars = [
        {"timestamp": (now - timedelta(days=2)).isoformat(), "close": 1.0800},
        {"timestamp": (now - timedelta(days=1)).isoformat(), "close": 1.0820},
        {"timestamp": now.isoformat(), "close": 1.0850},
    ]
    res = validate_ohlcv_freshness(bars, "EURUSD", reference_date=now, max_stale_days=5)
    assert len(res) == 3


def test_validate_ohlcv_empty():
    with pytest.raises(NoMarketDataError):
        validate_ohlcv_freshness([], "EURUSD")


def test_validate_ohlcv_stale():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    # Latest bar is 20 days ago
    bars = [
        {"timestamp": (now - timedelta(days=25)).isoformat(), "close": 1.0800},
        {"timestamp": (now - timedelta(days=20)).isoformat(), "close": 1.0820},
    ]
    with pytest.raises(StaleDataError) as exc:
        validate_ohlcv_freshness(bars, "EURUSD", reference_date=now, max_stale_days=5)
    assert "stale" in str(exc.value)


def test_validate_ohlcv_non_monotonic():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    bars = [
        {"timestamp": now.isoformat(), "close": 1.0850},
        {"timestamp": (now - timedelta(days=1)).isoformat(), "close": 1.0820},
    ]
    with pytest.raises(NonMonotonicDataError):
        validate_ohlcv_freshness(bars, "EURUSD", reference_date=now)


def test_intraday_cache_expired():
    now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    recent_cache = now - timedelta(seconds=300)  # 5 mins ago
    assert is_intraday_cache_expired(recent_cache, ttl_seconds=900, now=now) is False

    old_cache = now - timedelta(seconds=1200)  # 20 mins ago
    assert is_intraday_cache_expired(old_cache, ttl_seconds=900, now=now) is True
