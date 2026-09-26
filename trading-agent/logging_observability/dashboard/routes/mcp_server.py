# ==============================================================================
# File: logging_observability/dashboard/routes/mcp_server.py
# Description: Model Context Protocol (MCP) HTTP/SSE Server Router for Dashboard API
# Exposes Monika quantitative trading intelligence and tools to external
# clients over network HTTP/SSE (Cursor, Claude Code, Antigravity, etc.)
# ==============================================================================

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from analysis.mcp.dispatcher import MonikaMcpDispatcher

logger = logging.getLogger("TradingAgent.Dashboard.MCP")

mcp_router = APIRouter(prefix="/api/mcp", tags=["Model Context Protocol"])

# Session queue store for active SSE client connections
_active_mcp_sessions: Dict[str, asyncio.Queue] = {}
_dispatcher: Optional[MonikaMcpDispatcher] = None


def get_dispatcher() -> MonikaMcpDispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = MonikaMcpDispatcher()
    return _dispatcher


@mcp_router.get("/tools")
async def list_mcp_tools():
    """List all MCP tools exposed by Monika."""
    dispatcher = get_dispatcher()
    tools = dispatcher.get_tool_list()
    return JSONResponse(content={"tools": tools, "count": len(tools)})


@mcp_router.get("/sse")
async def mcp_sse_endpoint(request: Request):
    """Server-Sent Events (SSE) endpoint for standard MCP client connections."""
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _active_mcp_sessions[session_id] = queue

    logger.info(f"[MCP-SSE] Client connected. Session ID: {session_id}")

    async def event_generator():
        # Step 1: Send endpoint event directing POST requests to /api/mcp/messages
        post_endpoint = f"/api/mcp/messages?sessionId={session_id}"
        yield f"event: endpoint\ndata: {post_endpoint}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    logger.info(f"[MCP-SSE] Client disconnected: {session_id}")
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    # Ping / keep-alive comment
                    yield ": keep-alive\n\n"
        finally:
            _active_mcp_sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@mcp_router.post("/messages")
async def mcp_post_message(request: Request, sessionId: Optional[str] = Query(None)):
    """Receives JSON-RPC requests from MCP clients and returns response."""
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}},
        )

    dispatcher = get_dispatcher()
    resp = await dispatcher.handle_request(payload)

    # If associated with an active SSE session queue, push onto queue and return 202
    if sessionId and sessionId in _active_mcp_sessions:
        if resp is not None:
            await _active_mcp_sessions[sessionId].put(resp)
        return Response(status_code=202, content="Accepted")

    # Otherwise return response directly in HTTP response body
    if resp is not None:
        return JSONResponse(content=resp)
    return Response(status_code=204)
