import pytest
from analysis.tools.loop_guard import ToolLoopGuard, canonical_tool_hash


def test_canonical_tool_hash_argument_invariance():
    # Order of dictionary keys shouldn't affect hash
    args1 = {"symbol": "EURUSD", "timeframe": "M15", "count": 100}
    args2 = {"count": 100, "symbol": "EURUSD", "timeframe": "M15"}
    h1 = canonical_tool_hash("get_candles", args1)
    h2 = canonical_tool_hash("get_candles", args2)
    assert h1 == h2

    # Different arguments produce different hashes
    args3 = {"symbol": "XAUUSD", "timeframe": "M15", "count": 100}
    h3 = canonical_tool_hash("get_candles", args3)
    assert h1 != h3


def test_tool_loop_guard_escalation():
    guard = ToolLoopGuard()
    tool_name = "get_candles"
    args = {"symbol": "EURUSD", "timeframe": "H1"}

    # Calls 1-2: Normal
    stop, msg = guard.check(tool_name, args)
    assert not stop and msg is None

    stop, msg = guard.check(tool_name, args)
    assert not stop and msg is None

    # Call 3: Gentle Loop Advisory
    stop, msg = guard.check(tool_name, args)
    assert not stop
    assert msg is not None
    assert "called 3 times consecutively" in msg

    # Call 4: Still below insistent threshold
    stop, msg = guard.check(tool_name, args)
    assert not stop and msg is None

    # Call 5: Insistent Warning
    stop, msg = guard.check(tool_name, args)
    assert not stop
    assert msg is not None
    assert "5 consecutive times" in msg

    # Calls 6-7: Normal
    guard.check(tool_name, args)
    guard.check(tool_name, args)

    # Call 8: Force Stop
    stop, msg = guard.check(tool_name, args)
    assert stop is True
    assert "[FORCE STOP]" in msg


def test_tool_loop_guard_reset_on_different_tool():
    guard = ToolLoopGuard()
    # 2 calls on tool A
    guard.check("tool_a", {"x": 1})
    guard.check("tool_a", {"x": 1})

    # Call on tool B resets tool A
    guard.check("tool_b", {"y": 2})

    # Now tool A starts fresh at 1
    stop, msg = guard.check("tool_a", {"x": 1})
    assert not stop and msg is None
