# ==============================================================================
# File: analysis/mcp/servers/fetch_server.py
# Description: Free Built-in Web Fetcher MCP Server
# Extracts clean text/markdown from public HTTP/HTTPS URLs over stdio JSON-RPC.
# ==============================================================================

import asyncio
import ipaddress
import json
import re
import socket
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from monika.infrastructure.mcp.protocol import (
    INVALID_REQUEST,
    LATEST_PROTOCOL_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    make_error_response,
    make_result_response,
)


def validate_safe_url(url: str) -> None:
    """Validate that the URL does not resolve to private, loopback, or cloud metadata IPs."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must start with http:// or https://")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must include a valid hostname")

    lowered = hostname.lower()
    if lowered in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        raise PermissionError(f"Access to private/local network address '{hostname}' is forbidden.")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise PermissionError(f"Access to private/local network IP '{ip_str}' is forbidden.")
            if str(ip) in ("169.254.169.254", "169.254.170.2"):
                raise PermissionError("Access to cloud metadata endpoint is forbidden.")
    except socket.gaierror as e:
        raise ValueError(f"Could not resolve hostname '{hostname}': {e}")


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Enforces SSRF validation on every redirect location."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
        validate_safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


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
            validate_safe_url(url)

            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Monika/1.0"},
            )
            opener = urllib.request.build_opener(SafeRedirectHandler)
            with opener.open(req, timeout=10) as response:
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
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line_str = line.strip()
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
