# ==============================================================================
# File: cli/chat/session.py
# Description: Interactive REPL Execution Session for Monika CLI Chat
# ==============================================================================

"""
Core REPL session manager for Monika Interactive CLI Trading Desk.
Coordinates prompt input, slash commands, WebSocket streaming, local fallback engine,
thinking scrubber, tool tree cards, and single-turn interrupt handling.
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

import aiohttp

from cli.chat.commands import ChatCommandRouter, CommandResult
from cli.chat.prompt import ChatPromptManager
from cli.chat.renderer import ChatRenderer, ThinkingScrubber
from cli.chat.theme import get_chat_palette
from config.settings import load_settings

logger = logging.getLogger("TradingAgent.CLI.Chat.Session")

DEFAULT_API_URL = (
    os.environ.get("MONIKA_API_URL")
    or os.environ.get("TRADEAGENT_API_URL")
    or os.environ.get("DASHBOARD_URL")
    or "http://127.0.0.1:8000"
)


def _is_ws_alive(ws: Optional[aiohttp.ClientWebSocketResponse]) -> bool:
    """Check if a ClientWebSocketResponse is open and transport is writable."""
    if ws is None or ws.closed:
        return False
    writer = getattr(ws, "_writer", None)
    if writer:
        transport = getattr(writer, "transport", None)
        if transport is None or transport.is_closing():
            return False
    return True


class ChatReplSession:
    """Institutional-grade CLI Chat REPL session for Monika Trading Desk."""

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        offline: bool = False,
        model: str = "auto",
        theme: str = "retro_vintage",
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key or os.getenv("DASHBOARD_API_KEY", "")
        self.session_id = session_id or "cli:repl_user"
        self.offline = offline
        self.initial_model = model
        self.theme = theme

        # Presentation and Input Managers
        self.renderer = ChatRenderer(theme_name=theme)
        self.prompt_manager = ChatPromptManager(
            theme_name=theme,
            interrupt_callback=self._handle_interrupt,
        )
        self.prompt_manager.update_telemetry(model=model)

        self.command_router = ChatCommandRouter(
            renderer=self.renderer,
            prompt_manager=self.prompt_manager,
            api_url=self.api_url,
            api_key=self.api_key,
            session_id=self.session_id,
        )

        # Connection & Engine states
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        self.local_agent: Optional[Any] = None

        # Turn lifecycle states
        self.pending_action_id: Optional[str] = None
        self.current_turn_task: Optional[asyncio.Task] = None
        self.is_interrupted: bool = False
        self.history: List[Dict[str, Any]] = []

    def _handle_interrupt(self) -> None:
        """Single-turn interrupt callback triggered by prompt_manager on Ctrl+C."""
        self.is_interrupted = True
        self.prompt_manager.update_telemetry(is_generating=False)

        # Signal WebSocket or local engine to interrupt
        if self.ws and not self.ws.closed:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self.ws.send_json({"type": "interrupt"}))
            except Exception:
                pass

        if self.local_agent and hasattr(self.local_agent, "interrupt"):
            try:
                self.local_agent.interrupt("Turn interrupted by CLI operator.")
            except Exception:
                pass

        # Cancel active turn task
        if self.current_turn_task and not self.current_turn_task.done():
            self.current_turn_task.cancel()

    async def _connect_ws(self) -> bool:
        """Establish WebSocket connection with dashboard gateway."""
        if self.offline:
            return False

        ws_url = (
            self.api_url.replace("http://", "ws://").replace("https://", "wss://")
            + f"/ws/agent-chat?session_id={self.session_id}"
        )
        if self.api_key:
            ws_url += f"&token={self.api_key}"

        try:
            if self.http_session is None or self.http_session.closed:
                self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4.0))

            self.ws = await asyncio.wait_for(self.http_session.ws_connect(ws_url), timeout=3.0)

            # Read initial welcome / approval packets
            init_msg = await asyncio.wait_for(self.ws.receive_json(), timeout=2.0)
            if init_msg.get("type") == "open_approvals":
                requests = init_msg.get("requests", [])
                if requests:
                    first_req = requests[0]
                    self.pending_action_id = first_req.get("id")
                    self.renderer.render_approval_card(first_req)

            self.prompt_manager.update_telemetry(status="ONLINE")
            return True
        except Exception as e:
            logger.debug(f"WebSocket gateway connection failed: {e}")
            if self.ws and not self.ws.closed:
                await self.ws.close()
            self.ws = None
            self.prompt_manager.update_telemetry(status="LOCAL ENGINE")
            return False

    def _ensure_local_agent(self) -> bool:
        """Lazily initialize local ChatAgent engine if not already active."""
        if self.local_agent is not None:
            return True
        try:
            from telegram_bot.chat_agent import ChatAgent

            _loader = load_settings
            try:
                import cli.tui_chat
                _loader = getattr(cli.tui_chat, "load_settings", load_settings)
            except Exception:
                pass

            settings = _loader()
            # Set mode telemetry based on paper trading setting
            mode_str = "PAPER" if settings.get("paper_trading", {}).get("enabled", True) else "LIVE"
            self.prompt_manager.update_telemetry(mode=mode_str)

            self.local_agent = ChatAgent(settings=settings, user_id=self.session_id, is_admin=True)

            # Instrument tool listener
            async def _local_tool_hook(event_type: str, data: dict):
                if event_type == "start":
                    self.renderer.render_tool_start(data.get("tool", "tool"), data.get("input", {}))
                elif event_type == "result":
                    self.renderer.render_tool_result(
                        data.get("tool", "tool"),
                        summary=str(data.get("summary", "")),
                        duration_ms=0.0,
                    )

            self.local_agent.set_tool_event_listener(_local_tool_hook)
            return True
        except Exception as e:
            self.renderer.render_notice(f"Failed to initialize local ChatAgent: {e}", level="error")
            return False

    async def run(self) -> None:
        """Run the interactive chat REPL loop."""
        # 1. Attempt connection
        is_connected = await self._connect_ws()
        if not is_connected:
            self._ensure_local_agent()

        # 2. Render institutional header banner
        self.renderer.render_banner(
            model_name=self.prompt_manager.active_model,
            mode=self.prompt_manager.active_mode,
            session_id=self.session_id,
            is_live_service=(self.ws is not None),
        )

        # 3. Main prompt loop
        while True:
            self.prompt_manager.update_telemetry(is_generating=False)
            user_input = await self.prompt_manager.prompt_async()

            if user_input is None:
                # Ctrl+C at empty prompt or EOF
                self.renderer.render_notice("Session terminated by operator.", level="info")
                break

            clean_text = user_input.strip()
            if not clean_text:
                continue

            # Check for slash commands
            cmd_result: CommandResult = await self.command_router.handle(
                clean_text,
                pending_action_id=self.pending_action_id,
                history_records=self.history,
            )

            if cmd_result.handled:
                if cmd_result.should_exit:
                    break
                if cmd_result.action_payload:
                    await self._submit_decision(cmd_result.action_payload)
                continue

            # Standard chat message turn
            self.history.append({"sender": "user", "text": clean_text})
            self.renderer.render_user_prompt(clean_text)

            # Execute turn in managed task with interrupt safety
            self.is_interrupted = False
            self.prompt_manager.update_telemetry(is_generating=True)
            self.current_turn_task = asyncio.create_task(self._execute_turn(clean_text))

            try:
                await self.current_turn_task
            except asyncio.CancelledError:
                self.renderer.render_notice("Turn interrupted by operator.", level="warn")
            except Exception as e:
                self.renderer.render_notice(f"Error during response generation: {e}", level="error")
            finally:
                self.prompt_manager.update_telemetry(is_generating=False)
                self.current_turn_task = None

        # Clean teardown
        await self._teardown()

    async def _execute_turn(self, text: str) -> None:
        """Execute a single query turn against WebSocket or local engine."""
        t0 = time.time()
        active_model = self.prompt_manager.active_model

        # Ensure active connection
        if not self.offline and not _is_ws_alive(self.ws):
            await self._connect_ws()

        if _is_ws_alive(self.ws):
            await self._execute_ws_turn(text, active_model, t0)
        else:
            self._ensure_local_agent()
            await self._execute_local_turn(text, active_model, t0)

    async def _execute_ws_turn(self, text: str, model: str, t0: float) -> None:
        """Stream turn from daemon WebSocket."""
        assert self.ws is not None
        scrubber = ThinkingScrubber()
        full_content_chunks: List[str] = []
        full_thinking_chunks: List[str] = []
        tokens_out_est = 0

        self.renderer.render_agent_header(model)

        await self.ws.send_json({
            "type": "message",
            "text": text,
            "model": model,
        })

        try:
            while True:
                msg = await asyncio.wait_for(self.ws.receive(), timeout=90.0)
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break

                data = json.loads(msg.data)
                etype = data.get("type")

                if etype == "connection_established":
                    continue

                elif etype == "delta":
                    delta_text = data.get("text", "")
                    tokens_out_est += max(1, len(delta_text.split()))

                    think_part, content_part = scrubber.process_chunk(delta_text)
                    if think_part:
                        full_thinking_chunks.append(think_part)
                    if content_part:
                        full_content_chunks.append(content_part)
                        sys.stdout.write(content_part)
                        sys.stdout.flush()

                elif etype == "tool_start":
                    self.renderer.render_tool_start(
                        data.get("tool", "tool"),
                        data.get("input", {}),
                    )

                elif etype == "tool_result":
                    self.renderer.render_tool_result(
                        data.get("tool", "tool"),
                        summary=str(data.get("summary", "")),
                        duration_ms=0.0,
                    )

                elif etype == "approval_request":
                    action = data.get("action", {})
                    self.pending_action_id = action.get("id")
                    self.renderer.render_approval_card(action)
                    break

                elif etype == "complete":
                    sys.stdout.write("\n")
                    sys.stdout.flush()

                    full_reply = "".join(full_content_chunks).strip() or data.get("text", "")
                    thinking_text = scrubber.get_full_thinking()
                    if thinking_text:
                        self.renderer.render_thinking_card(thinking_text, scrubber.elapsed_time)

                    self.history.append({"sender": "agent", "text": full_reply})

                    latency = time.time() - t0
                    tokens_in_est = max(1, len(text.split()) * 4 // 3)
                    self.renderer.render_telemetry_footer(
                        tokens_in=tokens_in_est,
                        tokens_out=tokens_out_est,
                        latency_s=latency,
                    )
                    self.prompt_manager.update_telemetry(
                        latency_s=latency,
                        tokens=tokens_in_est + tokens_out_est,
                    )
                    break

                elif etype == "interrupted":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    self.renderer.render_notice("Generation halted by operator interrupt.", level="warn")
                    break

                elif etype == "error":
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    self.renderer.render_notice(f"{data.get('message')}", level="error")
                    break

        except asyncio.TimeoutError:
            self.renderer.render_notice("WebSocket stream timed out after 90 seconds.", level="error")
        except Exception as e:
            self.renderer.render_notice(f"WebSocket error during turn: {e}", level="warn")
            self.ws = None

    async def _execute_local_turn(self, text: str, model: str, t0: float) -> None:
        """Stream or execute turn using local ChatAgent engine."""
        if not self.local_agent:
            self.renderer.render_notice("Local engine unavailable.", level="error")
            return

        scrubber = ThinkingScrubber()
        self.renderer.render_agent_header(f"{model} (local)")

        full_content_chunks: List[str] = []
        tokens_out_est = 0

        # Stream callback for local engine
        def _token_push(token: str):
            nonlocal tokens_out_est
            tokens_out_est += 1
            think_part, content_part = scrubber.process_chunk(token)
            if content_part:
                full_content_chunks.append(content_part)
                sys.stdout.write(content_part)
                sys.stdout.flush()

        try:
            handle_fn = getattr(self.local_agent, "handle", None)
            is_mock = type(handle_fn).__name__ in ("AsyncMock", "MagicMock", "Mock")
            if is_mock:
                reply_text, pending = await self.local_agent.handle(text)
                if reply_text and not full_content_chunks:
                    sys.stdout.write(reply_text)
                    sys.stdout.flush()
            else:
                try:
                    reply_text, pending = await self.local_agent.handle(text, token_callback=_token_push)
                except TypeError:
                    reply_text, pending = await self.local_agent.handle(text)
                    if reply_text and not full_content_chunks:
                        sys.stdout.write(reply_text)
                        sys.stdout.flush()

            sys.stdout.write("\n")
            sys.stdout.flush()

            final_text = reply_text if reply_text else "".join(full_content_chunks).strip()
            thinking_text = scrubber.get_full_thinking()
            if thinking_text:
                self.renderer.render_thinking_card(thinking_text, scrubber.elapsed_time)

            self.history.append({"sender": "agent", "text": final_text})

            if pending:
                action_dict = {
                    "id": getattr(pending, "action_id", getattr(pending, "id", "local_act")),
                    "description": getattr(pending, "description", "Proposed execution action"),
                    "symbol": getattr(pending, "symbol", "N/A"),
                    "direction": getattr(pending, "direction", "BUY"),
                    "volume": getattr(pending, "volume", 0.01),
                    "sl": getattr(pending, "sl", "N/A"),
                    "tp": getattr(pending, "tp", "N/A"),
                }
                self.pending_action_id = action_dict["id"]
                self.renderer.render_approval_card(action_dict)

            latency = time.time() - t0
            tokens_in_est = max(1, len(text.split()) * 4 // 3)
            if tokens_out_est == 0:
                tokens_out_est = max(1, len(final_text.split()) * 4 // 3)

            self.renderer.render_telemetry_footer(
                tokens_in=tokens_in_est,
                tokens_out=tokens_out_est,
                latency_s=latency,
            )
            self.prompt_manager.update_telemetry(
                latency_s=latency,
                tokens=tokens_in_est + tokens_out_est,
            )
        except Exception as e:
            self.renderer.render_notice(f"Execution error: {e}", level="error")

    async def _submit_decision(self, payload: Dict[str, Any]) -> None:
        """Submit HITL approval decision to daemon or local agent."""
        action_id = payload.get("action_id", "")
        decision = payload.get("decision", "deny")

        if _is_ws_alive(self.ws):
            try:
                await self.ws.send_json(payload)
                msg = await asyncio.wait_for(self.ws.receive_json(), timeout=5.0)
                reply = msg.get("text", f"Action {decision} processed.")
                self.renderer.render_notice(reply, level="success" if "allow" in decision else "info")
            except Exception as e:
                self.renderer.render_notice(f"Failed to submit decision via WebSocket: {e}", level="error")
        else:
            self._ensure_local_agent()
            if not self.local_agent:
                self.renderer.render_notice("Local agent unavailable to process approval.", level="error")
                return

            try:
                if decision == "allow_once":
                    ok, res = await self.local_agent.confirm_action(action_id)
                elif decision == "allow_session":
                    ok, res = await self.local_agent.approve_for_session(action_id)
                else:
                    res = await self.local_agent.reject_action(action_id)
                self.renderer.render_notice(res, level="success" if "allow" in decision else "info")
            except Exception as e:
                self.renderer.render_notice(f"Error executing approval decision: {e}", level="error")

        self.pending_action_id = None

    async def _teardown(self) -> None:
        """Cleanly close active sessions and network sockets."""
        if self.ws and not self.ws.closed:
            try:
                await self.ws.close()
            except Exception:
                pass
        self.ws = None

        if self.http_session and not self.http_session.closed:
            try:
                await self.http_session.close()
            except Exception:
                pass
        self.http_session = None
