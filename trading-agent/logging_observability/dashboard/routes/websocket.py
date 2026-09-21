# ==============================================================================
# File: logging_observability/dashboard/routes/websocket.py
# Description: WebSocket Streaming & Conversation Session Endpoints
# ==============================================================================

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect

from logging_observability.dashboard.rbac import Role, resolve_role, require_role, ROLE_HIERARCHY
from logging_observability.dashboard.routes.common import (
    _active_websockets,
    get_dashboard_dependency,
    get_current_stream_seq,
    get_buffered_events_since,
)
from utils.streaming.stream_scrubber import StatefulStreamScrubber

logger = logging.getLogger("TradingAgent.DashboardAPI.WebSocket")

router = APIRouter()
websocket_router = router


@router.websocket("/ws/live-feed")
async def websocket_live_feed(websocket: WebSocket):
    """Real-time WebSocket stream untuk push updates tick, posisi, dan activity logs with auth verification."""
    token_param = websocket.query_params.get("token") or websocket.query_params.get("api_key")
    auth_header = websocket.headers.get("authorization", "")
    bearer_key = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
    client_key = token_param or websocket.headers.get("x-api-key") or bearer_key or ""
    client_host = websocket.client.host if websocket.client else "127.0.0.1"
    is_localhost = client_host in ("127.0.0.1", "::1", "localhost", "testclient")

    role = None
    authenticated = False

    if token_param:
        logger.warning("[Dashboard WS] DeprecationWarning: Query parameter auth ('?token=...') is deprecated. Use initial handshake message {'type': 'authenticate', 'token': '...'}")

    try:
        role = resolve_role(str(client_key), is_localhost=is_localhost)
        authenticated = True
    except PermissionError:
        if client_key:
            logger.warning(f"[Dashboard WS] Unauthorized connection attempt from {client_host}")
            await websocket.close(code=1008, reason="Unauthorized: Invalid API key")
            return
        authenticated = False

    await websocket.accept()

    if not authenticated:
        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            auth_msg = json.loads(raw_auth)
            if auth_msg.get("type") == "authenticate":
                token = auth_msg.get("token") or auth_msg.get("api_key") or ""
                role = resolve_role(str(token), is_localhost=is_localhost)
                authenticated = True
            else:
                await websocket.close(code=1008, reason="Unauthorized: Expected authenticate message")
                return
        except (asyncio.TimeoutError, json.JSONDecodeError, PermissionError) as auth_err:
            logger.warning(f"[Dashboard WS] Handshake auth failed from {client_host}: {auth_err}")
            await websocket.close(code=1008, reason="Unauthorized: Authentication handshake failed")
            return

    _active_websockets.add(websocket)
    try:
        current_seq = get_current_stream_seq()
        await websocket.send_json({
            "type": "connection_established",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "connected",
            "seq": current_seq,
            "as_of_seq": current_seq,
        })

        # Replay catch-up on reconnect if since_seq was provided via query param
        since_raw = websocket.query_params.get("since_seq") or websocket.query_params.get("last_seq")
        if since_raw:
            try:
                since_seq = int(since_raw)
                missed_events = get_buffered_events_since(since_seq)
                for ev in missed_events:
                    await websocket.send_json(ev)
            except (ValueError, TypeError):
                pass

        try:
            from risk.approval_hub import ApprovalHub
            open_reqs = ApprovalHub.get_instance().get_open_requests()
            if open_reqs:
                await websocket.send_json({
                    "type": "open_approvals",
                    "requests": open_reqs,
                    "seq": get_current_stream_seq(),
                    "as_of_seq": get_current_stream_seq(),
                })
        except Exception:
            pass

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
            elif data:
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "authenticate":
                        await websocket.send_json({"type": "authenticated", "role": role.value if role else "viewer"})
                    elif msg.get("type") in ("replay", "catch_up", "sync"):
                        since_seq = msg.get("since_seq") or msg.get("last_seq") or 0
                        missed = get_buffered_events_since(int(since_seq))
                        await websocket.send_json({
                            "type": "replay_batch",
                            "events": missed,
                            "count": len(missed),
                            "as_of_seq": get_current_stream_seq(),
                        })
                    elif msg.get("type") == "steer":
                        text = msg.get("message") or (msg.get("payload", {}).get("message") if isinstance(msg.get("payload"), dict) else None)
                        symbol = msg.get("symbol") or "ALL"
                        if text:
                            from risk.approval_hub import ApprovalHub
                            operator_tag = f"ws:{role.value if role else 'client'}"
                            steer_res = await ApprovalHub.get_instance().steer(symbol, str(text), operator=operator_tag)
                            await websocket.send_json({"type": "steer_acknowledged", **steer_res})
                    elif msg.get("type") in ("approve", "approval_approve"):
                        req_id = msg.get("request_id") or msg.get("action_id")
                        operator_tag = f"ws:{role.value if role else 'client'}"
                        from risk.approval_hub import ApprovalHub
                        ok, res_str = await ApprovalHub.get_instance().approve(str(req_id), operator=operator_tag)
                        await websocket.send_json({"type": "approval_result", "request_id": req_id, "success": ok, "message": res_str})
                    elif msg.get("type") in ("reject", "approval_reject"):
                        req_id = msg.get("request_id") or msg.get("action_id")
                        reason = msg.get("reason", "")
                        operator_tag = f"ws:{role.value if role else 'client'}"
                        from risk.approval_hub import ApprovalHub
                        ok, res_str = await ApprovalHub.get_instance().reject(str(req_id), operator=operator_tag, reason=reason)
                        await websocket.send_json({"type": "approval_result", "request_id": req_id, "success": ok, "message": res_str})
                except Exception:
                    pass
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _active_websockets.discard(websocket)
class TokenCoalescingBuffer:
    """
    High-performance 30 FPS (~33ms flush interval) token coalescing stream buffer.
    Coalesces incoming fine-grained tokens/chunks and safely strips reasoning blocks
    and credentials via StatefulStreamScrubber before dispatching over WebSocket.
    """
    def __init__(
        self,
        websocket: WebSocket,
        flush_interval: float = 0.033,
        max_buffer_chars: int = 120,
        scrub: bool = True,
    ):
        self.websocket = websocket
        self.flush_interval = flush_interval
        self.max_buffer_chars = max_buffer_chars
        self._buffer: list[str] = []
        self._buffer_len: int = 0
        self._last_flush: float = 0.0
        self.has_streamed: bool = False
        self.scrubber: Optional[StatefulStreamScrubber] = StatefulStreamScrubber() if scrub else None

    async def push(self, token: str):
        if not token:
            return
        if self.scrubber is not None:
            token = self.scrubber.process_delta(token)
            if not token:
                return
        self.has_streamed = True
        self._buffer.append(token)
        self._buffer_len += len(token)
        now = asyncio.get_event_loop().time()

        should_flush = (
            self._buffer_len >= self.max_buffer_chars
            or (self._buffer_len > 0 and (now - self._last_flush) >= self.flush_interval)
            or ("\n" in token)
        )
        if should_flush:
            await self.flush()

    async def flush(self, final: bool = False):
        if final and self.scrubber is not None:
            trailing = self.scrubber.flush()
            if trailing:
                self._buffer.append(trailing)
                self._buffer_len += len(trailing)

        if not self._buffer:
            return
        chunk = "".join(self._buffer)
        self._buffer.clear()
        self._buffer_len = 0
        self._last_flush = asyncio.get_event_loop().time()
        try:
            await self.websocket.send_json({"type": "delta", "text": chunk})
        except Exception:
            pass

    async def stream_text(self, text: str):
        """Streams text smoothly through the coalescing buffer at ~30 FPS."""
        tokens = re.findall(r'\S+|\s+', text)
        for tok in tokens:
            await self.push(tok)
            now = asyncio.get_event_loop().time()
            if (now - self._last_flush) >= self.flush_interval:
                await self.flush()
                await asyncio.sleep(self.flush_interval)
        await self.flush(final=True)



@router.websocket("/ws/agent-chat")
async def websocket_agent_chat(websocket: WebSocket):
    """Bidirectional streaming chat with Trading Agent for dashboard."""
    token_param = websocket.query_params.get("token") or websocket.query_params.get("api_key")
    auth_header = websocket.headers.get("authorization", "")
    bearer_key = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
    client_key = token_param or websocket.headers.get("x-api-key") or bearer_key or ""
    client_host = websocket.client.host if websocket.client else "127.0.0.1"
    is_localhost = client_host in ("127.0.0.1", "::1", "localhost", "testclient")

    role = None
    authenticated = False

    if token_param:
        logger.warning("[AgentChat WS] DeprecationWarning: Query parameter auth ('?token=...') is deprecated. Use initial handshake message {'type': 'authenticate', 'token': '...'}")

    try:
        role = resolve_role(str(client_key), is_localhost=is_localhost)
        authenticated = True
    except PermissionError as e:
        if client_key:
            logger.warning(f"[AgentChat WS] Unauthorized attempt from {client_host}: {e}")
            await websocket.close(code=1008, reason="Unauthorized: Invalid API key")
            return
        authenticated = False

    await websocket.accept()

    if not authenticated:
        try:
            raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
            auth_msg = json.loads(raw_auth)
            if auth_msg.get("type") == "authenticate":
                token = auth_msg.get("token") or auth_msg.get("api_key") or ""
                role = resolve_role(str(token), is_localhost=is_localhost)
                authenticated = True
            else:
                await websocket.close(code=1008, reason="Unauthorized: Expected authenticate message")
                return
        except (asyncio.TimeoutError, json.JSONDecodeError, PermissionError) as auth_err:
            logger.warning(f"[AgentChat WS] Handshake auth failed from {client_host}: {auth_err}")
            await websocket.close(code=1008, reason="Unauthorized: Authentication handshake failed")
            return

    session_id = websocket.query_params.get("session_id") or f"dash:{role.value if role else 'unknown'}"
    await websocket.send_json({
        "type": "connection_established",
        "role": role.value if role else "viewer",
        "session_id": session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    try:
        from risk.approval_hub import ApprovalHub
        open_reqs = ApprovalHub.get_instance().get_open_requests()
        if open_reqs:
            await websocket.send_json({
                "type": "open_approvals",
                "requests": open_reqs,
            })
    except Exception:
        pass

    from config.settings import load_settings
    raw_settings = get_dashboard_dependency("settings") or load_settings()
    settings: dict = dict(raw_settings) if isinstance(raw_settings, dict) else raw_settings.model_dump()
    from telegram_bot.chat_agent import ChatAgent
    agent = ChatAgent(settings=settings, user_id=session_id, is_admin=(role == Role.ADMIN))

    tools_used: list[str] = []

    async def tool_event_hook(event_type: str, data: dict):
        if event_type == "start":
            tool_name = data.get("tool", "")
            if tool_name not in tools_used:
                tools_used.append(tool_name)
            await websocket.send_json({
                "type": "tool_start",
                "tool": tool_name,
                "input": data.get("input", {}),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif event_type == "result":
            await websocket.send_json({
                "type": "tool_result",
                "tool": data.get("tool", ""),
                "summary": data.get("summary", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    agent.set_tool_event_listener(tool_event_hook)

    turn_task: Optional[asyncio.Task] = None

    try:
        while True:
            raw_data = await websocket.receive_text()
            if raw_data == "ping":
                await websocket.send_text("pong")
                continue

            try:
                msg = json.loads(raw_data)
            except Exception:
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})
                continue

            event_type = msg.get("type", "message")

            if event_type == "authenticate":
                token = msg.get("token") or msg.get("api_key") or ""
                try:
                    role = resolve_role(str(token), is_localhost=is_localhost)
                    agent.is_admin = (role == Role.ADMIN)
                    await websocket.send_json({"type": "authenticated", "role": role.value})
                except PermissionError:
                    await websocket.send_json({"type": "error", "message": "Invalid authentication token"})
                continue

            if event_type == "interrupt":
                interrupted = agent.interrupt("Turn interrupted by dashboard user.")
                if turn_task and not turn_task.done():
                    turn_task.cancel()
                await websocket.send_json({
                    "type": "interrupted",
                    "success": interrupted,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue

            elif event_type == "approval_response":
                user_role_level = ROLE_HIERARCHY.get(role, 0) if role is not None else 0
                if user_role_level < ROLE_HIERARCHY.get(Role.OPERATOR, 1):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Forbidden: Approving or denying actions requires Operator or Admin role.",
                    })
                    continue

                action_id = msg.get("action_id", "")
                decision = str(msg.get("decision", "")).lower()
                operator_tag = f"ws:{role.value if role else 'client'}"

                try:
                    from risk.approval_hub import ApprovalHub
                    if decision in ("allow_once", "allow_session"):
                        await ApprovalHub.get_instance().approve(action_id, operator=operator_tag)
                    elif decision in ("deny", "reject"):
                        await ApprovalHub.get_instance().reject(action_id, operator=operator_tag, reason=str(msg.get("reason", "")))
                except Exception:
                    pass

                if decision == "allow_once":
                    ok, res_text = await agent.confirm_action(action_id)
                    await websocket.send_json({
                        "type": "complete",
                        "text": res_text,
                        "action_id": action_id,
                        "status": "approved" if ok else "failed",
                    })
                elif decision == "allow_session":
                    ok, res_text = await agent.approve_for_session(action_id)
                    await websocket.send_json({
                        "type": "complete",
                        "text": res_text,
                        "action_id": action_id,
                        "status": "session_approved" if ok else "failed",
                    })
                elif decision in ("deny", "reject"):
                    res_text = await agent.reject_action(action_id)
                    await websocket.send_json({
                        "type": "complete",
                        "text": res_text,
                        "action_id": action_id,
                        "status": "denied",
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown decision '{decision}'. Use allow_once, allow_session, or deny.",
                    })
                continue

            elif event_type == "message":
                user_role_level = ROLE_HIERARCHY.get(role, 0) if role is not None else 0
                if user_role_level < ROLE_HIERARCHY.get(Role.OPERATOR, 1):
                    await websocket.send_json({
                        "type": "error",
                        "message": "Forbidden: Sending messages to the chat agent requires Operator or Admin role.",
                    })
                    continue

                if turn_task and not turn_task.done():
                    await websocket.send_json({
                        "type": "error",
                        "message": "Agent is currently busy processing another message. Please wait or interrupt.",
                    })
                    continue

                text = msg.get("text", "").strip()
                if not text:
                    continue

                model_pref = msg.get("model", "auto")
                processed_text = text
                if model_pref in ("fast", "tier_lite") and not text.startswith("/"):
                    processed_text = f"/fast {text}"
                elif model_pref in ("deep_research", "research") and not text.startswith("/"):
                    processed_text = f"/research {text}"
                elif model_pref in ("medium", "tier_medium") and not text.startswith("/"):
                    processed_text = f"/medium {text}"
                elif model_pref in ("complex", "tier_deep") and not text.startswith("/"):
                    processed_text = f"/analyze {text}"

                tools_used.clear()

                async def _run_chat_turn(input_text: str):
                    try:
                        coalescer = TokenCoalescingBuffer(websocket, flush_interval=0.033)
                        try:
                            reply_text, pending = await agent.handle(input_text, token_callback=coalescer.push)
                        except TypeError:
                            reply_text, pending = await agent.handle(input_text)

                        if "Turn interrupted" in reply_text:
                            return

                        if not coalescer.has_streamed:
                            await coalescer.stream_text(reply_text)
                        else:
                            await coalescer.flush(final=True)

                        sanitized_reply = StatefulStreamScrubber.scrub_text(reply_text)
                        await websocket.send_json({
                            "type": "complete",
                            "text": sanitized_reply,
                            "tools_used": list(tools_used),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                        if pending:
                            await websocket.send_json({
                                "type": "approval_request",
                                "action": pending.to_dict(),
                                "expires_in": 90,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            })
                    except asyncio.CancelledError:
                        pass
                    except Exception as err:
                        logger.error(f"[AgentChat WS] Error during turn: {err}", exc_info=True)
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Agent error: {str(err)}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                turn_task = asyncio.create_task(_run_chat_turn(processed_text))

    except WebSocketDisconnect:
        logger.info(f"[AgentChat WS] Disconnected {session_id}")
        if turn_task and not turn_task.done():
            turn_task.cancel()
    except Exception as e:
        logger.debug(f"[AgentChat WS] Session error: {e}")


@router.get("/api/sessions", tags=["Sessions"])
@require_role(Role.VIEWER)
async def list_sessions(
    request: Request,
    source: Optional[str] = Query(default=None, description="'telegram' or 'dashboard'"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List conversation sessions with message counts, activity times, and preview."""
    from database.db import AsyncSessionLocal
    from database.models import TelegramConversation
    from sqlalchemy import select, func, desc

    async with AsyncSessionLocal() as session:
        query = (
            select(
                TelegramConversation.telegram_user_id,
                func.count(TelegramConversation.id).label("message_count"),
                func.max(TelegramConversation.timestamp).label("last_active"),
                func.min(TelegramConversation.timestamp).label("first_active"),
            )
            .group_by(TelegramConversation.telegram_user_id)
            .order_by(desc("last_active"))
            .limit(limit)
        )

        if source == "dashboard":
            query = query.where(TelegramConversation.telegram_user_id.like("dash%"))
        elif source == "telegram":
            query = query.where(~TelegramConversation.telegram_user_id.like("dash%"))

        rows = (await session.execute(query)).all()

        results = []
        for row in rows:
            uid = row.telegram_user_id
            latest = (await session.execute(
                select(TelegramConversation.message, TelegramConversation.role)
                .where(TelegramConversation.telegram_user_id == uid)
                .order_by(TelegramConversation.timestamp.desc())
                .limit(1)
            )).first()

            results.append({
                "session_id": uid,
                "source": "dashboard" if uid.startswith("dash") else "telegram",
                "message_count": row.message_count,
                "last_active": row.last_active.isoformat() if row.last_active else None,
                "first_active": row.first_active.isoformat() if row.first_active else None,
                "last_message": latest.message[:120] if latest else "",
                "last_role": latest.role if latest else "",
            })
        return results


@router.get("/api/sessions/{session_id}/messages", tags=["Sessions"])
@require_role(Role.VIEWER)
async def get_session_messages(
    session_id: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
):
    """Retrieve conversation transcript for a given session."""
    from database.db import AsyncSessionLocal
    from database.models import TelegramConversation
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        stmt = (
            select(TelegramConversation)
            .where(TelegramConversation.telegram_user_id == session_id)
            .order_by(TelegramConversation.timestamp.asc())
            .limit(limit)
        )
        msgs = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": m.id,
                "session_id": m.telegram_user_id,
                "role": m.role,
                "message": m.message,
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
            }
            for m in msgs
        ]
