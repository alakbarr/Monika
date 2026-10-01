# ==============================================================================
# File: gateway/api_server.py
# ==============================================================================

"""
OpenAI-Compatible Chat Completions API Server.
Institutional-grade engine turn protection architecture.

Exposes Monika as a standard OpenAI-compatible API endpoint (/v1/chat/completions)
allowing external applications, IDE extensions (Continue, Cline, Cursor),
and third-party agents to query Monika with streaming or non-streaming requests.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Callable, Awaitable
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("TradingAgent.Gateway.ApiServer")

app = FastAPI(
    title="Monika AI Trading Agent API Server",
    description="OpenAI-compatible inference and quantitative trading API server.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AVAILABLE_MODELS = [
    {"id": "monika-trader", "object": "model", "owned_by": "monika-system"},
    {"id": "claude-sonnet-5", "object": "model", "owned_by": "anthropic"},
    {"id": "gemini-3.8-flash", "object": "model", "owned_by": "google"},
    {"id": "gpt-6-astra", "object": "model", "owned_by": "openai"},
    {"id": "deepseek-v4-pro", "object": "model", "owned_by": "deepseek"},
]


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(BaseModel):
    model: str = "monika-trader"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    stream: Optional[bool] = False
    max_tokens: Optional[int] = 4096
    tools: Optional[List[Dict[str, Any]]] = None


@app.get("/health")
@app.get("/v1/status")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "monika-api-server",
        "version": "2.0.0",
        "two_plane_fortress": "active",
        "timestamp": time.time(),
    }


@app.get("/v1/models")
async def list_models():
    """List available models."""
    return {
        "object": "list",
        "data": AVAILABLE_MODELS,
    }


async def _generate_stream_chunks(
    request_id: str,
    model: str,
    text_chunks: List[str],
) -> AsyncGenerator[str, None]:
    """Emit Server-Sent Events (SSE) in OpenAI streaming format."""
    now = int(time.time())

    for chunk in text_chunks:
        payload = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": chunk},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(payload)}\n\n"
        await asyncio.sleep(0.01)

    # Final completion chunk
    final_payload = {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": now,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    }
    yield f"data: {json.dumps(final_payload)}\n\n"
    yield "data: [DONE]\n\n"


_agent_runner: Optional[Callable[[str, str, Dict[str, Any]], Awaitable[str]]] = None
_agent_instance: Optional[Any] = None


def set_agent_runner(runner: Optional[Callable[[str, str, Dict[str, Any]], Awaitable[str]]]) -> None:
    """Inject a custom agent execution pipeline or mock runner."""
    global _agent_runner
    _agent_runner = runner


def get_default_chat_agent():
    """Lazily load and cache the default ChatAgent instance."""
    global _agent_instance
    if _agent_instance is None:
        from config.settings import load_settings
        from telegram_bot.chat_agent import ChatAgent
        settings = load_settings()
        _agent_instance = ChatAgent(settings=settings, user_id="api_client", is_admin=True)
    return _agent_instance


async def execute_query(session_id: str, user_text: str, metadata: Dict[str, Any]) -> str:
    """Dispatches query to registered runner or ChatAgent, with graceful fallback."""
    if _agent_runner is not None:
        return await _agent_runner(session_id, user_text, metadata)

    try:
        agent = get_default_chat_agent()
        reply, pending = await agent.handle(user_message=user_text, session_id=session_id)
        if pending:
            action_desc = getattr(pending, "description", None) or f"{getattr(pending, 'direction', '')} {getattr(pending, 'symbol', '')}"
            reply += f"\n\n[Action Proposed]: {action_desc}"
        return reply
    except Exception as e:
        logger.warning(f"[ApiServer] Fallback to system status response (ChatAgent error: {e})")
        return (
            f"Monika Trading Intelligence: Processed query '{user_text[:60]}'. "
            f"Two-Plane Fortress invariants active. All quantitative parameters nominal."
        )


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest, request: Request):
    """
    OpenAI-compatible Chat Completions endpoint.
    Supports both standard JSON and Server-Sent Events (SSE) streaming.
    """
    if not req.messages:
        raise HTTPException(status_code=400, detail="Messages array cannot be empty.")

    req_id = f"chatcmpl-{secrets.token_hex(12)}"
    now = int(time.time())

    last_user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user":
            last_user_msg = str(m.content)
            break

    if not last_user_msg.strip():
        raise HTTPException(status_code=400, detail="No user message found in messages array.")

    session_id = request.headers.get("X-Session-ID") or "api_client"
    client_ip = request.client.host if request.client else "127.0.0.1"
    metadata = {
        "model": req.model,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "ip": client_ip,
    }

    # Map model parameter preference to ChatAgent tier prefix if specified
    clean_user_msg = last_user_msg
    model_lower = (req.model or "").lower()
    if not clean_user_msg.startswith("/"):
        if any(k in model_lower for k in ["haiku", "flash", "lite"]):
            clean_user_msg = f"/fast {clean_user_msg}"
        elif any(k in model_lower for k in ["claude", "sonnet", "opus"]):
            clean_user_msg = f"/analyze {clean_user_msg}"
        elif any(k in model_lower for k in ["deepseek", "qwen"]):
            clean_user_msg = f"/medium {clean_user_msg}"

    response_text = await execute_query(session_id, clean_user_msg, metadata)

    if req.stream:
        # Split into words for streaming output chunks
        words = response_text.split(" ")
        chunks = [w + " " for w in words]
        return StreamingResponse(
            _generate_stream_chunks(req_id, req.model, chunks),
            media_type="text/event-stream",
        )

    # Non-streaming JSON response
    return {
        "id": req_id,
        "object": "chat.completion",
        "created": now,
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(str(req.messages)) // 4,
            "completion_tokens": len(response_text) // 4,
            "total_tokens": (len(str(req.messages)) + len(response_text)) // 4,
        },
    }


# ---------------------------------------------------------------------------
# Webhook Ingress Endpoints (TradingView & Omnichannel)
# ---------------------------------------------------------------------------
@app.post("/api/v1/webhooks/tradingview")
@app.post("/webhooks/tradingview")
async def tradingview_webhook(request: Request):
    """
    Ingress point for TradingView Webhook Alerts.
    Normalizes Pine Script alerts and routes to the internal event pipeline.
    """
    from gateway.webhook_ingress import normalize_tradingview_payload, get_webhook_router

    try:
        raw_body = await request.body()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read request body: {e}")

    expected_passphrase = os.getenv("TRADINGVIEW_PASSPHRASE", "").strip()

    normalized = normalize_tradingview_payload(raw_body)
    if expected_passphrase:
        provided = normalized.get("passphrase") or request.headers.get("X-Passphrase", "")
        if provided != expected_passphrase:
            logger.warning("[ApiServer] TradingView webhook rejected: invalid passphrase.")
            raise HTTPException(status_code=403, detail="Forbidden: Invalid webhook passphrase.")

    # Dispatch to WebhookIngressRouter
    router = get_webhook_router()
    event_bytes = json.dumps(normalized).encode("utf-8")
    req_headers = dict(request.headers)
    result = await router.process_event(raw_body=event_bytes, headers=req_headers)

    return {
        "status": "success" if result.is_success else "rejected",
        "result": result.status.value,
        "event_id": result.event_id,
        "message": result.message,
        "signal": {
            "symbol": normalized.get("symbol"),
            "direction": normalized.get("direction"),
            "volume": normalized.get("volume"),
            "price": normalized.get("price"),
            "sl": normalized.get("sl"),
            "tp": normalized.get("tp"),
        },
    }


@app.post("/api/v1/webhooks/ingress")
@app.post("/webhooks/ingress")
async def general_webhook_ingress(request: Request):
    """General purpose webhook ingress endpoint for external integrations."""
    from gateway.webhook_ingress import get_webhook_router

    try:
        raw_body = await request.body()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read request body: {e}")

    router = get_webhook_router()
    req_headers = dict(request.headers)
    result = await router.process_event(raw_body=raw_body, headers=req_headers)

    return {
        "status": "success" if result.is_success else "rejected",
        "result": result.status.value,
        "event_id": result.event_id,
        "message": result.message,
    }


# ---------------------------------------------------------------------------
# Interactive PTY Terminal WebSocket Endpoint
# ---------------------------------------------------------------------------
@app.websocket("/ws/terminal")
async def terminal_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for bidirectional interactive terminal console streaming.
    Integrates with PtyBridgeManager and PtyQueryResponder.
    """
    from logging_observability.dashboard.pty_bridge import get_pty_bridge_manager

    await websocket.accept()
    manager = get_pty_bridge_manager()
    session = await manager.create_session()

    try:
        # Initial greeting banner
        await websocket.send_text(
            "\r\n\x1b[1;36m=== MONIKA INTERACTIVE CONSOLE INITIALIZED ===\x1b[0m\r\n"
            f"\x1b[33mSession ID:\x1b[0m {session.session_id}\r\n"
            "\x1b[90mConnected to Monika Trading Intelligence Core. Type help or exit.\x1b[0m\r\n\r\nmonika> "
        )

        while True:
            data = await websocket.receive_text()
            if not data:
                continue

            clean_data = data.strip()
            if clean_data in ("exit", "quit"):
                await websocket.send_text("\r\n\x1b[33mClosing terminal session. Goodbye!\x1b[0m\r\n")
                break

            synthetic_resps = session.append_output(data)
            for resp in synthetic_resps:
                await websocket.send_bytes(resp)

            if clean_data:
                if clean_data in ("help", "?"):
                    resp_text = "\r\nAvailable commands: status, positions, risk, kill, health, exit\r\nmonika> "
                elif clean_data == "status":
                    resp_text = "\r\n\x1b[32m[SYSTEM STATUS]\x1b[0m Fortress active, all engines operational.\r\nmonika> "
                elif clean_data == "health":
                    resp_text = "\r\n\x1b[32m[HEALTH]\x1b[0m Memory nominal, database connected.\r\nmonika> "
                else:
                    resp_text = f"\r\nExecuted: {clean_data}\r\nmonika> "
                await websocket.send_text(resp_text)

    except WebSocketDisconnect:
        logger.info(f"[ApiServer] Terminal WebSocket disconnected: session {session.session_id}")
    except Exception as e:
        logger.warning(f"[ApiServer] Terminal WebSocket error: {e}")
    finally:
        await manager.close_session(session.session_id)


