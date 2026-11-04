"""
Unit test suite for TickCoalescer primitive.
"""

from monika.core.primitives.tick_coalescer import TickCoalescer, get_tick_coalescer


def test_tick_coalescer_debounce():
    coalescer = TickCoalescer(debounce_seconds=0.25)

    # First tick should emit
    assert coalescer.should_emit("EURUSD", now_mono=100.0) is True

    # Immediate second tick within debounce window should NOT emit
    assert coalescer.should_emit("EURUSD", now_mono=100.1) is False
    assert coalescer.should_emit("EURUSD", now_mono=100.24) is False

    # Tick after debounce window should emit
    assert coalescer.should_emit("EURUSD", now_mono=100.26) is True

    # Different symbol should emit independently
    assert coalescer.should_emit("XAUUSD", now_mono=100.27) is True
    assert coalescer.should_emit("XAUUSD", now_mono=100.30) is False


def test_tick_coalescer_reset():
    coalescer = TickCoalescer(debounce_seconds=1.0)
    assert coalescer.should_emit("BTCUSD", now_mono=10.0) is True
    assert coalescer.should_emit("BTCUSD", now_mono=10.5) is False

    coalescer.reset("BTCUSD")
    assert coalescer.should_emit("BTCUSD", now_mono=10.6) is True


def test_tick_coalescer_singleton():
    c1 = get_tick_coalescer()
    c2 = get_tick_coalescer()
    assert c1 is c2
