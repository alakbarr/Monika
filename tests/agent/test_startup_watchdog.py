import pytest
import time
from monika.application.agent.monitors.startup_watchdog import StartupWatchdog


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
    for _ in range(30):
        if deadlock_triggered:
            break
        time.sleep(0.05)
    assert deadlock_triggered is True
    assert watchdog.is_complete is False


def test_watchdog_skipped_in_child_process():
    """Verify watchdog does not arm inside multiprocessing child processes."""
    from unittest.mock import patch, MagicMock

    mock_proc = MagicMock()
    mock_proc.name = "guardian-process"

    with patch("multiprocessing.current_process", return_value=mock_proc):
        watchdog = StartupWatchdog(timeout_seconds=1)
        watchdog.start()
        assert watchdog._started is False
        assert watchdog._thread is None


def test_watchdog_skipped_with_multiprocessing_fork_arg():
    """Verify watchdog does not arm if spawned with --multiprocessing-fork in sys.argv."""
    from unittest.mock import patch

    with patch("sys.argv", ["python", "--multiprocessing-fork"]):
        watchdog = StartupWatchdog(timeout_seconds=1)
        watchdog.start()
        assert watchdog._started is False
        assert watchdog._thread is None
