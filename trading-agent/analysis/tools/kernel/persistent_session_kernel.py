# ==============================================================================
# File: analysis/tools/kernel/persistent_session_kernel.py
# ==============================================================================

"""
Persistent Session Python Kernel for Programmatic Tool Calling.
Institutional-grade engine turn protection architecture.

Maintains an isolated, persistent Python subprocess per conversation/task session.
State (imports, variables, dataframes, user-defined functions) persists across
subsequent cell executions while isolating host memory and sensitive credentials.
Subprocesses are guarded by OS-level parent watchdogs on both Windows and POSIX
to guarantee clean termination without leaving dangling background processes.
"""

from __future__ import annotations

import atexit
import contextlib
import io
import json
import logging
import os
import queue
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from analysis.tools.kernel.code_execution_rpc import (
    CodeExecutionRpcServer,
    generate_monika_tools_client_code,
)
from analysis.tools.kernel.env_sanitizer import get_sanitized_environment
from analysis.tools.kernel.output_spiller import truncate_and_spill_output

logger = logging.getLogger("TradingAgent.Tools.PersistentSessionKernel")

_IS_WINDOWS = sys.platform == "win32"
_DEFAULT_TIMEOUT = 120.0
_MAX_CAPTURE_BYTES = 100_000

# Subprocess runner script template executed inside the child process
_RUNNER_CODE = '''\
import contextlib
import io
import json
import os
import sys
import threading
import traceback

_SENTINEL = os.environ["MONIKA_KERNEL_SENTINEL"]
_CAPTURE_LIMIT = 500000

GLOBALS = {"__name__": "__main__", "__builtins__": __builtins__}

def _clip(text):
    if len(text) <= _CAPTURE_LIMIT:
        return text, False
    return text[:_CAPTURE_LIMIT], True

def _start_watchdog_windows():
    raw_handle = os.environ.get("MONIKA_PARENT_HANDLE", "")
    if not raw_handle:
        return
    try:
        import ctypes
        handle = int(raw_handle)
        def _wait():
            ctypes.windll.kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
            os._exit(0)
        t = threading.Thread(target=_wait, name="monika-parent-watchdog", daemon=True)
        t.start()
    except Exception:
        pass

def _start_watchdog_posix():
    raw_fd = os.environ.get("MONIKA_PARENT_DEATH_FD", "")
    if not raw_fd:
        return
    try:
        fd = int(raw_fd)
        def _wait():
            try:
                while os.read(fd, 1):
                    pass
            except OSError:
                pass
            os._exit(0)
        t = threading.Thread(target=_wait, name="monika-parent-watchdog", daemon=True)
        t.start()
    except Exception:
        pass

if sys.platform == "win32":
    _start_watchdog_windows()
else:
    _start_watchdog_posix()

def run_cell(code):
    out_buf, err_buf = io.StringIO(), io.StringIO()
    status, trace = "ok", ""
    try:
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            compiled = compile(code, "<monika_cell>", "exec")
            exec(compiled, GLOBALS)
    except SystemExit as exc:
        status, trace = "exit", f"SystemExit: {exc.code}"
    except BaseException:
        status, trace = "error", traceback.format_exc()
        
    stdout_txt, stdout_clipped = _clip(out_buf.getvalue())
    stderr_txt, stderr_clipped = _clip(err_buf.getvalue())
    return {
        "status": status,
        "stdout": stdout_txt,
        "stderr": stderr_txt,
        "traceback": trace,
        "stdout_clipped": stdout_clipped,
        "stderr_clipped": stderr_clipped,
    }

# Main request loop
while True:
    try:
        line = sys.stdin.readline()
        if not line:
            break
        req = json.loads(line)
        if req.get("action") == "reset":
            GLOBALS.clear()
            GLOBALS.update({"__name__": "__main__", "__builtins__": __builtins__})
            payload = {"status": "ok", "stdout": "[Kernel state reset]", "stderr": "", "traceback": ""}
        else:
            payload = run_cell(req.get("code", ""))
            
        json_bytes = json.dumps(payload).encode("utf-8")
        frame_header = f"{_SENTINEL} {len(json_bytes)}\\n".encode("utf-8")
        sys.stdout.buffer.write(frame_header + json_bytes + b"\\n")
        sys.stdout.buffer.flush()
    except Exception as exc:
        err_payload = {"status": "error", "traceback": f"Runner loop error: {exc}", "stdout": "", "stderr": ""}
        json_bytes = json.dumps(err_payload).encode("utf-8")
        frame_header = f"{_SENTINEL} {len(json_bytes)}\\n".encode("utf-8")
        sys.stdout.buffer.write(frame_header + json_bytes + b"\\n")
        sys.stdout.buffer.flush()
'''


class PersistentSessionKernel:
    """
    Manages a persistent Python execution subprocess for a single session.
    """

    def __init__(
        self,
        session_id: str = "default",
        timeout_seconds: float = _DEFAULT_TIMEOUT,
        rpc_server: Optional[CodeExecutionRpcServer] = None,
        working_dir: Optional[str] = None,
    ):
        self.session_id = session_id
        self.timeout_seconds = timeout_seconds
        self.rpc_server = rpc_server
        self.sentinel = f"MKA_{secrets.token_hex(8)}"
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self.cwd = Path(working_dir) if working_dir else None
        self.proc: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.execution_count: int = 0
        self._is_alive: bool = False

    def _ensure_started(self) -> None:
        """Spawn persistent runner subprocess if not already running."""
        if self.proc and self.proc.poll() is None:
            return

        if not self.cwd:
            self._temp_dir = tempfile.TemporaryDirectory(
                prefix=f"monika_kernel_{self.session_id}_",
                ignore_cleanup_errors=True,
            )
            self.cwd = Path(self._temp_dir.name)

        # Inject monika_tools.py into session CWD if RPC server is present
        if self.rpc_server and self.rpc_server.port > 0:
            client_code = generate_monika_tools_client_code(
                port=self.rpc_server.port,
                token=self.rpc_server.rpc_token,
                allowed_tools=self.rpc_server.allowed_tools,
            )
            stub_path = self.cwd / "monika_tools.py"
            stub_path.write_text(client_code, encoding="utf-8")

        # Prepare runner script
        runner_path = self.cwd / "_runner.py"
        runner_path.write_text(_RUNNER_CODE, encoding="utf-8")

        child_env = get_sanitized_environment()
        child_env["MONIKA_KERNEL_SENTINEL"] = self.sentinel
        child_env["PYTHONUNBUFFERED"] = "1"
        child_env["PYTHONIOENCODING"] = "utf-8"

        # Setup OS watchdog handle/pipe
        pass_fds = []
        if _IS_WINDOWS:
            import ctypes
            SYNCHRONIZE = 0x00100000
            current_proc = ctypes.windll.kernel32.GetCurrentProcess()
            target_proc_handle = ctypes.wintypes.HANDLE()
            # Duplicate handle for inheritance
            ctypes.windll.kernel32.DuplicateHandle(
                current_proc,
                current_proc,
                current_proc,
                ctypes.byref(target_proc_handle),
                SYNCHRONIZE,
                True,  # bInheritHandle
                0,
            )
            child_env["MONIKA_PARENT_HANDLE"] = str(target_proc_handle.value)
        else:
            r_fd, w_fd = os.pipe()
            os.set_inheritable(r_fd, True)
            os.set_inheritable(w_fd, False)
            child_env["MONIKA_PARENT_DEATH_FD"] = str(r_fd)
            pass_fds.append(r_fd)

        cmd = [sys.executable, str(runner_path)]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(self.cwd),
            env=child_env,
            pass_fds=pass_fds if pass_fds else (),
            bufsize=0,
        )
        self._is_alive = True
        logger.debug(f"[PersistentSessionKernel] Spawned runner PID {self.proc.pid} for session {self.session_id}")

    def execute(self, code_str: str, timeout_seconds: Optional[float] = None) -> Tuple[str, bool]:
        """
        Send code cell to persistent kernel, wait for framed sentinel response.
        Returns: (formatted_output, is_success)
        """
        timeout = timeout_seconds or self.timeout_seconds
        with self.lock:
            self._ensure_started()
            self.execution_count += 1

            req_payload = {"action": "run", "code": code_str}
            req_line = json.dumps(req_payload) + "\n"

            try:
                self.proc.stdin.write(req_line.encode("utf-8"))
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                self.terminate()
                return f"Execution failed: Kernel process died before writing ({e})", False

            # Read framed response: <SENTINEL> <length>\n<json>
            try:
                response = self._read_framed_response(timeout=timeout)
            except TimeoutError:
                self.terminate()
                return f"Execution timed out after {timeout} seconds. Kernel was terminated to prevent hangs.", False
            except Exception as e:
                self.terminate()
                return f"Kernel communication error: {e}", False

            status = response.get("status", "error")
            stdout_txt = response.get("stdout", "")
            stderr_txt = response.get("stderr", "")
            traceback_txt = response.get("traceback", "")

            output_parts = []
            if stdout_txt:
                output_parts.append(stdout_txt)
            if stderr_txt:
                output_parts.append(f"[STDERR]:\n{stderr_txt}")
            if traceback_txt and status != "ok":
                output_parts.append(f"[TRACEBACK]:\n{traceback_txt}")

            full_output = "\n".join(output_parts).strip()
            if not full_output:
                full_output = "[Execution succeeded with no output]"

            # Spilling / truncation safety
            truncated_output, _ = truncate_and_spill_output(full_output, tool_name=f"ptc_{self.session_id}")
            return truncated_output, (status == "ok")

    def reset(self) -> Tuple[str, bool]:
        """Reset globals inside kernel without killing subprocess."""
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                return "Kernel was not running. Resetting.", True

            req_payload = {"action": "reset"}
            try:
                self.proc.stdin.write((json.dumps(req_payload) + "\n").encode("utf-8"))
                self.proc.stdin.flush()
                res = self._read_framed_response(timeout=5.0)
                return res.get("stdout", "Kernel reset"), True
            except Exception as e:
                self.terminate()
                return f"Reset failed, killed kernel: {e}", False

    def _read_framed_response(self, timeout: float) -> Dict[str, Any]:
        """Read sentinel frame from stdout within timeout."""
        import queue
        import threading

        result_queue: queue.Queue[Tuple[bool, Any]] = queue.Queue()

        def _reader() -> None:
            line_buf = bytearray()
            try:
                while True:
                    char = self.proc.stdout.read(1)
                    if not char:
                        result_queue.put((False, RuntimeError("Kernel process exited prematurely.")))
                        return
                    if char == b"\n":
                        line = line_buf.decode("utf-8", errors="replace").strip()
                        if line.startswith(self.sentinel):
                            parts = line.split(" ", 1)
                            if len(parts) == 2 and parts[1].isdigit():
                                length = int(parts[1])
                                json_bytes = self.proc.stdout.read(length)
                                result_queue.put((True, json.loads(json_bytes.decode("utf-8"))))
                                return
                        line_buf.clear()
                    else:
                        line_buf.extend(char)
            except Exception as e:
                result_queue.put((False, e))

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        try:
            success, res = result_queue.get(timeout=timeout)
            if success:
                return res
            raise res
        except queue.Empty:
            raise TimeoutError("Kernel response wait timeout")

    def terminate(self) -> None:
        """Kill the kernel subprocess and clean up temporary directory."""
        if self.proc:
            try:
                if self.proc.stdin:
                    try:
                        self.proc.stdin.close()
                    except Exception:
                        pass
                if self.proc.stdout:
                    try:
                        self.proc.stdout.close()
                    except Exception:
                        pass
                if self.proc.stderr:
                    try:
                        self.proc.stderr.close()
                    except Exception:
                        pass
                self.proc.kill()
                self.proc.wait(timeout=2.0)
            except Exception:
                pass
            self.proc = None
        self._is_alive = False

        if self._temp_dir:
            try:
                self._temp_dir.cleanup()
            except Exception:
                pass
            self._temp_dir = None
