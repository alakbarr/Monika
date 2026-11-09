# ==============================================================================
# File: tests/test_process_guardian.py
# Description: Unit tests for Multi-Process Guardian and Emergency Kill Supervisor
# ==============================================================================

import io
import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

from monika.application.agent.monitors.process_guardian import (
    GuardianRequestHandler,
    GuardianSupervisor,
    _get_heartbeat_path,
    _get_kill_flag_path,
    clear_stale_heartbeat_kill_flag,
    trigger_emergency_kill,
)


class MockSocket:
    """Mock socket for BaseHTTPRequestHandler request/response testing."""

    def __init__(self, request_bytes: bytes):
        self.rfile = io.BytesIO(request_bytes)
        self.wfile = io.BytesIO()

    def makefile(self, mode: str, *args, **kwargs):
        if "r" in mode:
            return self.rfile
        return self.wfile

    def sendall(self, data: bytes):
        self.wfile.write(data)


def test_trigger_emergency_kill(tmp_path: Path):
    with patch(
        "monika.application.agent.monitors.process_guardian._get_kill_flag_path",
        return_value=tmp_path / "kill_switch.flag",
    ):
        result = trigger_emergency_kill(source="UnitTest")
        assert result is True

        flag_file = tmp_path / "kill_switch.flag"
        assert flag_file.exists()
        payload = json.loads(flag_file.read_text(encoding="utf-8"))
        assert payload["source"] == "UnitTest"
        assert payload["active"] is True
        assert isinstance(payload["timestamp"], (int, float))


def test_guardian_request_handler_status(tmp_path: Path):
    hb_file = tmp_path / "monika_main.hb"
    hb_file.write_text(str(time.time()), encoding="utf-8")
    kill_file = tmp_path / "kill_switch.flag"

    with (
        patch("monika.application.agent.monitors.process_guardian._get_heartbeat_path", return_value=hb_file),
        patch("monika.application.agent.monitors.process_guardian._get_kill_flag_path", return_value=kill_file),
    ):
        mock_socket = MockSocket(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")

        GuardianRequestHandler.primary_pid = os.getpid()
        _ = GuardianRequestHandler(mock_socket, ("127.0.0.1", 12345), None)

        output = mock_socket.wfile.getvalue().decode("utf-8")
        assert "200 OK" in output
        assert '"status": "healthy"' in output
        assert '"primary_alive": true' in output


def test_guardian_request_handler_kill(tmp_path: Path):
    kill_file = tmp_path / "kill_switch.flag"

    with patch("monika.application.agent.monitors.process_guardian._get_kill_flag_path", return_value=kill_file):
        mock_socket = MockSocket(b"POST /kill HTTP/1.1\r\nHost: localhost\r\n\r\n")

        GuardianRequestHandler.primary_pid = os.getpid()
        _ = GuardianRequestHandler(mock_socket, ("127.0.0.1", 12345), None)

        output = mock_socket.wfile.getvalue().decode("utf-8")
        assert "200 OK" in output
        assert '"status": "killed"' in output
        assert kill_file.exists()


def test_guardian_request_handler_shutdown():
    shutdown_ev = threading.Event()
    GuardianRequestHandler.shutdown_flag = shutdown_ev

    mock_socket = MockSocket(b"POST /shutdown HTTP/1.1\r\nHost: localhost\r\n\r\n")
    _ = GuardianRequestHandler(mock_socket, ("127.0.0.1", 12345), None)

    output = mock_socket.wfile.getvalue().decode("utf-8")
    assert "200 OK" in output
    assert '"status": "shutting_down"' in output
    assert shutdown_ev.is_set()


def test_guardian_request_handler_not_found():
    mock_socket = MockSocket(b"GET /unknown_route HTTP/1.1\r\nHost: localhost\r\n\r\n")
    _ = GuardianRequestHandler(mock_socket, ("127.0.0.1", 12345), None)

    output = mock_socket.wfile.getvalue().decode("utf-8")
    assert "404 Not Found" in output


def test_guardian_supervisor_lifecycle(tmp_path: Path):
    hb_file = tmp_path / "monika_main.hb"
    with patch("monika.application.agent.monitors.process_guardian._get_heartbeat_path", return_value=hb_file):
        supervisor = GuardianSupervisor(port=9099)
        assert supervisor.port == 9099
        assert not supervisor._running

        supervisor.start()
        assert supervisor._running
        assert hb_file.exists()

        # Stop cleans up heartbeat file
        supervisor.stop()
        assert not supervisor._running
        assert not hb_file.exists()


def test_run_guardian_loop_catches_keyboard_interrupt():
    """Verify that _run_guardian_loop catches KeyboardInterrupt cleanly without propagating it, and closes the server."""
    from unittest.mock import MagicMock, patch
    from monika.application.agent.monitors.process_guardian import _run_guardian_loop

    mock_server = MagicMock()
    mock_stop_event = MagicMock()
    mock_stop_event.is_set.side_effect = [False, False]

    with (
        patch("http.server.ThreadingHTTPServer", return_value=mock_server),
        patch("time.sleep", side_effect=KeyboardInterrupt()),
    ):
        # Must not raise KeyboardInterrupt
        _run_guardian_loop(primary_pid=1234, port=9099, stop_event=mock_stop_event)

        # Verify server was cleanly shut down and closed in finally
        mock_server.shutdown.assert_called_once()
        mock_server.server_close.assert_called_once()


def test_guardian_supervisor_threshold_resolution():
    """Verify GuardianSupervisor correctly resolves threshold from default, settings, and env vars."""
    # 1. Default threshold is 240.0
    supervisor_default = GuardianSupervisor()
    assert supervisor_default.heartbeat_stale_threshold_seconds == 240.0

    # 2. From settings dict
    supervisor_settings = GuardianSupervisor(settings={"guardian": {"heartbeat_stale_threshold_seconds": 180.0}})
    assert supervisor_settings.heartbeat_stale_threshold_seconds == 180.0

    # 3. From system.guardian
    supervisor_sys = GuardianSupervisor(settings={"system": {"guardian": {"heartbeat_stale_threshold_seconds": 300.0}}})
    assert supervisor_sys.heartbeat_stale_threshold_seconds == 300.0

    # 4. From environment variable
    with patch.dict(os.environ, {"GUARDIAN_HEARTBEAT_TIMEOUT_SECONDS": "150.0"}):
        supervisor_env = GuardianSupervisor()
        assert supervisor_env.heartbeat_stale_threshold_seconds == 150.0


def test_ab_testing_heartbeat_staleness_condition_a_vs_condition_b(tmp_path: Path):
    """
    A/B Testing:
    Condition A (Old Baseline - threshold 60s):
      At 70s lag (scraping duration on battery), Guardian trips emergency kill switch and terminates primary PID.
    Condition B (Hardened - threshold 240s):
      At 70s and 90s lag, Guardian remains healthy, does NOT trip kill switch, and allows process to continue.
    Condition C (Fail-closed Safety - threshold 240s):
      At 250s lag (true stall), Guardian trips emergency kill switch and terminates primary PID.
    """
    from unittest.mock import MagicMock
    from monika.application.agent.monitors.process_guardian import _run_guardian_loop

    hb_file = tmp_path / "monika_main.hb"
    kill_file = tmp_path / "kill_switch.flag"

    mock_server = MagicMock()
    mock_proc = MagicMock()

    # --- Condition A: Threshold = 60.0s, Age = 70.0s ---
    hb_file.write_text(str(time.time() - 70.0), encoding="utf-8")
    stop_event_a = MagicMock()
    # Let loop run 1 cycle then stop
    stop_event_a.is_set.side_effect = [False, True]

    with (
        patch("http.server.ThreadingHTTPServer", return_value=mock_server),
        patch("monika.application.agent.monitors.process_guardian._get_heartbeat_path", return_value=hb_file),
        patch("monika.application.agent.monitors.process_guardian._get_kill_flag_path", return_value=kill_file),
        patch("psutil.pid_exists", return_value=True),
        patch("psutil.Process", return_value=mock_proc),
        patch("time.sleep", return_value=None),
    ):
        _run_guardian_loop(port=9099, primary_pid=9999, stop_event=stop_event_a, stale_threshold=60.0)

        # In Condition A, emergency kill flag must be written and proc terminated
        assert kill_file.exists()
        payload = json.loads(kill_file.read_text(encoding="utf-8"))
        assert "HeartbeatStale" in payload["source"]
        mock_proc.terminate.assert_called_once()

    # Clean up for Condition B
    kill_file.unlink()
    mock_proc.reset_mock()

    # --- Condition B: Threshold = 240.0s, Age = 70.0s & 90.0s ---
    hb_file.write_text(str(time.time() - 90.0), encoding="utf-8")
    stop_event_b = MagicMock()
    stop_event_b.is_set.side_effect = [False, True]

    with (
        patch("http.server.ThreadingHTTPServer", return_value=mock_server),
        patch("monika.application.agent.monitors.process_guardian._get_heartbeat_path", return_value=hb_file),
        patch("monika.application.agent.monitors.process_guardian._get_kill_flag_path", return_value=kill_file),
        patch("psutil.pid_exists", return_value=True),
        patch("psutil.Process", return_value=mock_proc),
        patch("time.sleep", return_value=None),
    ):
        _run_guardian_loop(port=9099, primary_pid=9999, stop_event=stop_event_b, stale_threshold=240.0)

        # In Condition B, 90s delay is well within 240s: NO kill flag, NO termination
        assert not kill_file.exists()
        mock_proc.terminate.assert_not_called()

    # --- Condition C: Threshold = 240.0s, Age = 250.0s (True freeze) ---
    hb_file.write_text(str(time.time() - 250.0), encoding="utf-8")
    stop_event_c = MagicMock()
    stop_event_c.is_set.side_effect = [False, True]

    with (
        patch("http.server.ThreadingHTTPServer", return_value=mock_server),
        patch("monika.application.agent.monitors.process_guardian._get_heartbeat_path", return_value=hb_file),
        patch("monika.application.agent.monitors.process_guardian._get_kill_flag_path", return_value=kill_file),
        patch("psutil.pid_exists", return_value=True),
        patch("psutil.Process", return_value=mock_proc),
        patch("time.sleep", return_value=None),
    ):
        _run_guardian_loop(port=9099, primary_pid=9999, stop_event=stop_event_c, stale_threshold=240.0)

        # In Condition C, genuine freeze > 240s triggers emergency kill switch
        assert kill_file.exists()
        mock_proc.terminate.assert_called_once()


def test_clear_stale_heartbeat_kill_flag_success(tmp_path: Path):
    """Verify that clear_stale_heartbeat_kill_flag clears and archives flags from process hangs."""
    flag_file = tmp_path / "kill_switch.flag"
    flag_file.write_text(
        json.dumps(
            {
                "source": "HeartbeatStale_68s",
                "timestamp": time.time(),
                "active": True,
            }
        ),
        encoding="utf-8",
    )

    with patch("monika.application.agent.monitors.process_guardian._get_data_dir", return_value=tmp_path):
        res = clear_stale_heartbeat_kill_flag(flag_file)
        assert res is True
        assert not flag_file.exists()

        archive_file = tmp_path / "guardian_restart.json"
        assert archive_file.exists()
        data = json.loads(archive_file.read_text(encoding="utf-8"))
        assert data["source"] == "HeartbeatStale_68s"
        assert data["original_payload"]["active"] is True


def test_clear_stale_heartbeat_kill_flag_preserves_financial_kill_flags(tmp_path: Path):
    """Verify that financial/manual kill switch flags are strictly preserved (fail-closed)."""
    financial_sources = ["DrawdownMonitor", "MarginMonitor", "Manual", "DashboardAPI"]
    for src in financial_sources:
        flag_file = tmp_path / f"kill_{src}.flag"
        flag_file.write_text(
            json.dumps({"source": src, "timestamp": time.time(), "active": True}),
            encoding="utf-8",
        )
        res = clear_stale_heartbeat_kill_flag(flag_file)
        assert res is False
        assert flag_file.exists(), f"Flag for source {src} must NOT be removed"


def test_clear_stale_heartbeat_kill_flag_preserves_corrupted_flag(tmp_path: Path):
    """Verify unparseable kill switch flag is kept fail-closed."""
    flag_file = tmp_path / "kill_corrupt.flag"
    flag_file.write_text("1", encoding="utf-8")  # legacy plain-text or corrupt
    res = clear_stale_heartbeat_kill_flag(flag_file)
    assert res is False
    assert flag_file.exists()


def test_clear_stale_heartbeat_kill_flag_nonexistent(tmp_path: Path):
    flag_file = tmp_path / "nonexistent.flag"
    assert clear_stale_heartbeat_kill_flag(flag_file) is False


def test_guardian_supervisor_heals_stale_flag_on_start(tmp_path: Path):
    """Verify GuardianSupervisor.start() heals stale HeartbeatStale flags before loops begin."""
    hb_file = tmp_path / "monika_main.hb"
    kill_file = tmp_path / "kill_switch.flag"
    kill_file.write_text(
        json.dumps({"source": "HeartbeatStale_120s", "timestamp": time.time(), "active": True}),
        encoding="utf-8",
    )

    with (
        patch("monika.application.agent.monitors.process_guardian._get_heartbeat_path", return_value=hb_file),
        patch("monika.application.agent.monitors.process_guardian._get_kill_flag_path", return_value=kill_file),
        patch("monika.application.agent.monitors.process_guardian._get_data_dir", return_value=tmp_path),
    ):
        supervisor = GuardianSupervisor(port=9099)
        supervisor.start()
        try:
            assert supervisor._running
            assert not kill_file.exists()
            assert (tmp_path / "guardian_restart.json").exists()
        finally:
            supervisor.stop()


def test_guardian_process_sleep_resume_detection(tmp_path: Path):
    """Verify _run_guardian_loop detects system sleep/resume and grants grace period without killing."""
    from monika.application.agent.monitors.process_guardian import _run_guardian_loop

    hb_file = tmp_path / "monika_main.hb"
    # Heartbeat from 2500 seconds ago (simulating 41.5 min sleep)
    initial_time = 1000000.0
    hb_file.write_text(str(initial_time), encoding="utf-8")

    stop_event = threading.Event()
    times = [
        initial_time,  # entry before sleep
        initial_time + 2500.0,  # after waking up (slept 2500s)
        initial_time + 2500.0,  # now in check
        initial_time + 2501.0,  # next iteration
        initial_time + 2501.0,
    ]

    def mock_time():
        if times:
            return times.pop(0)
        return initial_time + 3000.0

    call_count = 0

    def mock_sleep(_duration):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            stop_event.set()

    with (
        patch("monika.application.agent.monitors.process_guardian._get_heartbeat_path", return_value=hb_file),
        patch("monika.application.agent.monitors.process_guardian.trigger_emergency_kill") as mock_kill,
        patch("time.time", side_effect=mock_time),
        patch("time.sleep", side_effect=mock_sleep),
        patch("http.server.ThreadingHTTPServer"),
    ):
        _run_guardian_loop(port=9098, primary_pid=12345, stop_event=stop_event, stale_threshold=240.0)

        # Emergency kill MUST NOT be triggered because system sleep was detected
        assert not mock_kill.called
        # Heartbeat file was re-stamped with wake time
        new_hb = float(hb_file.read_text(encoding="utf-8").strip())
        assert new_hb >= initial_time + 2400.0
