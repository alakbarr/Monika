# ==============================================================================
# File: analysis/mcp/servers/fetch_server.py
# Description: Free Built-in Web Fetcher MCP Server
# Extracts clean text/markdown from public HTTP/HTTPS URLs over stdio JSON-RPC.
# ==============================================================================

import sys
import json
import asyncio
import urllib.request
import urllib.parse
import re
from typing import Any, Dict, List, Optional

from analysis.mcp.protocol import (
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    LATEST_PROTOCOL_VERSION,
    make_error_response,
    make_result_response,
)


class FetchMcpServer:
    """Free web page text extraction MCP server."""

    def __init__(self):
        self.name = "web-fetch-server"
        self.version = "1.0.0"

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "fetch_url_text",
                "description": "Fetch and extract clean readable text from a public web page URL.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "HTTP or HTTPS URL to fetch.",
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Maximum characters to return (default 4000).",
                        },
                    },
                    "required": ["url"],
                },
            }
        ]

    def _clean_html(self, html_content: str) -> str:
        text = re.sub(r"<script.*?</script>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if tool_name == "fetch_url_text":
            url = arguments.get("url", "").strip()
            max_chars = min(int(arguments.get("max_chars", 4000)), 12000)
            if not url.startswith("http://") and not url.startswith("https://"):
                raise ValueError("URL must start with http:// or https://")

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Monika/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode("utf-8", errors="replace")
                cleaned = self._clean_html(html)
                return {"url": url, "length": len(cleaned), "content": cleaned[:max_chars]}

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
    server = FetchMcpServer()
    asyncio.run(server.run())
