# ==============================================================================
# File: analysis/mcp/servers/filesystem_server.py
# Description: Free Built-in Sandboxed Filesystem MCP Server (Read-only)
# Exposes safe sandboxed read-only access to playbooks and markdown logs.
# ==============================================================================

import sys
import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from analysis.mcp.protocol import (
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    LATEST_PROTOCOL_VERSION,
    make_error_response,
    make_result_response,
)


class FilesystemMcpServer:
    """Safe read-only MCP Server for inspecting trading playbooks and logs."""

    def __init__(self):
        self.name = "sandboxed-filesystem-server"
        self.version = "1.0.0"
        self.root_dir = Path(__file__).resolve().parent.parent.parent.parent

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "fs_list_playbooks",
                "description": "List all markdown playbook files in skills/trading directory.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "fs_read_playbook",
                "description": "Read the text of a specific playbook or markdown document safely.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of the markdown file (e.g. 'central_banks_framework.md', 'smc_ict_playbook.md').",
                        }
                    },
                    "required": ["filename"],
                },
            },
        ]

    def _resolve_safe_path(self, filename: str) -> Path:
        clean = Path(filename).name
        target = self.root_dir / "skills" / "trading" / clean
        if not target.exists():
            target_pb = self.root_dir / "skills" / "trading" / "playbooks" / clean
            if target_pb.exists():
                return target_pb
            target_cr = self.root_dir / "skills" / "crystallized" / clean
            if target_cr.exists():
                return target_cr
            raise FileNotFoundError(f"File '{clean}' not found in skills directory.")
        return target

    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "fs_list_playbooks":
            skills_dir = self.root_dir / "skills" / "trading"
            files = [f.name for f in skills_dir.glob("*.md")]
            pb_dir = skills_dir / "playbooks"
            if pb_dir.exists():
                files.extend([f"playbooks/{f.name}" for f in pb_dir.glob("*.md")])
            return {"files": files}

        elif tool_name == "fs_read_playbook":
            fname = arguments.get("filename", "")
            safe_path = self._resolve_safe_path(fname)
            content = safe_path.read_text(encoding="utf-8")
            return {"filename": safe_path.name, "content": content}

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
    server = FilesystemMcpServer()
    asyncio.run(server.run())
