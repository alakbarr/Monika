# ==============================================================================
# File: cli/tui_chat.py
# ==============================================================================

"""
Interactive REPL Chat Screen and Standalone CLI Chat for AI Trading Agent.

Features:
- ChatScreen: Interactive full-screen Textual Screen overlay within TUI dashboard
- run_cli_chat: Standalone CLI REPL chat mode using prompt_toolkit and Rich
- Streaming token-by-token response generation
- Tool execution indicators (tool_start, tool_result)
- HITL action approval handling (allow_once, allow_session, deny)
- Connects to /ws/agent-chat WebSocket or local ChatAgent engine
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypeGuard

import aiohttp
from rich.console import Console
from rich.markdown import Markdown
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, RichLog, Static

from config.settings import load_settings
from cli.theme import (
    build_chat_css,
    get_console,
    PHOSPHOR_AMBER,
    BRASS,
    BULL_PROFIT,
    BEAR_LOSS,
    MUTED,
    PAPER,
    stamp_ok,
    stamp_err,
    stamp_warn,
    stamp_exec,
    stamp_info,
)

logger = logging.getLogger("TradingAgent.TUI.Chat")

DEFAULT_API_URL = os.environ.get("MONIKA_API_URL") or os.environ.get("TRADEAGENT_API_URL") or os.environ.get("DASHBOARD_URL") or "http://127.0.0.1:8000"

CHAT_SCREEN_CSS = build_chat_css()


def is_ws_alive(ws: Optional[aiohttp.ClientWebSocketResponse]) -> TypeGuard[aiohttp.ClientWebSocketResponse]:
    """Check if a ClientWebSocketResponse is fully alive and underlying transport is open."""
    if ws is None or ws.closed:
        return False
    writer = getattr(ws, "_writer", None)
    if writer:
        transport = getattr(writer, "transport", None)
        if transport is None or transport.is_closing():
            return False
    return True


class ChatScreen(Screen):
    """
    Full-screen interactive chat REPL within Textual TUI.

    Connects to /ws/agent-chat for streaming responses, or falls back to
    direct ChatAgent execution if the dashboard server is offline.
    """

    CSS = CHAT_SCREEN_CSS
    TITLE = "Monika — Interactive Chat"

    BINDINGS = [
        Binding("escape", "back", "Back to Dashboard", show=True),
        Binding("ctrl+c", "interrupt", "Interrupt Turn", show=True),
        Binding("ctrl+l", "clear_transcript", "Clear Transcript", show=True),
    ]

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key or os.getenv("DASHBOARD_API_KEY", "")
        self.session_id = session_id or "cli:tui_user"

        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._pending_action_id: Optional[str] = None
        self._is_generating = False
        self._local_agent: Optional[Any] = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(
            f"[bold {PHOSPHOR_AMBER}][ DESK CONSOLE ][/] Monika Quantitative Assistant  │  "
            f"Model: [{BRASS}]Dynamic Routing[/]  │  "
            f"[dim {MUTED}]Press [bold {PAPER}]ESC[/] to return to Dashboard[/]",
            id="chat_header",
        )
        yield RichLog(id="transcript", wrap=True, highlight=True, markup=True)
        yield Static("", id="streaming_output")
        yield Input(
            id="chat_input",
            placeholder="Enter query or directive (e.g. /fast EURUSD, /analyze XAUUSD)...",
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize chat transcript and attempt WebSocket connection."""
        transcript = self.query_one("#transcript", RichLog)
        transcript.write(f"[bold {PHOSPHOR_AMBER}][ STATUS ][/] Monika Interactive Trading Desk Ready")
        transcript.write(
            f"[dim {MUTED}]Instructions: Enter analytical inquiries or execution directives. Use [bold {PAPER}]/allow[/] or [bold {PAPER}]/deny[/] "
            f"for HITL order authorization. Press [bold {PAPER}]ESC[/] to return.[/]\n"
        )

        # Attempt WS connection
        await self._connect_ws()

    def _is_ws_healthy(self) -> bool:
        """Check if active WebSocket is open and transport is writable."""
        return is_ws_alive(self._ws)

    async def _close_ws(self) -> None:
        """Cleanly close active WebSocket and HTTP session without transport leaks."""
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        if self._session and not self._session.closed:
            try:
                await self._session.close()
            except Exception:
                pass
        self._session = None

    async def on_unmount(self) -> None:
        """Cleanup WebSocket connections."""
        await self._close_ws()

    async def _connect_ws(self) -> bool:
        """Connect to /ws/agent-chat endpoint and consume initial handshake greeting."""
        await self._close_ws()
        ws_url = self.api_url.replace("http://", "ws://").replace("https://", "wss://") + f"/ws/agent-chat?session_id={self.session_id}"
        if self.api_key:
            ws_url += f"&token={self.api_key}"

        try:
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(ws_url)
            # Consume initial connection_established greeting
            try:
                await self._ws.receive(timeout=2.0)
            except Exception:
                pass
            transcript = self.query_one("#transcript", RichLog)
            transcript.write("[dim green]✔ Connected to live streaming Agent WebSocket engine.[/]\n")
            return True
        except Exception:
            await self._close_ws()
            transcript = self.query_one("#transcript", RichLog)
            transcript.write("[dim yellow]ℹ Dashboard server not active. Operating in standalone local mode.[/]\n")
            return False

    async def _ensure_ws(self) -> bool:
        """Ensure WebSocket connection is healthy, reconnecting if stale, idle-closed, or dead."""
        if self._is_ws_healthy():
            return True
        return await self._connect_ws()

    async def action_back(self) -> None:
        """Return to main dashboard."""
        self.app.pop_screen()

    async def action_interrupt(self) -> None:
        """Interrupt currently executing LLM turn."""
        transcript = self.query_one("#transcript", RichLog)
        ws = self._ws
        if ws is not None and is_ws_alive(ws):
            try:
                await ws.send_json({"type": "interrupt"})
                transcript.write("[bold yellow]🛑 Sent interrupt signal to agent.[/]")
                return
            except Exception as e:
                logger.warning(f"[TUI Chat] Failed sending WS interrupt: {e}")
        if self._local_agent:
            self._local_agent.interrupt("Turn interrupted by user.")
            transcript.write("[bold yellow]🛑 Interrupted local agent turn.[/]")

    async def action_clear_transcript(self) -> None:
        """Clear transcript messages."""
        transcript = self.query_one("#transcript", RichLog)
        transcript.clear()
        transcript.write("[dim]Transcript cleared.[/]\n")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input in chat screen with crash-proof guard."""
        text = event.value.strip()
        event.input.value = ""
        if not text or self._is_generating:
            return

        transcript = self.query_one("#transcript", RichLog)
        transcript.write(f"[bold green]You:[/] {text}")

        # Check for approval shortcuts
        if self._pending_action_id:
            if text.lower() in ("/allow", "/yes", "allow", "yes"):
                await self._handle_approval_decision(self._pending_action_id, "allow_once")
                return
            elif text.lower() in ("/session", "allow_session"):
                await self._handle_approval_decision(self._pending_action_id, "allow_session")
                return
            elif text.lower() in ("/deny", "/no", "deny", "no"):
                await self._handle_approval_decision(self._pending_action_id, "deny")
                return

        # Execute turn safely
        self._is_generating = True
        try:
            if self._is_ws_healthy() or await self._ensure_ws():
                await self._run_ws_turn(text)
            else:
                await self._run_local_turn(text)
        except Exception as e:
            logger.error(f"[TUI Chat] Error in turn execution: {e}", exc_info=True)
            transcript.write(f"[bold red]❌ Failed to process request:[/] {e}\n")
        finally:
            self._is_generating = False

    async def _handle_approval_decision(self, action_id: str, decision: str) -> None:
        transcript = self.query_one("#transcript", RichLog)
        transcript.write(f"[dim]Submitting decision [bold white]{decision}[/] for action {action_id}...[/]")

        if (self._is_ws_healthy() or await self._ensure_ws()) and self._ws is not None:
            ws = self._ws
            try:
                await ws.send_json({
                    "type": "approval_response",
                    "action_id": action_id,
                    "decision": decision,
                })
                self._pending_action_id = None
                return
            except Exception as e:
                logger.warning(f"[TUI Chat] WS approval send error: {e}")

        if self._local_agent:
            if decision == "allow_once":
                ok, res = await self._local_agent.confirm_action(action_id)
            elif decision == "allow_session":
                ok, res = await self._local_agent.approve_for_session(action_id)
            else:
                res = await self._local_agent.reject_action(action_id)
            transcript.write(f"[bold cyan]Agent:[/] {res}\n")
            self._pending_action_id = None

    async def _run_ws_turn(self, text: str) -> None:
        """Send message via WebSocket with auto-reconnect retry and local fallback."""
        transcript = self.query_one("#transcript", RichLog)

        if not await self._ensure_ws() or self._ws is None:
            transcript.write("[dim yellow]ℹ WebSocket disconnected. Falling back to local engine...[/]\n")
            await self._run_local_turn(text)
            return

        ws = self._ws
        # Attempt send with auto-reconnect retry
        try:
            await ws.send_json({"type": "message", "text": text})
        except (aiohttp.ClientError, ConnectionResetError, OSError) as send_err:
            logger.warning(f"[TUI Chat] WebSocket send error ({send_err}), reconnecting...")
            if await self._connect_ws() and self._ws is not None:
                ws = self._ws
                try:
                    await ws.send_json({"type": "message", "text": text})
                except Exception as retry_err:
                    logger.error(f"[TUI Chat] WebSocket retry failed: {retry_err}")
                    transcript.write("[dim yellow]ℹ WebSocket disconnected. Falling back to local engine...[/]\n")
                    await self._run_local_turn(text)
                    return
            else:
                transcript.write("[dim yellow]ℹ WebSocket reconnection failed. Falling back to local engine...[/]\n")
                await self._run_local_turn(text)
                return

        response_chunks: List[str] = []
        while True:
            try:
                msg = await ws.receive()
            except (aiohttp.ClientError, ConnectionResetError, OSError) as recv_err:
                logger.warning(f"[TUI Chat] WebSocket stream receive error: {recv_err}")
                transcript.write("[bold red]❌ WebSocket connection dropped while receiving response stream.[/]\n")
                break

            if msg.type != aiohttp.WSMsgType.TEXT:
                break

            try:
                data = json.loads(msg.data)
            except Exception:
                continue

            etype = data.get("type")
            if etype == "connection_established":
                continue
            elif etype == "delta":
                delta_text = data.get("text", "")
                response_chunks.append(delta_text)
                accum = "".join(response_chunks)
                try:
                    self.query_one("#streaming_output", Static).update(f"[bold cyan]Agent:[/] {accum}▌")
                except Exception:
                    pass
            elif etype == "tool_start":
                tool = data.get("tool", "")
                transcript.write(f"[dim cyan]🔧 Invoking tool:[/] [white]{tool}[/]")
            elif etype == "tool_result":
                tool = data.get("tool", "")
                summary = data.get("summary", "")
                transcript.write(f"[dim green]✔ Tool {tool}:[/] [dim]{summary}[/]")
            elif etype == "approval_request":
                action = data.get("action", {})
                self._pending_action_id = action.get("id")
                desc = action.get("description", "Proposed trade action")
                transcript.write(
                    f"\n[bold yellow]⚠️ APPROVAL REQUIRED:[/] {desc}\n"
                    f"[dim]Modal prompt active or type [bold green]/allow[/], [bold cyan]/session[/], or [bold red]/deny[/].[/]\n"
                )
                try:
                    from cli.overlays.approval_modal import ApprovalModalScreen
                    action_id = str(action.get("id", ""))

                    def _on_modal_result(decision: Optional[str]) -> None:
                        if decision:
                            import asyncio
                            asyncio.create_task(self._handle_approval_decision(action_id, decision))

                    if hasattr(self, "app") and self.app:
                        self.app.push_screen(ApprovalModalScreen(action), callback=_on_modal_result)
                except Exception as modal_err:
                    logger.debug(f"[TUI Chat] Could not push ApprovalModalScreen: {modal_err}")
            elif etype == "complete":
                try:
                    self.query_one("#streaming_output", Static).update("")
                except Exception:
                    pass
                full_reply = data.get("text") or "".join(response_chunks)
                transcript.write(f"[bold cyan]Agent:[/] {full_reply}\n")
                break
            elif etype in ("error", "interrupted"):
                try:
                    self.query_one("#streaming_output", Static).update("")
                except Exception:
                    pass
                if etype == "error":
                    transcript.write(f"[bold red]❌ Error:[/] {data.get('message', 'Unknown error')}\n")
                else:
                    transcript.write("[yellow]Turn was interrupted by operator.[/]\n")
                break

    async def _run_local_turn(self, text: str) -> None:
        """Run message turn directly using local ChatAgent engine."""
        transcript = self.query_one("#transcript", RichLog)
        try:
            if not self._local_agent:
                from telegram_bot.chat_agent import ChatAgent
                settings = load_settings()
                self._local_agent = ChatAgent(settings=settings, user_id=self.session_id)

            transcript.write("[dim yellow]Thinking...[/]")
            reply_text, pending = await self._local_agent.handle(text)

            # Live streaming display to widget
            try:
                streaming_widget = self.query_one("#streaming_output", Static)
            except Exception:
                streaming_widget = None

            words = reply_text.split(" ")
            accum = ""
            for w in words:
                accum += w + " "
                if streaming_widget is not None:
                    streaming_widget.update(f"[bold cyan]Agent:[/] {accum}▌")
                await asyncio.sleep(0.01)

            if streaming_widget is not None:
                streaming_widget.update("")
            transcript.write(f"[bold cyan]Agent:[/] {reply_text}\n")

            if pending:
                self._pending_action_id = pending.id
                transcript.write(
                    f"\n[bold yellow]⚠️ APPROVAL REQUIRED:[/] {pending.description}\n"
                    f"[dim]Type [bold green]/allow[/] to execute, or [bold red]/deny[/] to cancel.[/]\n"
                )
        except Exception as e:
            logger.error(f"[TUI Chat] Error in local agent turn: {e}", exc_info=True)
            transcript.write(f"[bold red]❌ Error processing request:[/] {e}\n")


# -------------------------------------------------------------------------------
# Standalone CLI REPL Chat (prompt_toolkit + Rich)
# -------------------------------------------------------------------------------

def _get_prompt_session():
    """Safely initialize prompt_toolkit PromptSession with fallback for Windows non-console."""
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import InMemoryHistory
        return PromptSession(history=InMemoryHistory())
    except Exception as e:
        logger.debug(f"Falling back from standard prompt_toolkit: {e}")
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.output.vt100 import Vt100_Output
            from prompt_toolkit.data_structures import Size
            from prompt_toolkit.history import InMemoryHistory
            out = Vt100_Output(sys.stdout, lambda: Size(rows=24, columns=80))
            return PromptSession(output=out, history=InMemoryHistory())
        except Exception:
            return None


async def run_cli_chat(
    api_url: str = DEFAULT_API_URL,
    api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    offline: bool = False,
    model: str = "auto",
) -> None:
    """
    Interactive standalone REPL chat with AI Trading Agent.

    Streams tokens in real time to the terminal.
    """
    console = get_console()
    api_url = api_url.rstrip("/")
    api_key = api_key or os.getenv("DASHBOARD_API_KEY", "")
    session_id = session_id or "cli:repl_user"

    console.print(f"[bold {PHOSPHOR_AMBER}]┌─────────────────────────────────────────────────────────────┐[/]")
    console.print(f"[bold {PHOSPHOR_AMBER}]│  MONIKA QUANTITATIVE TRADING DESK — REPL CONSOLE            │[/]")
    console.print(f"[dim {MUTED}]│  Type /help for command reference, /exit to disconnect.     │[/]")
    console.print(f"[bold {PHOSPHOR_AMBER}]└─────────────────────────────────────────────────────────────┘[/]\n")

    ws_url = api_url.replace("http://", "ws://").replace("https://", "wss://") + f"/ws/agent-chat?session_id={session_id}"
    if api_key:
        ws_url += f"&token={api_key}"

    prompt_session = _get_prompt_session()

    ws = None
    session_client = None
    local_agent = None

    if not offline:
        try:
            session_client = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.0))
            ws = await asyncio.wait_for(session_client.ws_connect(ws_url), timeout=3.0)
            init_msg = await ws.receive_json()
            console.print(f"{stamp_ok('CONNECTED')} Live agent service online (Session: {session_id}).\n")
        except Exception as e:
            if session_client and not session_client.closed:
                await session_client.close()
            session_client = None
            ws = None
            console.print(f"{stamp_info('LOCAL')} API Gateway unreachable ({e}). Falling back to local engine.\n")

    if ws is None:
        try:
            from telegram_bot.chat_agent import ChatAgent
            settings = load_settings()
            local_agent = ChatAgent(settings=settings, user_id=session_id)
            console.print(f"{stamp_ok('LOCAL')} Local ChatAgent engine initialized.\n")
        except Exception as e:
            console.print(f"{stamp_err('INITIALIZATION')} Failed to initialize ChatAgent: {e}")
            return

    pending_action_id: Optional[str] = None

    while True:
        try:
            if prompt_session is not None:
                user_input = await asyncio.to_thread(prompt_session.prompt, "MONIKA > ")
            else:
                user_input = await asyncio.to_thread(input, "MONIKA > ")
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n[dim {MUTED}]Session terminated by operator.[/]")
            break

        text = user_input.strip()
        if not text:
            continue

        if text.lower() in ("/quit", "/exit", "quit", "exit"):
            console.print(f"[dim {MUTED}]Terminating interactive chat session. Disconnected.[/]")
            break

        if text.lower() == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue

        if text.lower() == "/help":
            console.print(
                f"\n[bold {PHOSPHOR_AMBER}]Interactive Command Reference:[/]\n"
                f" • [{PAPER}]/exit, /quit[/]     : Disconnect and exit interactive desk session\n"
                f" • [{PAPER}]/clear[/]            : Clear console display\n"
                f" • [{PAPER}]/allow[/]            : Authorize pending order execution proposal (single-order authorization)\n"
                f" • [{PAPER}]/session[/]          : Grant 4-hour execution authorization for current session\n"
                f" • [{PAPER}]/deny[/]             : Reject pending order execution proposal\n"
                f" • [{PAPER}]/fast <prompt>[/]    : Route query via Tier 1 Low-Latency model (Gemini Flash)\n"
                f" • [{PAPER}]/analyze <prompt>[/] : Route query via Tier 3 Deep Synthesis model\n"
                f" • [{PAPER}]/research <prompt>[/]: Route query via Tier 4 Macro Research model\n"
            )
            continue

        # Handle approval responses
        if pending_action_id:
            if text.lower() in ("/allow", "/yes", "allow", "yes"):
                await _submit_cli_decision(ws, local_agent, pending_action_id, "allow_once", console)
                pending_action_id = None
                continue
            elif text.lower() in ("/session", "allow_session"):
                await _submit_cli_decision(ws, local_agent, pending_action_id, "allow_session", console)
                pending_action_id = None
                continue
            elif text.lower() in ("/deny", "/no", "deny", "no"):
                await _submit_cli_decision(ws, local_agent, pending_action_id, "deny", console)
                pending_action_id = None
                continue

        # Send turn
        if ws is not None:
            if not is_ws_alive(ws):
                try:
                    if session_client is None or session_client.closed:
                        session_client = aiohttp.ClientSession()
                    ws = await asyncio.wait_for(session_client.ws_connect(ws_url), timeout=3.0)
                    try:
                        await ws.receive(timeout=2.0)
                    except Exception:
                        pass
                except Exception:
                    ws = None

        if ws is not None:
            try:
                await ws.send_json({"type": "message", "text": text, "model": model})
                while True:
                    msg = await ws.receive()
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    data = json.loads(msg.data)
                    etype = data.get("type")

                    if etype == "connection_established":
                        continue
                    elif etype == "delta":
                        sys.stdout.write(data.get("text", ""))
                        sys.stdout.flush()
                    elif etype == "tool_start":
                        console.print(f"\n[dim {MUTED}]  [{BRASS}][ TOOL ][/] {data.get('tool')}...[/]", end="")
                    elif etype == "tool_result":
                        console.print(f" {stamp_ok()}", end="")
                    elif etype == "approval_request":
                        action = data.get("action", {})
                        pending_action_id = action.get("id")
                        desc = action.get("description", "Proposed execution action")
                        console.print(
                            f"\n\n{stamp_warn('AUTHORIZATION REQUIRED')} {desc}\n"
                            f"[dim {MUTED}]Type [bold {BULL_PROFIT}]/allow[/] to authorize, [bold {BRASS}]/session[/] for 4h session, or [bold {BEAR_LOSS}]/deny[/] to reject.[/]"
                        )
                    elif etype == "complete":
                        console.print("\n")
                        break
                    elif etype == "error":
                        console.print(f"\n{stamp_err()} {data.get('message')}\n")
                        break
            except Exception as e:
                console.print(f"\n{stamp_warn('CONNECTION')} WebSocket connection dropped ({e}). Falling back to local engine...\n")
                if ws and not ws.closed:
                    try:
                        await ws.close()
                    except Exception:
                        pass
                ws = None

        if ws is None:
            try:
                if local_agent is None:
                    from telegram_bot.chat_agent import ChatAgent
                    settings = load_settings()
                    local_agent = ChatAgent(settings=settings, user_id=session_id)
                reply_text, pending = await local_agent.handle(text)
                sys.stdout.write(reply_text)
                sys.stdout.flush()
                console.print("\n")

                if pending:
                    pending_action_id = getattr(pending, "action_id", getattr(pending, "id", None))
                    console.print(
                        f"\n{stamp_warn('AUTHORIZATION REQUIRED')} {pending.description}\n"
                        f"[dim {MUTED}]Type [bold {BULL_PROFIT}]/allow[/] to authorize, or [bold {BEAR_LOSS}]/deny[/] to reject.[/]\n"
                    )
            except Exception as e:
                console.print(f"\n{stamp_err('EXECUTION')} {e}\n")

    # Cleanup
    if ws and not ws.closed:
        await ws.close()
    if session_client and not session_client.closed:
        await session_client.close()


async def _submit_cli_decision(ws, local_agent, action_id: str, decision: str, console: Console) -> None:
    """Submit approval decision in CLI REPL."""
    if ws and not ws.closed:
        await ws.send_json({
            "type": "approval_response",
            "action_id": action_id,
            "decision": decision,
        })
        msg = await ws.receive_json()
        console.print(f"[bold {PHOSPHOR_AMBER}]Monika:[/] {msg.get('text', 'Decision processed.')}\n")
    else:
        if local_agent is None:
            from telegram_bot.chat_agent import ChatAgent
            settings = load_settings()
            local_agent = ChatAgent(settings=settings, user_id="cli:repl_user")
        if decision == "allow_once":
            ok, res = await local_agent.confirm_action(action_id)
        elif decision == "allow_session":
            ok, res = await local_agent.approve_for_session(action_id)
        else:
            res = await local_agent.reject_action(action_id)
        console.print(f"[bold {PHOSPHOR_AMBER}]Monika:[/] {res}\n")
