"""
Programmatic Tool Calling (PTC) Handler — Subprocess Sandbox.

LLM writes Python script → executed in subprocess → tools accessed via JSON-RPC
over localhost TCP → stdout returned as single tool result.

Zero LLM token cost for intermediate iterations.
"""
import asyncio
import json
import logging
import tempfile
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("TradingAgent.PTC")

PTC_TIMEOUT_SECONDS = 120
PTC_MAX_OUTPUT_BYTES = 100_000  # 100KB max stdout


class PTCHandler:
    """Execute agent-generated Python code in subprocess with tool RPC access."""

    def __init__(self, tool_executor: Any, settings: Optional[dict] = None):
        self.tool_executor = tool_executor
        self.settings = settings or {}

    @staticmethod
    def _validate_code_ast(code: str) -> tuple[bool, str]:
        """
        Statically inspects Python code using AST to block malicious modules and dangerous calls.
        """
        import ast

        FORBIDDEN_MODULES = {
            "subprocess", "ctypes", "shutil", "pty",
            "multiprocessing", "threading", "signal", "webbrowser",
            "winreg", "_winapi",
        }
        FORBIDDEN_CALLS = {"eval", "exec", "__import__", "compile"}

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod_root = alias.name.split(".")[0].lower()
                    if mod_root in FORBIDDEN_MODULES:
                        return False, f"Import of restricted module '{mod_root}' is prohibited"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    mod_root = node.module.split(".")[0].lower()
                    if mod_root in FORBIDDEN_MODULES:
                        return False, f"Import from restricted module '{mod_root}' is prohibited"
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in FORBIDDEN_CALLS:
                        return False, f"Call to dangerous built-in '{node.func.id}' is prohibited"

        return True, ""

    async def execute(self, code: str, allowed_tools: Optional[list] = None) -> dict:
        """
        Run Python code in isolated subprocess.

        The subprocess gets a `tools` namespace with all registered tool functions.
        Tools are called via JSON-RPC over a localhost TCP socket.

        Returns:
            {"status": "success"|"error", "stdout": str, "stderr": str,
             "tool_calls_made": int, "tokens_saved_estimate": int}
        """
        # 0. AST Static Security Inspection
        is_safe, sec_err = self._validate_code_ast(code)
        if not is_safe:
            logger.warning(f"PTC code execution rejected by AST sandbox: {sec_err}")
            return {
                "status": "error",
                "stdout": "",
                "stderr": f"SecurityViolation: {sec_err}",
                "tool_calls_made": 0,
                "tokens_saved_estimate": 0,
            }

        # 1. Start RPC server for tool access
        rpc_server, rpc_port = await self._start_tool_rpc_server(allowed_tools)

        try:
            # 2. Write script to temp file with tool bridge preamble
            script_content = self._build_sandboxed_script(code, rpc_port)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(script_content)
                script_path = f.name

            try:
                # 3. Execute in subprocess (using to_thread for cross-platform Selector/Proactor compatibility)
                base_dir = str(Path(__file__).resolve().parent.parent.parent.parent)
                # P0-11: Subprocess Env Sanitization - whitelist safe system env vars only
                safe_keys = {
                    "PATH",
                    "SYSTEMROOT",
                    "SYSTEMDRIVE",
                    "WINDIR",
                    "COMSPEC",
                    "PATHEXT",
                    "TEMP",
                    "TMP",
                    "TMPDIR",
                    "PYTHONPATH",
                    "PYTHONUNBUFFERED",
                    "PYTHONHOME",
                    "LANG",
                    "LC_ALL",
                }
                env = {k: v for k, v in os.environ.items() if k.upper() in safe_keys}
                env["PYTHONPATH"] = base_dir
                env["PYTHONUNBUFFERED"] = "1"

                def _run_proc():
                    import subprocess
                    p = subprocess.Popen(
                        [sys.executable, script_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env,
                    )
                    try:
                        out, err = p.communicate(timeout=PTC_TIMEOUT_SECONDS)
                        return p.returncode, out, err, False
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait()
                        return -1, b"", b"", True

                returncode, stdout_bytes, stderr_bytes, timed_out = await asyncio.to_thread(_run_proc)

                if timed_out:
                    return {
                        "status": "error",
                        "error": f"Script execution timed out after {PTC_TIMEOUT_SECONDS}s",
                        "stdout": "",
                        "stderr": "",
                        "tool_calls_made": rpc_server.call_count,
                    }

                stdout = stdout_bytes.decode("utf-8", errors="replace")[:PTC_MAX_OUTPUT_BYTES]
                stderr = stderr_bytes.decode("utf-8", errors="replace")[:10000]


                if returncode != 0:
                    error_lines = [l for l in stderr.strip().split("\n") if l.strip()]
                    last_error = error_lines[-1] if error_lines else f"Process exited with code {returncode}"
                    return {

                        "status": "error",
                        "error": last_error,
                        "stdout": stdout,
                        "stderr": stderr[-2000:],
                        "tool_calls_made": rpc_server.call_count,
                    }

                return {
                    "status": "success",
                    "stdout": stdout,
                    "tool_calls_made": rpc_server.call_count,
                    "tokens_saved_estimate": rpc_server.call_count * 800,
                }
            finally:
                if os.path.exists(script_path):
                    try:
                        os.unlink(script_path)
                    except Exception:
                        pass
        finally:
            rpc_server.close()
            await rpc_server.wait_closed()

    def _build_sandboxed_script(self, user_code: str, rpc_port: int) -> str:
        """Build script with tool bridge preamble."""
        return f'''import json, sys, socket

class _ToolBridge:
    """RPC bridge to parent agent's tool executor."""
    def __init__(self, port):
        self._port = port

    def _send_request(self, name, kwargs):
        sock = socket.create_connection(("127.0.0.1", self._port), timeout=60)
        try:
            request = json.dumps({{"tool": name, "args": kwargs}}) + "\\n"
            sock.sendall(request.encode("utf-8"))
            response = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response += chunk
            return json.loads(response.decode("utf-8"))
        finally:
            sock.close()

    def call_tool(self, tool_name, **kwargs):
        return self._send_request(tool_name, kwargs)

    def __getattr__(self, name):
        def _call(**kwargs):
            return self._send_request(name, kwargs)
        return _call

tools = _ToolBridge({rpc_port})

# ── User Code ──
{user_code}
'''


    async def _start_tool_rpc_server(self, allowed_tools):
        """Start localhost TCP server that bridges tool calls to executor."""

        class _RPCServer:
            def __init__(self, executor, allowed):
                self.executor = executor
                self.allowed = set(allowed) if allowed else None
                self.call_count = 0
                self._server: Optional[asyncio.Server] = None

            async def handle_client(self, reader, writer):
                try:
                    data = await asyncio.wait_for(reader.read(1_000_000), timeout=60)
                    request = json.loads(data.decode("utf-8"))
                    tool_name = request["tool"]
                    tool_args = request.get("args", {})

                    if self.allowed and tool_name not in self.allowed:
                        result = {"error": f"Tool '{tool_name}' not in allowed list"}
                    else:
                        self.call_count += 1
                        result = await self.executor.execute(tool_name, tool_args)

                    writer.write(json.dumps(result, default=str).encode("utf-8"))
                    await writer.drain()
                except Exception as e:
                    try:
                        writer.write(json.dumps({"error": str(e)}).encode("utf-8"))
                        await writer.drain()
                    except Exception:
                        pass
                finally:
                    try:
                        writer.close()
                        await writer.wait_closed()
                    except Exception:
                        pass

            def close(self):
                if self._server:
                    self._server.close()

            async def wait_closed(self):
                if self._server:
                    await self._server.wait_closed()

        rpc = _RPCServer(self.tool_executor, allowed_tools)
        server = await asyncio.start_server(rpc.handle_client, "127.0.0.1", 0)
        rpc._server = server
        port = server.sockets[0].getsockname()[1]
        return rpc, port
