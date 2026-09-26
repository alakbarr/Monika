# ==============================================================================
# File: analysis/mcp/client.py
# Description: Model Context Protocol (MCP) Client Manager for Monika
# Connects to external or local MCP servers and bridges their tools into Monika's ToolRegistry.
# ==============================================================================

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import aiohttp

import asyncio
import json
import logging
import os
import sys
import urllib.parse
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import aiohttp

from analysis.mcp.protocol import LATEST_PROTOCOL_VERSION
from analysis.mcp.mcp_death_supervisor import McpDeathSupervisor
from analysis.mcp.mcp_schema_cache import McpSchemaCache
from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import default_tool_registry, ToolDefinition
from analysis.tools.unified_registry import unified_tool_registry
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.MCP.Client")


class McpServerProcess:
    """Manages an individual stdio-based or HTTP/SSE-based MCP server process/connection."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.transport = config.get("transport", "stdio").lower()
        self.command = config.get("command", "python")
        self.args = config.get("args", [])
        self.url = config.get("url", "")
        self.auth_token = config.get("auth_token")
        self.proxy = config.get("proxy")
        self.env = {**os.environ, **config.get("env", {})}
        self.timeout = config.get("timeout_seconds", 15)
        self.process: Optional[asyncio.subprocess.Process] = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._req_id = 0
        self._lock = asyncio.Lock()
        self._pending_futures: Dict[int, asyncio.Future] = {}
        self._listen_task: Optional[asyncio.Task] = None
        self._post_url: str = self.url
        self._endpoint_discovered: Optional[asyncio.Event] = None

    async def _read_sse_stream(self, resp: aiohttp.ClientResponse):
        """Read Server-Sent Events (SSE) stream from the server."""
        current_event = "message"
        current_data: List[str] = []
        try:
            async for raw_line in resp.content:
                line = raw_line.decode("utf-8").rstrip("\r\n")
                if not line:
                    if current_data:
                        data_str = "\n".join(current_data)
                        if current_event == "endpoint":
                            endpoint_url = data_str.strip()
                            self._post_url = urllib.parse.urljoin(self.url, endpoint_url)
                            logger.info(f"[MCP SSE] Discovered POST endpoint for '{self.name}': {self._post_url}")
                            if self._endpoint_discovered and not self._endpoint_discovered.is_set():
                                self._endpoint_discovered.set()
                        elif current_event == "message":
                            try:
                                msg = json.loads(data_str)
                                msg_id = msg.get("id")
                                if msg_id is not None and msg_id in self._pending_futures:
                                    fut = self._pending_futures.pop(msg_id)
                                    if not fut.done():
                                        fut.set_result(msg)
                            except Exception as e:
                                logger.debug(f"[MCP SSE] Failed to parse message: {e}")
                    current_event = "message"
                    current_data = []
                    continue

                if line.startswith("event:"):
                    current_event = line[6:].strip()
                elif line.startswith("data:"):
                    current_data.append(line[5:].lstrip())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"[MCP SSE] Stream reader error for '{self.name}': {e}")

    async def start(self) -> bool:
        """Starts the MCP server subprocess or HTTP/SSE session and performs handshake."""
        try:
            if self.transport == "sse":
                self._endpoint_discovered = asyncio.Event()
                self._post_url = self.url
                timeout = aiohttp.ClientTimeout(total=None, sock_read=None)
                headers = {"Accept": "text/event-stream"}
                if self.auth_token:
                    headers["Authorization"] = f"Bearer {self.auth_token}"
                self._http_session = aiohttp.ClientSession(timeout=timeout, trust_env=True)

                resp = await self._http_session.get(self.url, headers=headers)
                if resp.status != 200:
                    logger.warning(f"MCP SSE connection to '{self.name}' failed with status {resp.status}")
                    return False
                self._listen_task = asyncio.create_task(self._read_sse_stream(resp))

                try:
                    await asyncio.wait_for(self._endpoint_discovered.wait(), timeout=min(self.timeout, 8.0))
                except asyncio.TimeoutError:
                    logger.debug(f"[MCP SSE] No endpoint event received, defaulting POST URL to {self.url}")
            elif self.transport == "http":
                self._post_url = self.url
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                headers = {"Content-Type": "application/json"}
                if self.auth_token:
                    headers["Authorization"] = f"Bearer {self.auth_token}"
                self._http_session = aiohttp.ClientSession(
                    headers=headers, timeout=timeout, trust_env=True
                )
            else:
                # Default stdio
                cmd = [self.command] + self.args
                self.process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self.env,
                )
                if self.process and self.process.pid:
                    McpDeathSupervisor.register_process(self.process.pid)
                self._listen_task = asyncio.create_task(self._read_responses())

            # Perform initialize handshake
            init_res = await self.send_request(
                "initialize",
                {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "monika-mcp-client", "version": "1.0.0"},
                },
            )
            if not init_res or "error" in init_res:
                logger.warning(f"MCP server '{self.name}' initialization failed: {init_res}")
                return False

            # Send initialized notification
            await self.send_notification("notifications/initialized", {})
            conn_info = f"PID {self.process.pid}" if self.process else f"URL {self.url}"
            logger.info(f"Connected to MCP server '{self.name}' via {self.transport} ({conn_info})")
            return True
        except Exception as e:
            logger.warning(f"Failed to start MCP server '{self.name}': {e}")
            return False

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Sends a JSON-RPC request and awaits the response over stdio or HTTP/SSE."""
        async with self._lock:
            self._req_id += 1
            cur_id = self._req_id

        payload = {"jsonrpc": "2.0", "id": cur_id, "method": method}
        if params is not None:
            payload["params"] = params

        # HTTP / SSE transport dispatch
        if self.transport in ("sse", "http"):
            if not self._http_session:
                return {"error": "HTTP session is not initialized"}
            target_url = getattr(self, "_post_url", self.url)
            headers = {"Content-Type": "application/json"}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"

            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._pending_futures[cur_id] = fut

            try:
                async with self._http_session.post(target_url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        body = await resp.json()
                        self._pending_futures.pop(cur_id, None)
                        return body
                    elif resp.status in (202, 204):
                        # Awaiting async response via SSE event stream
                        return await asyncio.wait_for(fut, timeout=self.timeout)
                    else:
                        self._pending_futures.pop(cur_id, None)
                        return {"error": f"HTTP {resp.status}: {await resp.text()}"}
            except asyncio.TimeoutError:
                self._pending_futures.pop(cur_id, None)
                return {"error": f"Request {cur_id} timed out after {self.timeout}s"}
            except Exception as exc:
                self._pending_futures.pop(cur_id, None)
                return {"error": f"HTTP request failed: {exc}"}

        # Stdio transport dispatch
        if not self.process or not self.process.stdin:
            return {"error": "Server process is not running"}

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_futures[cur_id] = fut

        line = json.dumps(payload) + "\n"
        try:
            self.process.stdin.write(line.encode("utf-8"))
            await self.process.stdin.drain()
            result = await asyncio.wait_for(fut, timeout=self.timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_futures.pop(cur_id, None)
            return {"error": f"MCP request to '{self.name}' timed out after {self.timeout}s"}
        except Exception as e:
            self._pending_futures.pop(cur_id, None)
            return {"error": str(e)}
            return {"error": "Server process is not running"}

        async with self._lock:
            self._req_id += 1
            cur_id = self._req_id

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_futures[cur_id] = fut

        payload = {"jsonrpc": "2.0", "id": cur_id, "method": method}
        if params is not None:
            payload["params"] = params

        line = json.dumps(payload) + "\n"
        try:
            self.process.stdin.write(line.encode("utf-8"))
            await self.process.stdin.drain()
            result = await asyncio.wait_for(fut, timeout=self.timeout)
            return result
        except asyncio.TimeoutError:
            self._pending_futures.pop(cur_id, None)
            return {"error": f"MCP request to '{self.name}' timed out after {self.timeout}s"}
        except Exception as e:
            self._pending_futures.pop(cur_id, None)
            return {"error": str(e)}

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None):
        """Sends a JSON-RPC notification (no response expected)."""
        if not self.process or not self.process.stdin:
            return
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        line = json.dumps(payload) + "\n"
        try:
            self.process.stdin.write(line.encode("utf-8"))
            await self.process.stdin.drain()
        except Exception as e:
            logger.debug(f"Failed to send notification to '{self.name}': {e}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Fetches available tools from the MCP server."""
        resp = await self.send_request("tools/list", {})
        if resp and "result" in resp and "tools" in resp["result"]:
            return resp["result"]["tools"]
        return []

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Calls an MCP tool on this server."""
        resp = await self.send_request("tools/call", {"name": tool_name, "arguments": arguments})
        if not resp:
            return {"error": "No response received from MCP server"}
        if "error" in resp:
            return {"error": resp["error"]}
        return resp.get("result", {})

    async def _read_responses(self):
        """Background reader for stdio lines."""
        if not self.process or not self.process.stdout:
            return
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                    msg_id = data.get("id")
                    if msg_id is not None and msg_id in self._pending_futures:
                        fut = self._pending_futures.pop(msg_id)
                        if not fut.done():
                            fut.set_result(data)
                except Exception as e:
                    logger.debug(f"MCP server '{self.name}' malformed response: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"MCP server '{self.name}' reader stopped: {e}")

    async def stop(self):
        """Cleanly terminates the server process or HTTP/SSE session."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

        if self.process:
            if self.process.pid:
                McpDeathSupervisor.unregister_process(self.process.pid)
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None


class McpBridgeHandler(ToolHandler):
    """Dynamic ToolHandler that routes execution to an active MCP server."""

    def __init__(self, server: McpServerProcess, remote_tool_name: str, local_tool_name: str):
        self.server = server
        self.remote_tool_name = remote_tool_name
        self.name = local_tool_name
        self.category = "MCP"
        self.parallel_safe = True

    async def execute(
        self,
        args: Dict[str, Any],
        session: Optional[AsyncSession] = None,
        executor: Optional[Any] = None,
        **kwargs: Any
    ) -> Any:
        return await self.server.call_tool(self.remote_tool_name, args)


class McpClientManager:
    """Manages connections to all configured external MCP servers with disk schema caching."""

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}
        self.servers: Dict[str, McpServerProcess] = {}
        self.schema_cache = McpSchemaCache()

    async def initialize_servers(self) -> int:
        """Starts all enabled MCP servers and bridges their tools into default_tool_registry."""
        mcp_cfg = self.settings.get("mcp", {})
        if not mcp_cfg.get("enabled", True):
            logger.info("MCP client integration is disabled in settings.")
            return 0

        servers_cfg = mcp_cfg.get("client", {}).get("servers", {})
        connected_count = 0

        # Phase 1: Optimistic Lazy Registration from disk schema cache
        for s_name, s_cfg in servers_cfg.items():
            if not isinstance(s_cfg, dict) or not s_cfg.get("enabled", False):
                continue
            cached_tools = self.schema_cache.get_cached_tools(s_name, s_cfg)
            if cached_tools:
                logger.info(f"[McpClientManager] Lazy-booted {len(cached_tools)} cached tools for '{s_name}'.")

        # Phase 2: Live Connections & Cache Freshness Update
        for s_name, s_cfg in servers_cfg.items():
            if not isinstance(s_cfg, dict) or not s_cfg.get("enabled", False):
                continue

            proc = McpServerProcess(s_name, s_cfg)
            success = await proc.start()
            if success:
                self.servers[s_name] = proc
                tools = await proc.list_tools()
                if tools:
                    self.schema_cache.save_cached_tools(s_name, s_cfg, tools)

                for t in tools:
                    t_name = t.get("name", "")
                    if not t_name:
                        continue
                    local_name = f"mcp_{s_name}_{t_name}"
                    handler = McpBridgeHandler(proc, t_name, local_name)
                    # Register into default_tool_registry
                    default_tool_registry.register(
                        handler,
                        name=local_name,
                        aliases=[f"{s_name}_{t_name}"],
                        category="MCP",
                    )
                    # Register into unified_tool_registry
                    try:
                        unified_tool_registry.register_tool(
                            name=local_name,
                            category="MCP",
                            handler=handler.execute,
                            is_async=True,
                            description=t.get("description", f"MCP tool {t_name} from {s_name}"),
                        )
                    except Exception as reg_err:
                        logger.debug(f"Could not register '{local_name}' to unified_tool_registry: {reg_err}")
                    logger.debug(f"Bridged MCP tool '{local_name}' into ToolRegistry")
                connected_count += 1

        logger.info(f"McpClientManager initialized: {connected_count} server(s) connected.")
        return connected_count

    async def stop(self):
        """Stops all running MCP client subprocesses and connections."""
        for s in self.servers.values():
            await s.stop()
        self.servers.clear()
