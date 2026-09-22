# ==============================================================================
# File: analysis/mcp/server.py
# Description: Monika Model Context Protocol (MCP) Server
# Exposes Monika quantitative trading intelligence, metrics, and playbooks
# to external AI assistants (Claude, Cursor, Antigravity) over standard stdio JSON-RPC.
# ==============================================================================

import sys
import json
import asyncio
import logging
from typing import Any, Dict, List, Optional

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

logger = logging.getLogger("TradingAgent.MCP.Server")


class MonikaMcpServer:
    """Standard Model Context Protocol (MCP) server for Monika trading agent."""

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}
        self.server_name = "monika-trading-server"
        self.server_version = "1.0.0"

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns MCP-compliant tool definitions."""
        return [
            {
                "name": "monika_get_status",
                "description": "Get current Monika system runtime status, kill-switch status, execution mode, and active position counts.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "monika_get_open_positions",
                "description": "List all active open paper and real MT5 trading positions with current floating PnL and risk metrics.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["all", "real", "paper"],
                            "description": "Filter by position mode. Default: 'all'.",
                        }
                    },
                    "required": [],
                },
            },
            {
                "name": "monika_get_macro_regime",
                "description": "Retrieve current detected macro regime, VIX zone, and active market chronicles.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "monika_get_economic_calendar",
                "description": "Retrieve upcoming high- and medium-impact economic calendar events.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "hours_ahead": {
                            "type": "integer",
                            "description": "Hours ahead to inspect (default: 24).",
                        },
                        "impact_filter": {
                            "type": "string",
                            "enum": ["high", "medium", "all"],
                            "description": "Filter by impact level.",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "monika_list_playbooks",
                "description": "List all institutional trading playbooks and crystallized tactical skills available in Monika.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "monika_get_playbook",
                "description": "View the complete markdown content of a specific trading playbook or skill.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Exact name of the playbook (e.g. 'central_banks_framework', 'smc_ict_playbook', 'eurusd_playbook').",
                        }
                    },
                    "required": ["name"],
                },
            },
        ]

    async def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches an MCP tool call to Monika's internal services."""
        if tool_name == "monika_get_status":
            from database.db import get_session
            from database.models import SystemConfig, Position, PaperTradeRecord
            from sqlalchemy import select

            async with get_session() as session:
                cfgs = (await session.execute(select(SystemConfig))).scalars().all()
                cfg_map = {c.key: c.value for c in cfgs}
                open_real = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
                open_paper = (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "open"))).scalars().all()

                return {
                    "kill_switch": cfg_map.get("kill_switch") == "true",
                    "system_paused": cfg_map.get("system_paused") == "true",
                    "auto_execute": cfg_map.get("auto_execute") == "true",
                    "open_real_positions": len(open_real),
                    "open_paper_positions": len(open_paper),
                    "mode": self.settings.get("trading", {}).get("mode", "paper"),
                }

        elif tool_name == "monika_get_open_positions":
            from database.db import get_session
            from database.models import Position, PaperTradeRecord
            from sqlalchemy import select

            mode = arguments.get("mode", "all")
            positions_data = []

            async with get_session() as session:
                if mode in ("all", "real"):
                    real_rows = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
                    for r in real_rows:
                        positions_data.append({
                            "type": "real",
                            "ticket": r.mt5_ticket or r.id,
                            "symbol": r.symbol,
                            "direction": r.direction,
                            "volume": r.volume,
                            "open_price": r.entry_price,
                            "sl": r.sl,
                            "tp": r.tp,
                        })

                if mode in ("all", "paper"):
                    paper_rows = (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "open"))).scalars().all()
                    for p in paper_rows:
                        positions_data.append({
                            "type": "paper",
                            "ticket": p.id,
                            "symbol": p.symbol,
                            "direction": p.direction,
                            "volume": getattr(p, "risk_pct", 0.0),
                            "open_price": p.entry_price,
                            "sl": p.stop_loss,
                            "tp": p.take_profit,
                        })

            return {"count": len(positions_data), "positions": positions_data}

        elif tool_name == "monika_get_macro_regime":
            from database.db import get_session
            from analysis.memory.layered_memory import LayeredMemoryManager

            async with get_session() as session:
                mgr = LayeredMemoryManager(self.settings)
                regime = await mgr._detect_regime(session)
                core_mem = await mgr.get_core_memory(session)
                return {"regime": regime, "core_summary": core_mem}

        elif tool_name == "monika_get_economic_calendar":
            from analysis.tools.handlers.macro_tools import handle_get_economic_calendar
            from database.db import get_session

            async with get_session() as session:
                return await handle_get_economic_calendar(arguments, session=session)

        elif tool_name == "monika_list_playbooks":
            from analysis.tools.handlers.skills_tools import handle_skills_list
            return await handle_skills_list()

        elif tool_name == "monika_get_playbook":
            from analysis.tools.handlers.skills_tools import handle_skill_view
            return await handle_skill_view({"skill_name": arguments.get("name", "")})

        raise ValueError(f"Unknown MCP tool: '{tool_name}'")

    async def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handles a single JSON-RPC / MCP request dictionary."""
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {}) or {}

        if not method:
            return make_error_response(req_id, INVALID_REQUEST, "Missing method")

        if method == "initialize":
            return make_result_response(
                req_id,
                {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                    },
                    "serverInfo": {
                        "name": self.server_name,
                        "version": self.server_version,
                    },
                },
            )

        elif method == "notifications/initialized":
            # Initialized notification from client, no response needed for notifications
            return None

        elif method == "ping":
            return make_result_response(req_id, {})

        elif method == "tools/list":
            tools = self.get_tool_definitions()
            return make_result_response(req_id, {"tools": tools})

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {}) or {}
            if not tool_name:
                return make_error_response(req_id, INVALID_PARAMS, "Missing tool name in tools/call")

            try:
                result = await self.handle_tool_call(tool_name, arguments)
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
                logger.error(f"Error executing MCP tool '{tool_name}': {e}", exc_info=True)
                return make_result_response(
                    req_id,
                    {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": f"Error: {str(e)}",
                            }
                        ],
                    },
                )

        else:
            return make_error_response(req_id, METHOD_NOT_FOUND, f"Method '{method}' not found")

    async def run_stdio(self):
        """Runs standard I/O loop reading lines from stdin and writing JSON responses to stdout."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while True:
            line = await reader.readline()
            if not line:
                break

            line_str = line.decode("utf-8").strip()
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


def run_mcp_server(settings: Optional[Dict[str, Any]] = None):
    """Entrypoint function to run Monika MCP Server over stdio."""
    from utils.infra.event_loop import run_async

    server = MonikaMcpServer(settings=settings)
    run_async(server.run_stdio())


if __name__ == "__main__":
    run_mcp_server()
