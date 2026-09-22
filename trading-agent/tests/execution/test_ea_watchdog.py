"""
Tests for PR-16: Dual Heartbeat EA Watchdog.
Verifies EA heartbeat monitoring, staleness detection, circuit breaker trip,
auto-recovery, and HeartbeatManager integration.
"""

import asyncio
import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock

from execution.ea_bridge.heartbeat_writer import HeartbeatManager
from execution.ea_bridge.watchdog import EAWatchdog


def test_watchdog_fresh_heartbeat(tmp_path: Path):
    # Setup test common files directory
    hb_manager = HeartbeatManager(mt5_common_path=str(tmp_path))
    
    # Write fresh EA heartbeat (5s ago)
    now_ts = int(time.time()) - 5
    hb_manager.ea_heartbeat_file.write_text(str(now_ts), encoding="utf-8")

    tripped = []
    watchdog = EAWatchdog(
        heartbeat_manager=hb_manager,
        stale_threshold_seconds=120.0,
        on_trip_callback=lambda reason: tripped.append(reason),
    )

    is_healthy, stale = watchdog.check_now()
    assert is_healthy is True
    assert stale <= 10
    assert watchdog.is_alive is True
    assert len(tripped) == 0


def test_watchdog_stale_heartbeat_trips(tmp_path: Path):
    hb_manager = HeartbeatManager(mt5_common_path=str(tmp_path))
    
    # Write stale EA heartbeat (200s ago)
    now_ts = int(time.time()) - 200
    hb_manager.ea_heartbeat_file.write_text(str(now_ts), encoding="utf-8")

    tripped = []
    watchdog = EAWatchdog(
        heartbeat_manager=hb_manager,
        stale_threshold_seconds=120.0,
        on_trip_callback=lambda reason: tripped.append(reason),
    )

    is_healthy, stale = watchdog.check_now()
    assert is_healthy is False
    assert stale >= 190
    assert watchdog.is_alive is False
    assert len(tripped) == 1
    assert "stale" in tripped[0]


def test_watchdog_missing_file_trips(tmp_path: Path):
    hb_manager = HeartbeatManager(mt5_common_path=str(tmp_path))
    if hb_manager.ea_heartbeat_file.exists():
        hb_manager.ea_heartbeat_file.unlink()

    tripped = []
    watchdog = EAWatchdog(
        heartbeat_manager=hb_manager,
        stale_threshold_seconds=120.0,
        on_trip_callback=lambda reason: tripped.append(reason),
    )

    is_healthy, stale = watchdog.check_now()
    assert is_healthy is False
    assert stale == -1
    assert watchdog.is_alive is False
    assert len(tripped) == 1
    assert "missing" in tripped[0]


def test_watchdog_auto_recovery(tmp_path: Path):
    hb_manager = HeartbeatManager(mt5_common_path=str(tmp_path))
    
    # 1. Start with stale heartbeat
    now_ts = int(time.time()) - 300
    hb_manager.ea_heartbeat_file.write_text(str(now_ts), encoding="utf-8")

    recovered = []
    watchdog = EAWatchdog(
        heartbeat_manager=hb_manager,
        stale_threshold_seconds=120.0,
        on_recover_callback=lambda: recovered.append(True),
    )

    is_healthy1, _ = watchdog.check_now()
    assert is_healthy1 is False
    assert watchdog.is_alive is False

    # 2. EA writes fresh heartbeat
    fresh_ts = int(time.time())
    hb_manager.ea_heartbeat_file.write_text(str(fresh_ts), encoding="utf-8")

    is_healthy2, _ = watchdog.check_now()
    assert is_healthy2 is True
    assert watchdog.is_alive is True
    assert len(recovered) == 1


@pytest.mark.asyncio
async def test_watchdog_async_loop(tmp_path: Path):
    hb_manager = HeartbeatManager(mt5_common_path=str(tmp_path))
    hb_manager.ea_heartbeat_file.write_text(str(int(time.time())), encoding="utf-8")

    watchdog = EAWatchdog(
        heartbeat_manager=hb_manager,
        check_interval_seconds=0.1,
    )

    task = asyncio.create_task(watchdog.run_forever())
    await asyncio.sleep(0.25)
    assert watchdog.is_alive is True

    watchdog.stop()
    await task


def test_heartbeat_manager_get_watchdog_factory(tmp_path: Path):
    hb_manager = HeartbeatManager(mt5_common_path=str(tmp_path))
    wd = hb_manager.get_watchdog(check_interval_seconds=10.0)
    assert isinstance(wd, EAWatchdog)
    assert wd.check_interval == 10.0
