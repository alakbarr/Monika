# ==============================================================================
# File: tests/observability/test_dashboard_observability.py
# ==============================================================================

"""
Unit Test Suite for Stage 10:
Dashboard Observability, Ephemeral WebSocket Tickets, and Incremental LogStreamer.
"""

import asyncio
import tempfile
import time
from pathlib import Path
import pytest

from logging_observability.dashboard.ws_ticket import (
    WsTicketManager,
    get_ws_ticket_manager,
)
from logging_observability.dashboard.log_streamer import (
    LogStreamer,
    parse_log_line_level,
)


# ==============================================================================
# 1. Ephemeral Single-Use WebSocket Ticket Tests
# ==============================================================================

def test_ws_ticket_lifecycle_and_single_use():
    mgr = WsTicketManager(default_ttl=10.0)

    # 1. Create ticket
    ticket = mgr.create_ticket(user_id="trader_bob", role="admin")
    assert ticket
    assert len(ticket) > 20
    assert mgr.active_ticket_count() == 1

    # 2. Consume ticket once -> Success
    payload = mgr.validate_and_consume(ticket)
    assert payload is not None
    assert payload.user_id == "trader_bob"
    assert payload.role == "admin"

    # 3. Consume ticket second time -> Rejected (Single-use enforcement)
    payload_repeat = mgr.validate_and_consume(ticket)
    assert payload_repeat is None
    assert mgr.active_ticket_count() == 0


def test_ws_ticket_expiration():
    mgr = WsTicketManager(default_ttl=0.05)

    ticket = mgr.create_ticket(user_id="trader_alice", role="viewer")
    # Sleep past expiration
    time.sleep(0.08)

    payload = mgr.validate_and_consume(ticket)
    assert payload is None


def test_ws_ticket_invalid_token():
    mgr = WsTicketManager()
    assert mgr.validate_and_consume("completely_bogus_ticket_id") is None


# ==============================================================================
# 2. Incremental LogStreamer Tests
# ==============================================================================

def test_parse_log_line_level():
    assert parse_log_line_level("2026-09-27 00:00:00 [ERROR] MT5 connection dropped") == "ERROR"
    assert parse_log_line_level("2026-09-27 00:00:00 [WARNING] Spread widening") in ("WARNING", "WARN")
    assert parse_log_line_level("2026-09-27 00:00:00 [INFO] Heartbeat OK") == "INFO"


@pytest.mark.asyncio
async def test_log_streamer_incremental_tailing():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        log_file = Path(tmp_dir) / "agent_runtime.log"
        log_file.write_text("2026-09-27 00:00:00 [INFO] Initial startup line\n")

        streamer = LogStreamer(log_file, min_level="WARNING")
        gen = streamer.tail(poll_interval_seconds=0.04)
        streamed_lines = []

        async def _consumer():
            async for line in gen:
                streamed_lines.append(line)
                if len(streamed_lines) >= 2:
                    break

        consumer_task = asyncio.create_task(_consumer())

        # Give streamer a moment to initialize position
        await asyncio.sleep(0.06)

        # Append new lines (1 INFO should be ignored, 2 WARNING/ERROR should be emitted)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write("2026-09-27 00:00:01 [INFO] Ignored info line\n")
            f.write("2026-09-27 00:00:02 [WARNING] First warning alert\n")
            f.write("2026-09-27 00:00:03 [ERROR] Critical error alert\n")

        await asyncio.wait_for(consumer_task, timeout=1.0)
        streamer.stop()
        await gen.aclose()
        consumer_task.cancel()
        try:
            await consumer_task
        except (asyncio.CancelledError, Exception):
            pass

        assert len(streamed_lines) == 2
        assert "[WARNING]" in streamed_lines[0]
        assert "[ERROR]" in streamed_lines[1]
