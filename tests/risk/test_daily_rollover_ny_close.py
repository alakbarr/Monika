"""
Unit Tests for Daily Rollover Hour Calculation (NY Close 21:00 UTC) in RiskGate.
"""
import pytest
from datetime import datetime, timezone
from risk.risk_gate import get_trading_day_start


def test_get_trading_day_start_post_rollover():
    """When current time is 22:30 UTC and rollover is 21:00 UTC, trading day start is today at 21:00 UTC."""
    settings = {"trading": {"risk": {"daily_rollover_utc_hour": 21}}}
    now = datetime(2026, 8, 28, 22, 30, 0, tzinfo=timezone.utc)
    
    start = get_trading_day_start(settings, now)
    assert start == datetime(2026, 8, 28, 21, 0, 0, tzinfo=timezone.utc)


def test_get_trading_day_start_pre_rollover():
    """When current time is 14:00 UTC and rollover is 21:00 UTC, trading day start is yesterday at 21:00 UTC."""
    settings = {"trading": {"risk": {"daily_rollover_utc_hour": 21}}}
    now = datetime(2026, 8, 28, 14, 0, 0, tzinfo=timezone.utc)
    
    start = get_trading_day_start(settings, now)
    assert start == datetime(2026, 8, 27, 21, 0, 0, tzinfo=timezone.utc)


def test_get_trading_day_start_midnight_default():
    """When rollover is configured as 0 (midnight UTC), returns today at 00:00 UTC."""
    settings = {"trading": {"risk": {"daily_rollover_utc_hour": 0}}}
    now = datetime(2026, 8, 28, 14, 0, 0, tzinfo=timezone.utc)
    
    start = get_trading_day_start(settings, now)
    assert start == datetime(2026, 8, 28, 0, 0, 0, tzinfo=timezone.utc)


def test_get_trading_day_start_winter_est_dst():
    """When in winter (January, Standard Time EST), 17:00 NY Close corresponds to 22:00 UTC."""
    settings = {"trading": {"risk": {}}}  # Uses dynamic NY Close 17:00
    # January 15, 2026 at 23:00 UTC (after 17:00 EST / 22:00 UTC rollover)
    now_post = datetime(2026, 1, 15, 23, 0, 0, tzinfo=timezone.utc)
    start_post = get_trading_day_start(settings, now_post)
    assert start_post == datetime(2026, 1, 15, 22, 0, 0, tzinfo=timezone.utc)

    # January 15, 2026 at 15:00 UTC (before 17:00 EST / 22:00 UTC rollover)
    now_pre = datetime(2026, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
    start_pre = get_trading_day_start(settings, now_pre)
    assert start_pre == datetime(2026, 1, 14, 22, 0, 0, tzinfo=timezone.utc)
