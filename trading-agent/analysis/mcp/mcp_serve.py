# ==============================================================================
# File: analysis/mcp/mcp_serve.py
# ==============================================================================

"""
Unified Model Context Protocol (MCP) Server for Monika.
Institutional-grade engine turn protection architecture.

Exposes ALL tools registered in Monika's UnifiedToolRegistry to external clients
(Claude Desktop, Cursor, Antigravity, IDEs, or third-party agent frameworks)
via the standard Model Context Protocol (MCP) JSON-RPC 2.0 over stdio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.MCP.ServerDispatcher")

PROTOCOL_VERSION = "2024-11-05"


class McpServerDispatcher:
    """Standard MCP JSON-RPC 2.0 Server Dispatcher over stdio."""

    def __init__(self, name: str = "monika-agent", version: str = "1.0.0"):
        self.name = name
        self.version = version

    def get_tool_list(self) -> List[Dict[str, Any]]:
        """Extract tool schemas from UnifiedToolRegistry for MCP tools/list response."""
        tools = unified_tool_registry.list_tools(only_available=True)
        result = []
        for t in tools:
            input_model = getattr(t, "input_model", None)
            if input_model is not None and isinstance(input_model, type) and issubclass(input_model, BaseModel) and input_model is not BaseModel:
                try:
                    schema = input_model.model_json_schema()
                    schema.pop("title", None)
                except Exception:
                    schema = {"type": "object", "properties": {}}
            else:
                schema = {"type": "object", "properties": {}}
            result.append({
                "name": t.name,
                "description": t.description or f"Monika tool {t.name}",
                "inputSchema": schema,
            })
        return result

    async def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process incoming MCP JSON-RPC 2.0 request."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {}) or {}

        # Handle notifications (requests without id)
        if req_id is None:
            if method == "notifications/initialized":
                logger.info("[MCPServer] Client initialized.")
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "serverInfo": {
                        "name": self.name,
                        "version": self.version,
                    },
                    "capabilities": {
                        "tools": {
                            "listChanged": True,
                        }
                    },
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": self.get_tool_list(),
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {}) or {}

            try:
                raw_result = await unified_tool_registry.dispatch(tool_name, tool_args)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": str(raw_result),
                            }
                        ],
                        "isError": False,
                    },
                }
            except KeyError:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Tool '{tool_name}' not found in registry.",
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error executing tool '{tool_name}': {exc}",
                            }
                        ],
                        "isError": True,
                    },
                }

        elif method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {},
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not recognized.",
                },
            }

    async def run_stdio(self) -> None:
        """Run loop reading newline-delimited JSON-RPC from sys.stdin."""
        loop = asyncio.get_running_loop()
        while True:
            line_str = await loop.run_in_executor(None, sys.stdin.readline)
            if not line_str:
                break
            line_str = line_str.strip()
            if not line_str:
                continue

            try:
                req_obj = json.loads(line_str)
                resp_obj = await self.handle_request(req_obj)
                if resp_obj is not None:
                    out_line = json.dumps(resp_obj) + "\n"
                    sys.stdout.write(out_line)
                    sys.stdout.flush()
            except Exception as exc:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()


def main():
    """CLI entry point for running Monika as an MCP server."""
    dispatcher = McpServerDispatcher()
    asyncio.run(dispatcher.run_stdio())


if __name__ == "__main__":
    main()
