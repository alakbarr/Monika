# ==============================================================================
# File: cli/chat/commands.py
# Description: Slash Command Router for Monika CLI Chat
# ==============================================================================

"""
Slash command parser and dispatcher for Monika Interactive CLI Chat.
Handles local actions (/help, /model, /theme, /status, /positions, /clear, /export,
/allow, /deny, /session, /exit) with rich institutional formatting.
"""

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from rich import box
from rich.table import Table
from rich.text import Text

from cli.chat.prompt import ChatPromptManager
from cli.chat.renderer import ChatRenderer
from cli.chat.theme import (
    GLYPH_AGENT,
    GLYPH_ARROW_RIGHT,
    GLYPH_DOT,
    GLYPH_ERROR,
    GLYPH_SUCCESS,
    GLYPH_WARN,
    ChatPalette,
)
from cli.theme import (
    THEMES,
    stamp_err,
    stamp_info,
    stamp_ok,
    stamp_warn,
)

AVAILABLE_THEMES = list(THEMES.keys())

logger = logging.getLogger("TradingAgent.CLI.Chat.Commands")

MODEL_ALIASES: Dict[str, str] = {
    "auto": "auto",
    "fast": "gemini-2.5-flash",
    "balanced": "gemini-2.5-pro",
    "reasoning": "deepseek-r1",
    "deepseek": "deepseek-v3",
    "opus": "claude-3-5-sonnet",
    "claude": "claude-3-5-sonnet",
    "claude-sonnet": "claude-3-5-sonnet",
    "claude-opus": "claude-3-opus",
    "gemini-flash": "gemini-2.5-flash",
    "gemini-pro": "gemini-2.5-pro",
}


@dataclass
class CommandResult:
    """Outcome of a slash command evaluation."""
    handled: bool
    should_exit: bool = False
    action_payload: Optional[Dict[str, Any]] = None
    output_message: Optional[str] = None


class ChatCommandRouter:
    """Dispatches CLI slash commands and renders local desk telemetry."""

    def __init__(
        self,
        renderer: ChatRenderer,
        prompt_manager: ChatPromptManager,
        api_url: str = "http://127.0.0.1:8000",
        api_key: Optional[str] = None,
        session_id: str = "cli:repl_user",
    ):
        self.renderer = renderer
        self.prompt_manager = prompt_manager
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key or os.getenv("DASHBOARD_API_KEY", "")
        self.session_id = session_id

    async def handle(
        self,
        input_text: str,
        pending_action_id: Optional[str] = None,
        history_records: Optional[List[Dict[str, Any]]] = None,
    ) -> CommandResult:
        """
        Evaluate user input for slash command syntax.
        Returns CommandResult indicating whether input was handled.
        """
        stripped = input_text.strip()
        if not stripped.startswith("/"):
            return CommandResult(handled=False)

        parts = stripped.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("/exit", "/quit", "/q"):
            self.renderer.render_notice("Terminating interactive chat session. Disconnected.", level="info")
            return CommandResult(handled=True, should_exit=True)

        if cmd == "/help":
            self._render_help_catalog()
            return CommandResult(handled=True)

        if cmd == "/clear":
            self.renderer.console.clear()
            return CommandResult(handled=True)

        if cmd == "/theme":
            self._handle_theme_switch(arg)
            return CommandResult(handled=True)

        if cmd == "/model":
            self._handle_model_switch(arg)
            return CommandResult(handled=True)

        if cmd == "/status":
            await self._handle_status_query()
            return CommandResult(handled=True)

        if cmd == "/positions":
            await self._handle_positions_query()
            return CommandResult(handled=True)

        if cmd in ("/allow", "/yes"):
            target_id = arg or pending_action_id
            if not target_id:
                self.renderer.render_notice("No pending trade authorization proposal to approve.", level="warn")
                return CommandResult(handled=True)
            return CommandResult(
                handled=True,
                action_payload={"type": "approval_response", "action_id": target_id, "decision": "allow_once"},
            )

        if cmd in ("/session", "/allow_session"):
            target_id = arg or pending_action_id
            if not target_id:
                self.renderer.render_notice("No pending trade authorization proposal to approve for session.", level="warn")
                return CommandResult(handled=True)
            return CommandResult(
                handled=True,
                action_payload={"type": "approval_response", "action_id": target_id, "decision": "allow_session"},
            )

        if cmd in ("/deny", "/no"):
            target_id = arg or pending_action_id
            if not target_id:
                self.renderer.render_notice("No pending trade authorization proposal to reject.", level="warn")
                return CommandResult(handled=True)
            return CommandResult(
                handled=True,
                action_payload={"type": "approval_response", "action_id": target_id, "decision": "deny"},
            )

        if cmd == "/export":
            self._handle_export(arg, history_records or [])
            return CommandResult(handled=True)

        # Unrecognized slash command
        self.renderer.render_notice(
            f"Unrecognized command '{cmd}'. Type [bold]/help[/] for command catalog.",
            level="warn",
        )
        return CommandResult(handled=True)

    def _render_help_catalog(self) -> None:
        """Render comprehensive command & keybinding table."""
        p = self.renderer.palette
        console = self.renderer.console

        table = Table(
            title=f"[bold {p.primary}]{GLYPH_AGENT} MONIKA INTERACTIVE COMMAND REFERENCE[/]",
            box=box.ROUNDED,
            border_style=p.border,
            header_style=f"bold {p.accent}",
            expand=True,
        )
        table.add_column("Command", style=f"bold {p.text}", width=18)
        table.add_column("Arguments", style=f"dim {p.muted}", width=22)
        table.add_column("Description", style=f"{p.text}")

        commands_info = [
            ("/help", "None", "Display this interactive command catalog"),
            ("/model", "[name | alias]", "Switch LLM routing tier (e.g. /model fast, /model reasoning)"),
            ("/theme", "[theme_name]", "Switch UI color palette (retro_vintage, cyberpunk_neon, etc.)"),
            ("/status", "None", "Display live system health, DB connection & MT5 status"),
            ("/positions", "None", "List current open trading positions with PnL & targets"),
            ("/allow", "[action_id?]", "Authorize proposed trade execution (single-trade)"),
            ("/session", "[action_id?]", "Grant 4-hour trade execution window for active session"),
            ("/deny", "[action_id?]", "Reject proposed trade execution"),
            ("/export", "[filepath?]", "Export conversation transcript to Markdown or JSON"),
            ("/clear", "None", "Clear terminal screen display"),
            ("/exit, /quit", "None", "Terminate interactive session and disconnect"),
        ]

        for c, a, d in commands_info:
            table.add_row(c, a, d)

        console.print()
        console.print(table)

        # Keybinding shortcuts panel
        kb_table = Table(
            title=f"[bold {p.accent}]TERMINAL SHORTCUTS & KEYBINDINGS[/]",
            box=box.SIMPLE,
            border_style=p.thinking_border,
            header_style=f"bold {p.muted}",
        )
        kb_table.add_column("Shortcut", style=f"bold {p.accent}", width=18)
        kb_table.add_column("Function", style=f"{p.text}")

        shortcuts = [
            ("Enter", "Submit prompt query or execute command"),
            ("Shift+Enter / Alt+Enter", "Insert multi-line newline without submitting"),
            ("Ctrl+C", "Interrupt active generation turn / Cancel prompt input"),
            ("Ctrl+L", "Clear screen buffer"),
            ("Tab", "Trigger command auto-completion"),
        ]
        for k, f in shortcuts:
            kb_table.add_row(k, f)

        console.print(kb_table)
        console.print()

    def _handle_theme_switch(self, theme_name: str) -> None:
        """Switch palette across renderer and prompt manager."""
        p = self.renderer.palette
        console = self.renderer.console

        if not theme_name:
            available = ", ".join([f"[bold {p.accent}]{t}[/]" for t in AVAILABLE_THEMES])
            console.print(f"Current theme: [bold {p.primary}]{self.renderer.theme_name}[/]")
            console.print(f"Available themes: {available}")
            console.print(f"[dim {p.muted}]Usage: /theme <theme_name>[/]\n")
            return

        target_theme = theme_name.strip().lower()
        if target_theme not in AVAILABLE_THEMES:
            self.renderer.render_notice(
                f"Unknown theme '{target_theme}'. Available: {', '.join(AVAILABLE_THEMES)}",
                level="warn",
            )
            return

        self.renderer.set_theme(target_theme)
        self.prompt_manager.set_theme(target_theme)
        self.renderer.render_notice(f"Theme switched to '{target_theme}'.", level="success")

    def _handle_model_switch(self, model_arg: str) -> None:
        """Switch active model routing tier."""
        p = self.renderer.palette
        console = self.renderer.console

        if not model_arg:
            aliases_fmt = ", ".join([f"[bold {p.accent}]{k}[/]" for k in sorted(MODEL_ALIASES.keys())])
            console.print(f"Active model: [bold {p.primary}]{self.prompt_manager.active_model}[/]")
            console.print(f"Available tiers / aliases: {aliases_fmt}")
            console.print(f"[dim {p.muted}]Usage: /model <tier_or_name> (e.g. /model fast, /model reasoning)[/]\n")
            return

        target_alias = model_arg.strip().lower()
        resolved_model = MODEL_ALIASES.get(target_alias, model_arg.strip())

        self.prompt_manager.update_telemetry(model=resolved_model)
        self.renderer.render_notice(
            f"Active model routed to '[bold]{resolved_model}[/]'.",
            level="success",
        )

    async def _handle_status_query(self) -> None:
        """Query live system health and telemetry from daemon API or local fallback."""
        p = self.renderer.palette
        console = self.renderer.console

        health_data: Optional[Dict[str, Any]] = None
        url = f"{self.api_url}/api/health"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.0)) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        health_data = await resp.json()
        except Exception as e:
            logger.debug(f"Failed to query /api/health: {e}")

        table = Table(
            title=f"[bold {p.primary}]{GLYPH_AGENT} SYSTEM TELEMETRY & HEALTH STATUS[/]",
            box=box.ROUNDED,
            border_style=p.border,
            header_style=f"bold {p.accent}",
        )
        table.add_column("Parameter", style=f"dim {p.muted}", width=24)
        table.add_column("Status / Value", style=f"bold {p.text}")

        if health_data:
            db_status = (
                f"[bold {p.success}]{GLYPH_SUCCESS} CONNECTED[/]"
                if health_data.get("db_connected")
                else f"[bold {p.danger}]{GLYPH_ERROR} DISCONNECTED[/]"
            )
            mt5_status = (
                f"[bold {p.success}]{GLYPH_SUCCESS} ACTIVE[/]"
                if health_data.get("mt5_connected")
                else f"[bold {p.warning}]{GLYPH_WARN} NO HEARTBEAT[/]"
            )
            uptime_s = health_data.get("uptime_seconds", 0)
            hours, remainder = divmod(uptime_s, 3600)
            mins, secs = divmod(remainder, 60)
            uptime_str = f"{hours}h {mins}m {secs}s"

            table.add_row("Daemon Gateway", f"[bold {p.success}]ONLINE[/] ({self.api_url})")
            table.add_row("Database Engine", db_status)
            table.add_row("MetaTrader 5 Bridge", mt5_status)
            table.add_row("Daemon Uptime", uptime_str)
        else:
            table.add_row("Daemon Gateway", f"[{p.warning}]UNREACHABLE / OFFLINE[/]")
            table.add_row("Execution Mode", f"[{p.accent}]LOCAL FALLBACK ENGINE[/]")

        table.add_row("Active Model", f"[{p.primary}]{self.prompt_manager.active_model}[/]")
        table.add_row("Trading Desk Mode", f"[{p.accent}]{self.prompt_manager.active_mode}[/]")
        table.add_row("Session Identifier", f"[dim {p.muted}]{self.session_id}[/]")
        table.add_row("Timestamp", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))

        console.print()
        console.print(table)
        console.print()

    async def _handle_positions_query(self) -> None:
        """Fetch and render open positions table."""
        p = self.renderer.palette
        console = self.renderer.console

        positions: List[Dict[str, Any]] = []
        url = f"{self.api_url}/api/positions?status=open"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2.5)) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        positions = await resp.json()
        except Exception as e:
            logger.debug(f"Failed to fetch /api/positions: {e}")

        if not positions:
            self.renderer.render_notice("No open positions found or gateway unreachable.", level="info")
            return

        table = Table(
            title=f"[bold {p.primary}]{GLYPH_AGENT} OPEN TRADING POSITIONS[/]",
            box=box.ROUNDED,
            border_style=p.border,
            header_style=f"bold {p.accent}",
        )
        table.add_column("Ticket", style=f"dim {p.muted}")
        table.add_column("Symbol", style=f"bold {p.text}")
        table.add_column("Direction")
        table.add_column("Volume", justify="right")
        table.add_column("Entry Price", justify="right")
        table.add_column("SL", justify="right")
        table.add_column("TP", justify="right")
        table.add_column("PnL ($)", justify="right")

        for pos in positions:
            direction = str(pos.get("direction", "")).upper()
            dir_style = f"bold {p.success}" if direction in ("BUY", "LONG") else f"bold {p.danger}"

            pnl = pos.get("pnl")
            if pnl is not None:
                pnl_num = float(pnl)
                pnl_style = f"bold {p.success}" if pnl_num >= 0 else f"bold {p.danger}"
                pnl_str = f"[{pnl_style}]{pnl_num:+.2f}[/]"
            else:
                pnl_str = "[dim]---[/]"

            table.add_row(
                str(pos.get("mt5_ticket") or pos.get("id", "N/A")),
                str(pos.get("symbol", "N/A")),
                f"[{dir_style}]{direction}[/]",
                str(pos.get("volume", "0.0")),
                str(pos.get("entry_price", "0.0")),
                str(pos.get("sl", "---")),
                str(pos.get("tp", "---")),
                pnl_str,
            )

        console.print()
        console.print(table)
        console.print()

    def _handle_export(self, filepath: str, history: List[Dict[str, Any]]) -> None:
        """Export session transcript to markdown or json."""
        if not history:
            self.renderer.render_notice("Transcript is empty; nothing to export.", level="warn")
            return

        out_path = filepath.strip()
        if not out_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = f"monika_chat_export_{timestamp}.md"

        try:
            if out_path.endswith(".json"):
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(history, f, indent=2)
            else:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(f"# Monika Chat Transcript Export\n")
                    f.write(f"Session: `{self.session_id}` | Date: {datetime.now(timezone.utc).isoformat()}\n\n---\n\n")
                    for entry in history:
                        sender = entry.get("sender", "Unknown")
                        text = entry.get("text", "")
                        f.write(f"### {sender.upper()}\n\n{text}\n\n")

            self.renderer.render_notice(f"Transcript exported successfully to [bold]{out_path}[/].", level="success")
        except Exception as e:
            self.renderer.render_notice(f"Failed to export transcript: {e}", level="error")
