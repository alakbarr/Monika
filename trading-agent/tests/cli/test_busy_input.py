# ==============================================================================
# File: tests/cli/test_busy_input.py
# Description: Unit Tests for BusyInputBuffer
# ==============================================================================

import pytest
from cli.busy_input import BusyInputBuffer, InputDelivery


def test_busy_input_buffer_submit_and_pop():
    """Verify steer and follow-up queuing and retrieval."""
    buf = BusyInputBuffer()
    assert buf.pending_count == 0
    assert not buf.has_pending

    # Submit steer
    buf.submit("focus on XAUUSD", InputDelivery.STEER)
    assert buf.pending_count == 1
    assert len(buf.steer_queue) == 1
    assert len(buf.followup_queue) == 0

    # Submit follow-up
    buf.submit("review open risks later", InputDelivery.FOLLOW_UP)
    assert buf.pending_count == 2
    assert len(buf.followup_queue) == 1

    # Pop steer
    steer = buf.pop_steer()
    assert steer == "focus on XAUUSD"
    assert len(buf.steer_queue) == 0
    assert buf.pop_steer() is None

    # Pop follow-up
    fu = buf.pop_followup()
    assert fu == "review open risks later"
    assert len(buf.followup_queue) == 0
    assert buf.pop_followup() is None


def test_busy_input_interrupt():
    """Interrupt message is prepended to steer queue."""
    buf = BusyInputBuffer()
    buf.submit("normal steer", InputDelivery.STEER)
    buf.submit("STOP", InputDelivery.INTERRUPT)

    assert len(buf.steer_queue) == 2
    top = buf.pop_steer()
    assert top.startswith("[INTERRUPT]")
    assert "STOP" in top


def test_busy_input_dequeue_all():
    """dequeue_all empties both queues and returns all messages."""
    buf = BusyInputBuffer()
    buf.submit("s1", InputDelivery.STEER)
    buf.submit("s2", InputDelivery.STEER)
    buf.submit("f1", InputDelivery.FOLLOW_UP)

    assert buf.pending_count == 3
    msgs = buf.dequeue_all()
    assert msgs == ["s1", "s2", "f1"]
    assert buf.pending_count == 0
    assert not buf.has_pending


def test_busy_input_status_text():
    """status_text reflects queue contents."""
    buf = BusyInputBuffer()
    assert buf.status_text == ""

    buf.submit("msg1", InputDelivery.STEER)
    assert "1 steer" in buf.status_text

    buf.submit("msg2", InputDelivery.FOLLOW_UP)
    assert "1 steer" in buf.status_text
    assert "1 queued" in buf.status_text


def test_busy_input_empty_and_whitespace():
    """Empty and whitespace strings are ignored."""
    buf = BusyInputBuffer()
    buf.submit("", InputDelivery.STEER)
    buf.submit("   ", InputDelivery.FOLLOW_UP)
    assert buf.pending_count == 0
