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

    with patch("monika.application.agent.monitors.process_guardian._get_heartbeat_path", return_value=hb_file), patch(
        "monika.application.agent.monitors.process_guardian._get_kill_flag_path", return_value=kill_file
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
