import pytest
import time
from agent.monitors.startup_watchdog import StartupWatchdog


def test_watchdog_disarm_on_complete():
    """Verify watchdog disarms cleanly without triggering deadlock."""
    deadlock_triggered = False

    def on_deadlock():
        nonlocal deadlock_triggered
        deadlock_triggered = True

    watchdog = StartupWatchdog(timeout_seconds=1, on_deadlock=on_deadlock)
    watchdog.start()
    assert watchdog.is_complete is False

    # Mark complete immediately
    watchdog.mark_complete()
    assert watchdog.is_complete is True

    # Wait past timeout to ensure deadlock was NOT called
    time.sleep(1.2)
    assert deadlock_triggered is False


def test_watchdog_triggers_on_timeout():
    """Verify watchdog invokes on_deadlock callback when timeout expires."""
    deadlock_triggered = False

    def on_deadlock():
        nonlocal deadlock_triggered
        deadlock_triggered = True

    watchdog = StartupWatchdog(timeout_seconds=0.1, on_deadlock=on_deadlock)
    watchdog.start()

    # Don't mark complete — wait for timeout
    time.sleep(0.25)
    assert deadlock_triggered is True
    assert watchdog.is_complete is False
