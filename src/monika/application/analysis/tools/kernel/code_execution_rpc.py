# ==============================================================================
# File: analysis/tools/kernel/code_execution_rpc.py
# ==============================================================================

"""
Host-side RPC Server for Programmatic Tool Calling (PTC).
Institutional-grade engine turn protection architecture.

Enables sandboxed or persistent Python scripts to execute Monika tools
directly over loopback TCP IPC without paying multiple LLM inference turn roundtrips.
Enforces per-call token authentication, strict tool allowlisting, call budgets,
and thread-safe async dispatching via UnifiedToolRegistry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import socket
import threading
import time
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.Tools.CodeExecutionRpc")

# Blocked parameters from sandbox scripts to prevent daemon leakage or hangs
BLOCKED_TOOL_PARAMS = frozenset({"background", "is_daemon", "interactive", "wait_for_input"})

DEFAULT_MAX_TOOL_CALLS = 50

# Default tools accessible within the sandbox environment
DEFAULT_SANDBOX_TOOLS = frozenset(
    {
        "get_market_quote",
        "get_chart",
        "get_multi_timeframe_summary",
        "get_spread_snapshot",
        "get_central_bank_expectations",
        "get_bond_yield_spreads",
        "get_market_correlations",
        "get_eia_oil_inventory",
        "get_timesfm_forecast",
        "calculate_position_size",
        "search_historical_memories",
        "inspect_database_schema",
        "read_database_records",
        "web_search",
        "list_active_intelligence",
    }
)


def generate_monika_tools_client_code(port: int, token: str, allowed_tools: Set[str] | FrozenSet[str]) -> str:
    """
    Generate client stub script to be injected into the execution sandbox environment.
    Provides convenient `call_tool(tool_name, **kwargs)` and named stubs.
    """
    tools_list_repr = repr(list(sorted(allowed_tools)))
    return f'''# Auto-generated Monika Programmatic Tool Calling (PTC) Client
import json
import socket

_RPC_HOST = "127.0.0.1"
_RPC_PORT = {port}
_RPC_TOKEN = "{token}"
_ALLOWED_TOOLS = set({tools_list_repr})

def call_tool(tool_name: str, **kwargs) -> str:
    """Invoke a registered Monika tool directly via loopback RPC."""
    if tool_name not in _ALLOWED_TOOLS:
        raise ValueError(f"Tool '{{tool_name}}' is not allowed in sandbox. Allowed: {{sorted(_ALLOWED_TOOLS)}}")

    payload = {{
        "token": _RPC_TOKEN,
        "tool": tool_name,
        "args": kwargs,
    }}
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(60.0)
    try:
        sock.connect((_RPC_HOST, _RPC_PORT))
        req_bytes = (json.dumps(payload) + "\\n").encode("utf-8")
        sock.sendall(req_bytes)

        response_buf = bytearray()
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            response_buf.extend(chunk)
            if b"\\n" in chunk:
                break
        res_str = response_buf.decode("utf-8").strip()
        try:
            parsed = json.loads(res_str)
            if isinstance(parsed, dict) and "error" in parsed:
                return f"Error: {{parsed['error']}}"
            return res_str
        except Exception:
            return res_str
    finally:
        sock.close()

# Export helper functions for common tools
def get_market_quote(symbol: str) -> str:
    return call_tool("get_market_quote", symbol=symbol)

def search_historical_memories(query: str, top_k: int = 5) -> str:
    return call_tool("search_historical_memories", query=query, top_k=top_k)

def calculate_position_size(symbol: str, entry_price: float = 0.0, stop_loss: float = 0.0, risk_pct: float = 1.0, **kwargs) -> str:
    return call_tool("calculate_position_size", symbol=symbol, entry_price=entry_price, stop_loss=stop_loss, risk_pct=risk_pct, **kwargs)

def read_database_records(table_name: str, limit: int = 50) -> str:
    return call_tool("read_database_records", table_name=table_name, limit=limit)
'''


class CodeExecutionRpcServer:
    """
    Host-side Loopback TCP RPC Server for Programmatic Tool Calling.
    """

    def __init__(
        self,
        allowed_tools: Optional[FrozenSet[str] | Set[str]] = None,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
        dispatch_fn: Optional[Callable[[str, Dict[str, Any]], str]] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.allowed_tools: FrozenSet[str] = frozenset(allowed_tools or DEFAULT_SANDBOX_TOOLS)
        self.max_tool_calls = max_tool_calls
        self.tool_call_counter = [0]
        self.tool_call_log: List[Dict[str, Any]] = []
        self.rpc_token: str = secrets.token_hex(16)
        self.stop_event = threading.Event()
        self.server_sock: Optional[socket.socket] = None
        self.port: int = 0
        self.dispatch_fn = dispatch_fn
        self.loop = loop
        self._thread: Optional[threading.Thread] = None
        self.semaphore = threading.Semaphore(10)  # max_parallel_sub_calls = 10
        self._client_threads: List[threading.Thread] = []
        self._threads_lock = threading.Lock()

    def start(self) -> int:
        """Bind to ephemeral loopback port and start background listener thread."""
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", 0))
        self.port = self.server_sock.getsockname()[1]
        self.server_sock.listen(10)
        self.server_sock.settimeout(0.2)

        self._thread = threading.Thread(
            target=self._server_loop,
            name=f"monika-rpc-{self.port}",
            daemon=True,
        )
        self._thread.start()
        logger.debug(
            f"[CodeExecutionRPC] Server listening on 127.0.0.1:{self.port} with {len(self.allowed_tools)} tools."
        )
        return self.port

    def stop(self) -> None:
        """Stop server, close socket, and clean up active client threads."""
        self.stop_event.set()
        if self.server_sock:
            try:
                self.server_sock.close()
            except OSError:
                pass
        with self._threads_lock:
            threads = list(self._client_threads)
        for t in threads:
            if t.is_alive():
                t.join(timeout=0.5)
        with self._threads_lock:
            self._client_threads.clear()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.debug("[CodeExecutionRPC] Server stopped.")

    def _default_dispatch(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Default dispatch using Monika UnifiedToolRegistry."""
        from monika.application.analysis.tools.unified_registry import unified_tool_registry

        # Strip blocked params
        for p in BLOCKED_TOOL_PARAMS:
            tool_args.pop(p, None)

        if self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                unified_tool_registry.dispatch(tool_name, tool_args),
                self.loop,
            )
            return future.result(timeout=60.0)
        else:
            # Fallback to new event loop runner
            return asyncio.run(unified_tool_registry.dispatch(tool_name, tool_args))

    def _handle_request(self, request: Dict[str, Any]) -> str:
        token = request.get("token", "")
        if not self.rpc_token or not secrets.compare_digest(str(token), self.rpc_token):
            return json.dumps({"error": "Unauthorized RPC request: invalid token"})

        tool_name = request.get("tool", "")
        tool_args = request.get("args", {}) or {}

        if tool_name not in self.allowed_tools:
            return json.dumps(
                {
                    "error": f"Tool '{tool_name}' is not allowed in execute_code. "
                    f"Allowed: {', '.join(sorted(self.allowed_tools))}"
                }
            )

        if self.tool_call_counter[0] >= self.max_tool_calls:
            return json.dumps(
                {"error": f"Tool call budget exceeded ({self.max_tool_calls}). No more tool calls permitted."}
            )

        start_time = time.monotonic()
        dispatcher = self.dispatch_fn or self._default_dispatch

        try:
            result = dispatcher(tool_name, tool_args)
        except Exception as exc:
            logger.error(f"[CodeExecutionRPC] Error executing tool '{tool_name}': {exc}", exc_info=True)
            result = f"Error executing tool '{tool_name}': {exc}"

        duration = round(time.monotonic() - start_time, 3)
        self.tool_call_counter[0] += 1
        self.tool_call_log.append(
            {
                "tool": tool_name,
                "args_preview": str(tool_args)[:100],
                "duration": duration,
            }
        )
        return result

    def _server_loop(self) -> None:
        """Accept loopback connections and spawn concurrent client workers gated by semaphore."""
        if not self.server_sock:
            return
        while not self.stop_event.is_set():
            try:
                conn, _ = self.server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            worker_thread = threading.Thread(
                target=self._client_worker,
                args=(conn,),
                daemon=True,
            )
            with self._threads_lock:
                self._client_threads.append(worker_thread)
            worker_thread.start()

    def _client_worker(self, conn: socket.socket) -> None:
        cur_thread = threading.current_thread()
        try:
            with self.semaphore:
                self._handle_client(conn)
        finally:
            with self._threads_lock:
                if cur_thread in self._client_threads:
                    self._client_threads.remove(cur_thread)

    def _handle_client(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(60.0)
            buf = bytearray()
            while not self.stop_event.is_set():
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf) > 5 * 1024 * 1024:
                    conn.sendall(json.dumps({"error": "Payload exceeds 5MB limit"}).encode("utf-8") + b"\n")
                    return
                if b"\n" in chunk:
                    break
            if buf:
                line = buf.decode("utf-8").strip()
                try:
                    req_data = json.loads(line)
                    resp_str = self._handle_request(req_data)
                except Exception as e:
                    resp_str = json.dumps({"error": f"Invalid RPC payload: {e}"})
                conn.sendall((resp_str + "\n").encode("utf-8"))
        except Exception as e:
            logger.debug(f"[CodeExecutionRPC] Connection error: {e}")
        finally:
            try:
                conn.close()
            except OSError:
                pass


def render_tools_sdk_py(tool_schemas: List[Dict[str, Any]]) -> str:
    """
    Generate clean Python TypedDict and Tools(Protocol) type stub documentation
    from tool JSON schemas for read-only/analysis tools.
    """
    lines: List[str] = [
        '"""',
        "Auto-generated Monika Tools SDK type definitions.",
        "Provides TypedDict argument interfaces and Protocol method signatures.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Any, Dict, List, Optional, Protocol, TypedDict",
        "",
    ]

    type_mapping = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "List[Any]",
        "object": "Dict[str, Any]",
    }

    protocol_methods: List[str] = []

    for tool in tool_schemas:
        fn_data = tool.get("function", tool)
        name = fn_data.get("name", "")
        if not name:
            continue
        description = fn_data.get("description", "")
        params = fn_data.get("parameters", {})
        properties = params.get("properties", {})
        required = set(params.get("required", []))

        pascal_name = "".join(part.capitalize() for part in name.split("_"))
        typed_dict_name = f"{pascal_name}Args"

        lines.append(f"class {typed_dict_name}(TypedDict, total=False):")
        if description:
            first_line = description.strip().splitlines()[0]
            lines.append(f'    """{first_line}"""')

        if not properties:
            lines.append("    pass")
        else:
            for prop_name, prop_def in properties.items():
                p_type_raw = prop_def.get("type", "any")
                py_type = type_mapping.get(p_type_raw, "Any")
                if prop_name not in required:
                    py_type = f"Optional[{py_type}]"
                p_desc = prop_def.get("description", "")
                comment = f"  # {p_desc}" if p_desc else ""
                lines.append(f"    {prop_name}: {py_type}{comment}")

        lines.append("")

        param_sigs = ["self"]
        for prop_name, prop_def in properties.items():
            p_type_raw = prop_def.get("type", "any")
            py_type = type_mapping.get(p_type_raw, "Any")
            if prop_name not in required:
                param_sigs.append(f"{prop_name}: Optional[{py_type}] = None")
            else:
                param_sigs.append(f"{prop_name}: {py_type}")
        param_sigs.append("**kwargs: Any")

        method_doc = f'        """{description.strip()}"""' if description else '        """Execute tool."""'
        sig_str = ", ".join(param_sigs)
        protocol_methods.append(f"    def {name}({sig_str}) -> str:")
        protocol_methods.append(method_doc)
        protocol_methods.append("        ...")
        protocol_methods.append("")

    lines.append("class Tools(Protocol):")
    lines.append('    """Protocol defining available Monika analysis and research tools."""')
    lines.append("")
    if not protocol_methods:
        lines.append("    pass")
    else:
        lines.extend(protocol_methods)

    return "\n".join(lines) + "\n"
