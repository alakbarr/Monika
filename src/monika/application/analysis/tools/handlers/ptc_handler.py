"""
Programmatic Tool Calling (PTC) Handler — Subprocess Sandbox.

LLM writes Python script → executed in subprocess → tools accessed via JSON-RPC
over localhost TCP → stdout returned as single tool result.

Zero LLM token cost for intermediate iterations.
"""

import asyncio
import json
import logging
import os
import secrets
import sys
import tempfile
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
            "subprocess",
            "ctypes",
            "shutil",
            "pty",
            "multiprocessing",
            "threading",
            "signal",
            "webbrowser",
            "winreg",
            "_winapi",
            "os",
            "sys",
            "metatrader5",
            "mt5linux",
            "execution",
            "socket",
            "requests",
            "urllib",
            "httpx",
            "aiohttp",
            "pathlib",
        }
        FORBIDDEN_CALLS = {"eval", "exec", "__import__", "compile", "open"}
        DANGEROUS_ATTRIBUTES = {
            "system",
            "popen",
            "spawn",
            "order_send",
            "place_order",
            "close_position",
            "__subclasses__",
            "__builtins__",
            "__base__",
        }

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
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in DANGEROUS_ATTRIBUTES:
                        return False, f"Invocation of dangerous attribute '{node.func.attr}' is prohibited"
            elif isinstance(node, ast.Attribute):
                if node.attr in {"__subclasses__", "__builtins__", "__base__"}:
                    return False, f"Access to reflective attribute '{node.attr}' is prohibited"

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

        # 1. Start RPC server for tool access with ephemeral auth token
        auth_token = secrets.token_hex(24)
        rpc_server, rpc_port = await self._start_tool_rpc_server(allowed_tools, auth_token)

        try:
            # 2. Write script to temp file with tool bridge preamble
            script_content = self._build_sandboxed_script(code, rpc_port, auth_token)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
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
                scratch_dir = Path(base_dir) / "data" / "sandbox_scratch"
                scratch_dir.mkdir(parents=True, exist_ok=True)
                existing_mtimes = {p: p.stat().st_mtime for p in scratch_dir.glob("*") if p.is_file()}

                env = {k: v for k, v in os.environ.items() if k.upper() in safe_keys}
                env["PYTHONPATH"] = str(scratch_dir)
                env["PYTHONUNBUFFERED"] = "1"

                def _run_proc():
                    import subprocess

                    p = subprocess.Popen(
                        [sys.executable, "-I", script_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env,
                        cwd=str(scratch_dir),
                    )
                    try:
                        out, err = p.communicate(timeout=PTC_TIMEOUT_SECONDS)
                        return p.returncode, out, err, False
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait()
                        return -1, b"", b"", True

                returncode, stdout_bytes, stderr_bytes, timed_out = await asyncio.to_thread(_run_proc)

                # Scan for new/modified output files (charts and reports)
                for fpath in scratch_dir.glob("*"):
                    if not fpath.is_file():
                        continue
                    mtime = fpath.stat().st_mtime
                    if fpath not in existing_mtimes or mtime > existing_mtimes[fpath]:
                        suf = fpath.suffix.lower()
                        if suf in (".png", ".jpg", ".jpeg"):
                            if hasattr(self.tool_executor, "_pending_charts") and isinstance(
                                self.tool_executor._pending_charts, dict
                            ):
                                self.tool_executor._pending_charts[f"ptc_{fpath.name}"] = {
                                    "data": fpath.read_bytes(),
                                    "filename": fpath.name,
                                    "caption": f"Chart from Python sandbox: {fpath.name}",
                                }
                        elif suf in (".xlsx", ".csv", ".pdf", ".parquet", ".json"):
                            if hasattr(self.tool_executor, "add_pending_file"):
                                self.tool_executor.add_pending_file(
                                    file_path=str(fpath),
                                    filename=fpath.name,
                                    data=fpath.read_bytes(),
                                    caption=f"File generated in sandbox: {fpath.name}",
                                )

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

    def _build_sandboxed_script(self, user_code: str, rpc_port: int, auth_token: str) -> str:
        """Build script with tool bridge preamble."""
        return f'''import json, sys, socket

class _ToolBridge:
    """RPC bridge to parent agent's tool executor."""
    def __init__(self, port, token):
        self._port = port
        self._token = token

    def _send_request(self, name, kwargs):
        sock = socket.create_connection(("127.0.0.1", self._port), timeout=60)
        try:
            request = json.dumps({{"tool": name, "args": kwargs, "token": self._token}}) + "\\n"
            sock.sendall(request.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
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

tools = _ToolBridge({rpc_port}, "{auth_token}")

# ── User Code ──
{user_code}
'''

    async def _start_tool_rpc_server(self, allowed_tools: Optional[list] = None, auth_token: Optional[str] = None):
        """Start localhost TCP server that bridges tool calls to executor with constant-time token auth."""
        import secrets

        token = auth_token or secrets.token_urlsafe(32)
        FORBIDDEN_PTC_TOOLS = {
            "place_order",
            "close_position",
            "modify_position",
            "kill",
            "cancel_order",
            "submit_asset_analysis",
            "execute_manual_trade",
            "modify_stop_loss",
            "close_all_positions",
            "propose_trade",
            "trade",
            "buy",
            "sell",
            "execute_trade",
            "order_send",
            "emergency_stop",
        }

        class _RPCServer:
            def __init__(self, executor, allowed, token):
                self.executor = executor
                self.allowed = set(allowed) if allowed else None
                self.token = token
                self.call_count = 0
                self._server: Optional[asyncio.Server] = None

            async def handle_client(self, reader, writer):
                try:
                    data = await asyncio.wait_for(reader.readline(), timeout=60)
                    if not data:
                        return
                    request = json.loads(data.decode("utf-8"))
                    req_token = request.get("token", "")
                    if not secrets.compare_digest(str(req_token), self.token):
                        writer.write(json.dumps({"error": "Unauthorized: invalid RPC token"}).encode("utf-8"))
                        await writer.drain()
                        return

                    tool_name = request.get("tool", "")
                    tool_args = request.get("args", {})

                    is_mutating_tool = tool_name in FORBIDDEN_PTC_TOOLS or any(
                        w in tool_name.lower() for w in ("order", "trade", "position", "kill", "submit_asset")
                    )
                    if is_mutating_tool:
                        result = {
                            "error": f"Tool '{tool_name}' involves trade/order mutation and is forbidden in PTC environment (fail-closed)"
                        }
                    elif self.allowed and tool_name not in self.allowed:
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

        rpc = _RPCServer(self.tool_executor, allowed_tools, token)
        server = await asyncio.start_server(rpc.handle_client, "127.0.0.1", 0)
        rpc._server = server
        port = server.sockets[0].getsockname()[1]
        return rpc, port
