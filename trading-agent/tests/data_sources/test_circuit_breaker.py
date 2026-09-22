import time
import pytest
from unittest.mock import patch, MagicMock

from data_sources.circuit_breaker import (
    DataFeedCircuitBreaker,
    FeedStatus,
    get_data_feed_circuit_breaker,
    record_feed_heartbeat,
)


def test_feed_status_properties():
    now = time.time()
    feed = FeedStatus(name="mt5_ticks", last_heartbeat=now - 50, ttl_seconds=120.0)
    assert not feed.is_stale
    assert 45 < feed.age_seconds < 55

    feed_stale = FeedStatus(name="mt5_ticks", last_heartbeat=now - 200, ttl_seconds=120.0)
    assert feed_stale.is_stale

    feed_empty = FeedStatus(name="unknown", last_heartbeat=None)
    assert feed_empty.is_stale
    assert feed_empty.age_seconds == float("inf")


def test_record_heartbeat_and_check_feed():
    breaker = DataFeedCircuitBreaker()
    feed_name = "economic_calendar"

    # Initially empty heartbeat
    check = breaker.check_feed(feed_name)
    assert check["registered"] is True
    assert check["stale"] is True

    # Record heartbeat
    now = time.time()
    breaker.record_feed_heartbeat(feed_name, timestamp=now, metadata={"events": 5})

    check_after = breaker.check_feed(feed_name)
    assert check_after["stale"] is False
    assert check_after["age_seconds"] < 2.0
    assert not breaker.is_feed_stale(feed_name)


def test_circuit_breaker_manual_trip_and_reset():
    breaker = DataFeedCircuitBreaker()
    feed_name = "fred"

    with patch.object(breaker, "_publish_event") as mock_pub:
        # Trip
        tripped = breaker.trip(feed_name, reason="FRED API 500 internal server error", cooldown_seconds=600)
        assert tripped is True
        assert breaker.is_tripped() is True
        assert breaker.is_tripped(feed_name) is True
        mock_pub.assert_called_once()
        assert mock_pub.call_args[1]["is_active"] is True

        tripped_dict = breaker.get_tripped_feeds()
        assert feed_name in tripped_dict
        assert "FRED API 500" in tripped_dict[feed_name]["reason"]

        # Reset single feed
        mock_pub.reset_mock()
        reset_res = breaker.reset(feed_name, reason="FRED API recovered")
        assert reset_res is True
        assert breaker.is_tripped(feed_name) is False
        assert breaker.is_tripped() is False
        mock_pub.assert_called_once()
        assert mock_pub.call_args[1]["is_active"] is False


def test_evaluate_all_feeds_auto_trip():
    breaker = DataFeedCircuitBreaker()
    now = time.time()

    # mt5_ticks: TTL 120s, set heartbeat 300s ago
    breaker.record_feed_heartbeat("mt5_ticks", timestamp=now - 300)
    # fred: TTL 172800s, set heartbeat 1000s ago
    breaker.record_feed_heartbeat("fred", timestamp=now - 1000)

    report = breaker.evaluate_all_feeds(auto_trip=True, now=now)
    assert report["all_healthy"] is False
    assert "mt5_ticks" in report["stale_critical"]
    assert "fred" not in report["stale_critical"]
    assert breaker.is_tripped("mt5_ticks") is True
    assert breaker.is_tripped() is True


def test_auto_reset_on_fresh_data():
    breaker = DataFeedCircuitBreaker()
    now = time.time()

    # Manually trip stale feed
    breaker.trip("finnhub", reason="Stale feed")
    assert breaker.is_tripped("finnhub") is True

    # Record fresh heartbeat
    breaker.record_feed_heartbeat("finnhub", timestamp=now)
    assert breaker.is_tripped("finnhub") is False


def test_health_report_structure():
    breaker = DataFeedCircuitBreaker()
    report = breaker.get_health_report()
    assert "is_tripped" in report
    assert "tripped_feeds" in report
    assert "feeds" in report
    assert "mt5_ticks" in report["feeds"]
    assert "fred" in report["feeds"]
    assert "finnhub" in report["feeds"]


def test_global_singleton_convenience():
    breaker1 = get_data_feed_circuit_breaker()
    breaker2 = get_data_feed_circuit_breaker()
    assert breaker1 is breaker2

    record_feed_heartbeat("mt5_ticks")
    assert not breaker1.is_feed_stale("mt5_ticks")
