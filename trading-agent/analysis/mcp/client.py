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

from analysis.mcp.protocol import LATEST_PROTOCOL_VERSION
from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import default_tool_registry, ToolDefinition

logger = logging.getLogger("TradingAgent.MCP.Client")


class McpServerProcess:
    """Manages an individual stdio-based MCP server subprocess."""

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.command = config.get("command", "python")
        self.args = config.get("args", [])
        self.env = {**os.environ, **config.get("env", {})}
        self.timeout = config.get("timeout_seconds", 15)
        self.process: Optional[asyncio.subprocess.Process] = None
        self._req_id = 0
        self._lock = asyncio.Lock()
        self._pending_futures: Dict[int, asyncio.Future] = {}
        self._listen_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        """Starts the MCP server subprocess and performs initialization handshake."""
        try:
            cmd = [self.command] + self.args
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )
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
            logger.info(f"Connected to MCP server '{self.name}' (PID {self.process.pid})")
            return True
        except Exception as e:
            logger.warning(f"Failed to start MCP server '{self.name}': {e}")
            return False

    async def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Sends a JSON-RPC request and awaits the response."""
        if not self.process or not self.process.stdin:
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
        payload = {"jsonrpc": "2.0", "method": method}
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
        """Cleanly terminates the server process."""
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
        if self.process:
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

    async def execute(self, args: Dict[str, Any], **kwargs) -> Any:
        return await self.server.call_tool(self.remote_tool_name, args)


class McpClientManager:
    """Manages connections to all configured external MCP servers."""

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}
        self.servers: Dict[str, McpServerProcess] = {}

    async def initialize_servers(self) -> int:
        """Starts all enabled MCP servers and bridges their tools into default_tool_registry."""
        mcp_cfg = self.settings.get("mcp", {})
        if not mcp_cfg.get("enabled", True):
            logger.info("MCP client integration is disabled in settings.")
            return 0

        servers_cfg = mcp_cfg.get("client", {}).get("servers", {})
        connected_count = 0

        for s_name, s_cfg in servers_cfg.items():
            if not isinstance(s_cfg, dict) or not s_cfg.get("enabled", False):
                continue

            proc = McpServerProcess(s_name, s_cfg)
            success = await proc.start()
            if success:
                self.servers[s_name] = proc
                tools = await proc.list_tools()
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
                    logger.debug(f"Bridged MCP tool '{local_name}' into ToolRegistry")
                connected_count += 1

        logger.info(f"McpClientManager initialized: {connected_count} server(s) connected.")
        return connected_count

    async def stop(self):
        """Stops all running MCP client subprocesses."""
        for s in self.servers.values():
            await s.stop()
        self.servers.clear()
