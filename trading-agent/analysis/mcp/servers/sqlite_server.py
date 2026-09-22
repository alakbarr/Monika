# ==============================================================================
# File: analysis/mcp/servers/sqlite_server.py
# Description: Free Built-in SQLite Metrics MCP Server (Read-only)
# Exposes read-only SQLite database inspection over standard stdio JSON-RPC.
# ==============================================================================

import sys
import json
import sqlite3
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from analysis.mcp.protocol import (
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    LATEST_PROTOCOL_VERSION,
    make_error_response,
    make_result_response,
)


class SqliteMcpServer:
    """Read-only SQLite MCP Server for checkpointer and metrics inspection."""

    def __init__(self):
        self.name = "sqlite-metrics-server"
        self.version = "1.0.0"

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "sqlite_list_tables",
                "description": "List all tables and row counts in a local SQLite database.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "db_path": {
                            "type": "string",
                            "description": "Optional path to SQLite db (defaults to checkpointer or data db).",
                        }
                    },
                    "required": [],
                },
            },
            {
                "name": "sqlite_read_query",
                "description": "Execute a strictly read-only SELECT query against a local SQLite database.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "SQL SELECT query to execute (must start with SELECT or PRAGMA).",
                        },
                        "db_path": {
                            "type": "string",
                            "description": "Optional path to SQLite db.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum rows to return (default 50).",
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

    def _get_default_db(self) -> str:
        root = Path(__file__).resolve().parent.parent.parent.parent
        chk = root / "checkpoints.db"
        if chk.exists():
            return str(chk)
        # Search for any .db in trading-agent
        for d in root.glob("*.db"):
            return str(d)
        return str(root / "monika.db")

    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        db_path = arguments.get("db_path") or self._get_default_db()

        if tool_name == "sqlite_list_tables":
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [r[0] for r in cursor.fetchall()]
                results = {}
                for t in tables:
                    cursor.execute(f"SELECT count(*) FROM {t}")
                    results[t] = cursor.fetchone()[0]
                return {"database": db_path, "tables": results}
            finally:
                conn.close()

        elif tool_name == "sqlite_read_query":
            query = arguments.get("query", "").strip()
            # Enforce read-only safety
            normalized_q = query.upper()
            if not (normalized_q.startswith("SELECT") or normalized_q.startswith("PRAGMA") or normalized_q.startswith("EXPLAIN")):
                raise PermissionError("Only SELECT and PRAGMA read-only queries are permitted.")
            for forbid in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH", "DETACH"]:
                if forbid in normalized_q.split():
                    raise PermissionError(f"Disallowed mutating keyword: {forbid}")

            limit = min(int(arguments.get("limit", 50)), 100)
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                cursor = conn.cursor()
                cursor.execute(query)
                cols = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = cursor.fetchmany(limit)
                records = [dict(zip(cols, r)) for r in rows]
                return {"rows_returned": len(records), "records": records}
            finally:
                conn.close()

        raise ValueError(f"Unknown tool: '{tool_name}'")

    async def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {}) or {}

        if method == "initialize":
            return make_result_response(
                req_id,
                {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                },
            )
        elif method == "notifications/initialized":
            return None
        elif method == "ping":
            return make_result_response(req_id, {})
        elif method == "tools/list":
            return make_result_response(req_id, {"tools": self.get_tool_definitions()})
        elif method == "tools/call":
            t_name = params.get("name")
            args = params.get("arguments", {}) or {}
            if not isinstance(t_name, str):
                return make_error_response(req_id, -32602, "Invalid params: 'name' must be a string")
            try:
                res = self.handle_tool_call(t_name, args)
                return make_result_response(
                    req_id,
                    {"content": [{"type": "text", "text": json.dumps(res, indent=2)}]},
                )
            except Exception as e:
                return make_result_response(
                    req_id,
                    {"isError": True, "content": [{"type": "text", "text": f"Error: {e}"}]},
                )
        return make_error_response(req_id, METHOD_NOT_FOUND, f"Unknown method: '{method}'")

    async def run(self):
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
                resp = await self.handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err = make_error_response(None, PARSE_ERROR, str(e))
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = SqliteMcpServer()
    asyncio.run(server.run())
