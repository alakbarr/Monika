"""Tests for BrokerTimeResolver and canonical bar grid normalization."""

from datetime import datetime, timezone
import pytest

from monika.infrastructure.brokers.mt5.broker_time import (
    BrokerTimeResolver,
    get_broker_utc_offset_seconds,
    to_canonical_timestamp,
)


def test_get_configured_offset_hours_valid():
    settings = {"trading": {"mt5": {"broker_utc_offset_hours": 3}}}
    offset = BrokerTimeResolver.get_configured_offset_hours(settings)
    assert offset == 3.0


def test_get_configured_offset_hours_missing_fails_closed(monkeypatch):
    monkeypatch.setattr("monika.core.config.settings.load_settings", lambda: {})
    settings = {"trading": {"mt5": {}}}
    with pytest.raises(ValueError, match="CRITICAL: 'trading.mt5.broker_utc_offset_hours' is not configured"):
        BrokerTimeResolver.get_configured_offset_hours(settings)


def test_get_configured_offset_hours_invalid_type():
    settings = {"trading": {"mt5": {"broker_utc_offset_hours": "invalid_offset"}}}
    with pytest.raises(ValueError, match="must be numeric"):
        BrokerTimeResolver.get_configured_offset_hours(settings)


def test_resolve_offset_seconds():
    settings = {"trading": {"mt5": {"broker_utc_offset_hours": 3.0}}}
    sec = BrokerTimeResolver.resolve_offset_seconds(settings, force_refresh=True)
    assert sec == 10800
    assert get_broker_utc_offset_seconds(settings) == 10800


def test_canonical_timestamp_m15_and_h1():
    # 2026-10-20 14:23:45 UTC
    dt = datetime(2026, 10, 20, 14, 23, 45, tzinfo=timezone.utc)

    # M15 floored to 14:15:00
    canon_m15 = to_canonical_timestamp(dt, "M15")
    assert canon_m15 == datetime(2026, 10, 20, 14, 15, 0, tzinfo=timezone.utc)

    # H1 floored to 14:00:00
    canon_h1 = to_canonical_timestamp(dt, "H1")
    assert canon_h1 == datetime(2026, 10, 20, 14, 0, 0, tzinfo=timezone.utc)


def test_canonical_timestamp_h4_with_broker_offset():
    # With UTC+3 broker (FBS):
    # UTC 13:30:00 -> Broker time 16:30:00
    # Broker H4 candle opens at 16:00:00 broker time
    # 16:00:00 broker time - 3h = 13:00:00 UTC
    dt = datetime(2026, 10, 20, 13, 30, 0, tzinfo=timezone.utc)
    canon_h4 = to_canonical_timestamp(dt, "H4", offset_seconds=10800)
    assert canon_h4 == datetime(2026, 10, 20, 13, 0, 0, tzinfo=timezone.utc)

    # UTC 14:15:00 -> Broker time 17:15:00
    # Belongs to the same 16:00:00 broker candle -> canonical UTC is still 13:00:00
    dt2 = datetime(2026, 10, 20, 14, 15, 0, tzinfo=timezone.utc)
    canon_h4_2 = to_canonical_timestamp(dt2, "H4", offset_seconds=10800)
    assert canon_h4_2 == datetime(2026, 10, 20, 13, 0, 0, tzinfo=timezone.utc)


def test_canonical_timestamp_d1():
    # Broker UTC+3: UTC 2026-10-20 22:30:00 is Broker 2026-10-21 01:30:00
    # D1 canonical date should be 2026-10-21 00:00:00 UTC
    dt = datetime(2026, 10, 20, 22, 30, 0, tzinfo=timezone.utc)
    canon_d1 = to_canonical_timestamp(dt, "D1", offset_seconds=10800)
    assert canon_d1 == datetime(2026, 10, 21, 0, 0, 0, tzinfo=timezone.utc)


def test_canonical_timestamp_w1():
    # Broker UTC+3: Thursday 2026-10-22 10:00:00 -> Monday 2026-10-19 00:00:00 UTC
    dt = datetime(2026, 10, 22, 10, 0, 0, tzinfo=timezone.utc)
    canon_w1 = to_canonical_timestamp(dt, "W1", offset_seconds=10800)
    assert canon_w1 == datetime(2026, 10, 19, 0, 0, 0, tzinfo=timezone.utc)
