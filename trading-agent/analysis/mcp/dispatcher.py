# ==============================================================================
# File: analysis/mcp/dispatcher.py
# Description: Unified Model Context Protocol (MCP) Server Dispatcher for Monika
# Exposes both specialized quantitative trading tools and all registered
# UnifiedToolRegistry tools to external AI assistants (Cursor, Claude, IDEs)
# via JSON-RPC 2.0 over standard I/O and HTTP/SSE.
# ==============================================================================

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from analysis.mcp.protocol import (
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR,
    LATEST_PROTOCOL_VERSION,
    make_error_response,
    make_result_response,
)
from analysis.mcp.server import MonikaMcpServer
from analysis.tools.unified_registry import unified_tool_registry

logger = logging.getLogger("TradingAgent.MCP.Dispatcher")


class MonikaMcpDispatcher:
    """Unified MCP Server Dispatcher.
    
    Serves both:
    1. Built-in Quantitative Trading tools from MonikaMcpServer (positions, macro regime, calendar, playbooks).
    2. Dynamic tools registered in UnifiedToolRegistry (Pydantic v2 schemas).
    """

    def __init__(self, settings: Optional[Dict[str, Any]] = None, name: str = "monika-agent", version: str = "1.0.0"):
        self.settings = settings or {}
        self.name = name
        self.version = version
        self._quant_server = MonikaMcpServer(settings=self.settings)

    def get_tool_list(self) -> List[Dict[str, Any]]:
        """Combine quant tool definitions and dynamic UnifiedToolRegistry tools."""
        combined_tools: Dict[str, Dict[str, Any]] = {}

        # 1. Quant built-in tools
        for q_tool in self._quant_server.get_tool_definitions():
            combined_tools[q_tool["name"]] = q_tool

        # 2. Unified Tool Registry tools
        for t in unified_tool_registry.list_tools(only_available=True):
            input_model = getattr(t, "input_model", None)
            if input_model is not None and isinstance(input_model, type) and issubclass(input_model, BaseModel) and input_model is not BaseModel:
                try:
                    schema = input_model.model_json_schema()
                    schema.pop("title", None)
                except Exception:
                    schema = {"type": "object", "properties": {}}
            else:
                schema = {"type": "object", "properties": {}}

            tool_def = {
                "name": t.name,
                "description": t.description or f"Monika tool {t.name}",
                "inputSchema": schema,
            }
            combined_tools[t.name] = tool_def

        return list(combined_tools.values())

    async def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process incoming MCP JSON-RPC 2.0 request."""
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {}) or {}

        # Handle notifications (requests without id)
        if req_id is None:
            if method == "notifications/initialized":
                logger.info("[MonikaMcpDispatcher] Client initialized.")
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
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

            # Check if it's one of the dedicated quant tools
            quant_tool_names = {t["name"] for t in self._quant_server.get_tool_definitions()}
            if tool_name in quant_tool_names:
                return await self._quant_server.handle_request(request)

            # Check if it's in the UnifiedToolRegistry
            t_def = unified_tool_registry.get_tool(tool_name)
            if not t_def:
                return make_error_response(req_id, INVALID_PARAMS, f"Tool '{tool_name}' not found")

            try:
                # If tool has Pydantic input model, validate inputs
                input_model = getattr(t_def, "input_model", None)
                if input_model is not None and isinstance(input_model, type) and issubclass(input_model, BaseModel):
                    validated = input_model(**tool_args)
                    call_kwargs = validated.model_dump()
                else:
                    call_kwargs = tool_args

                handler = t_def.handler
                if t_def.is_async:
                    result = await handler(**call_kwargs)
                else:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(None, lambda: handler(**call_kwargs))

                return make_result_response(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result),
                            }
                        ]
                    },
                )
            except Exception as e:
                logger.error(f"[MonikaMcpDispatcher] Error executing tool '{tool_name}': {e}", exc_info=True)
                return make_result_response(
                    req_id,
                    {
                        "isError": True,
                        "content": [
                            {"type": "text", "text": f"Tool execution failed: {str(e)}"}
                        ],
                    },
                )

        else:
            return make_error_response(req_id, METHOD_NOT_FOUND, f"Method '{method}' not found")

    async def run_stdio(self):
        """Runs standard I/O loop reading lines from stdin and writing JSON responses to stdout."""
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break

            line_str = line.strip()
            if not line_str:
                continue

            try:
                req = json.loads(line_str)
            except Exception as e:
                err_resp = make_error_response(None, PARSE_ERROR, f"Invalid JSON: {e}")
                sys.stdout.write(json.dumps(err_resp) + "\n")
                sys.stdout.flush()
                continue

            resp = await self.handle_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
