# ==============================================================================
# File: interfaces/cli/tui_app/mixins/actions.py
# Description: Action handlers & interactive command bar mixin for Monika TUI
# ==============================================================================

import asyncio
import logging
from typing import Optional

import aiohttp
from textual.widgets import Input, RichLog

from monika.core.config.settings import load_settings
from monika.interfaces.cli.busy_input import InputDelivery
from monika.interfaces.cli.theme import BRASS, MUTED, PAPER, PHOSPHOR_AMBER, THEMES
from monika.interfaces.cli.tui_app.base import _TuiMixinBase
from monika.interfaces.cli.tui_app.widgets import KillConfirmModalScreen

logger = logging.getLogger("TradingAgent.TUI")


class ActionsMixin(_TuiMixinBase):
    """Mixin handling user actions, keybindings, and command bar execution."""

    async def _dispatch_steer(self, msg: str, mode: str = "steer") -> None:
        """Dispatch a steer directive mid-stream to the agent via API or DB fallback."""
        activity_log = self.query_one("#activity_log", RichLog)
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        dispatched = False
        if not self.standalone:
            try:
                timeout = aiohttp.ClientTimeout(total=2.0)
                async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                    res = await session.post(
                        f"{self.api_url}/api/v1/actions/steer", json={"message": msg, "mode": mode}
                    )
                    if res.status == 200:
                        dispatched = True
            except Exception:
                pass

        if not dispatched:
            try:
                from monika.infrastructure.database.db import get_session
                from monika.infrastructure.database.models import ActivityLog as DBLog
                from monika.infrastructure.database.models import UserMarketIntel, _utcnow

                async with get_session() as session:
                    session.add(
                        UserMarketIntel(
                            telegram_user_id="tui_operator",
                            intel_type="tactical_directive",
                            title="TUI Operator Steer",
                            summary=msg,
                            directive="neutral",
                            target_cycle="next_cycle_only" if mode == "follow_up" else "continuous",
                            affected_symbols="ALL",
                            is_active=True,
                            created_at=_utcnow(),
                        )
                    )
                    session.add(
                        DBLog(
                            category="analysis",
                            description=f"TUI Steer injected ({mode}): {msg[:100]}",
                            actor="operator_tui",
                        )
                    )
                    await session.commit()
                dispatched = True
            except Exception as dbe:
                logger.debug(f"[TUI] DB steer fallback error: {dbe}")

        try:
            det_log = self.query_one("#analysis_detail_log", RichLog)
            det_log.write(f"[bold green][OK] Steer Dispatched ({mode}):[/] {msg}")
        except Exception:
            pass
        activity_log.write(f"[bold {PHOSPHOR_AMBER}]⟳ Mid-stream steer injected into cycle:[/] {msg}")

    async def action_quit(self) -> None:
        """Cleanly exit the dashboard."""
        if self._is_input_focused():
            return
        self.exit()

    async def action_pause(self) -> None:
        """Pause system trading proposals."""
        if self._is_input_focused():
            return
        activity_log = self.query_one("#activity_log", RichLog)
        activity_log.write("[bold yellow][DIJEDA] Pausing system trading...[/]")
        from monika.application.services.trading_service import TradingService
        from monika.infrastructure.database.db import get_session, init_db

        await init_db()
        async with get_session() as session:
            await TradingService.pause_trading(session, reason="TUI Pause Action", actor="tui_operator")
        try:
            import aiohttp

            settings = load_settings()
            port = settings.get("dashboard", {}).get("port", 8000)
            async with aiohttp.ClientSession() as http_sess:
                await http_sess.post(
                    f"http://127.0.0.1:{port}/api/v1/actions/pause",
                    timeout=aiohttp.ClientTimeout(total=1.0),
                )
        except Exception:
            pass
        await self.refresh_data()

    def action_kill(self) -> None:
        """Trigger emergency kill switch with operator confirmation."""
        if self._is_input_focused():
            return

        def handle_decision(confirmed: Optional[bool]) -> None:
            if confirmed:
                asyncio.create_task(self._execute_kill())

        self.push_screen(KillConfirmModalScreen(), handle_decision)

    async def _execute_kill(self) -> None:
        """Execute emergency kill switch after confirmation."""
        activity_log = self.query_one("#activity_log", RichLog)
        activity_log.write("[bold red][EMERGENCY] TRIGGERING EMERGENCY KILL SWITCH...[/]")
        from monika.application.services.trading_service import TradingService
        from monika.infrastructure.database.db import get_session, init_db

        await init_db()
        async with get_session() as session:
            await TradingService.emergency_kill(session, reason="TUI Emergency Kill", actor="tui_operator")
        try:
            import aiohttp

            settings = load_settings()
            port = settings.get("dashboard", {}).get("port", 8000)
            async with aiohttp.ClientSession() as http_sess:
                await http_sess.post(
                    f"http://127.0.0.1:{port}/api/v1/kill",
                    timeout=aiohttp.ClientTimeout(total=1.0),
                )
        except Exception:
            pass
        await self.refresh_data()

    async def _send_inline_chat(self, prompt: str) -> None:
        """Process inline chat input and render AI response directly to inline_chat_log."""
        try:
            inline_log = self.query_one("#inline_chat_log", RichLog)
            inline_log.write(f"[bold {PAPER}]Operator:[/] {prompt}")
            inline_log.write(f"[dim {MUTED}]Thinking...[/]")

            if self._inline_chat_agent is None:
                from monika.application.agent.chat_agent import ChatAgent

                settings = getattr(self, "settings", None) or load_settings()
                self._inline_chat_agent = ChatAgent(settings=settings, user_id="cli:tui_inline")
            reply_text, pending = await self._inline_chat_agent.handle(prompt)
            inline_log.write(f"[bold {PHOSPHOR_AMBER}]Monika:[/] {reply_text}\n")
            if pending:
                inline_log.write(
                    f"\n[bold yellow][PERINGATAN] APPROVAL REQUIRED:[/] {pending.description}\n"
                    f"[dim]Press 'c' to enter interactive console and approve/reject.[/]\n"
                )
        except Exception as e:
            try:
                inline_log = self.query_one("#inline_chat_log", RichLog)
                inline_log.write(f"[bold red][GAGAL] Chat Error:[/] {e}\n")
            except Exception:
                pass

    async def action_chat(self) -> None:
        """Push interactive REPL chat screen overlay."""
        if self._is_input_focused():
            return
        from monika.interfaces.cli.tui_chat import ChatScreen

        await self.push_screen(ChatScreen(api_url=self.api_url, api_key=self.api_key))

    async def action_refresh(self) -> None:
        """Manually trigger data refresh."""
        if self._is_input_focused():
            return
        activity_log = self.query_one("#activity_log", RichLog)
        activity_log.write("[cyan][SYNC] Refreshing dashboard data...[/]")
        await self.refresh_data()

    async def action_focus_input(self) -> None:
        """Focus the interactive command bar."""
        self.query_one("#cmd_input", Input).focus()

    async def action_blur_input(self) -> None:
        """Blur the interactive command bar."""
        self.set_focus(None)

    def action_dequeue(self) -> None:
        """Restore all queued messages from busy buffer back to editor (Alt+Up shortcut)."""
        restored = self.busy_buffer.dequeue_all()
        if restored:
            inp = self.query_one("#cmd_input", Input)
            inp.value = restored[-1]
            inp.focus()
            activity_log = self.query_one("#activity_log", RichLog)
            activity_log.write(f"[cyan]Restored {len(restored)} message(s) from queue to input bar.[/]")
            self._refresh_status_bar()

    async def action_interrupt(self) -> None:
        """Abort or interrupt active agent operations."""
        activity_log = self.query_one("#activity_log", RichLog)
        activity_log.write("[bold red] Interruption triggered.[/]")
        self.busy_buffer.submit("INTERRUPT", InputDelivery.INTERRUPT)
        self._refresh_status_bar()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle interactive command bar input."""
        cmd_text = event.value.strip()
        event.input.value = ""
        if not cmd_text:
            return

        activity_log = self.query_one("#activity_log", RichLog)
        parts = cmd_text.split()
        cmd = parts[0].lower()

        # Route chat messages to inline_chat_log if on tab_chat
        try:
            from textual.widgets import TabbedContent

            active_tab = self.query_one("#main_tabs", TabbedContent).active
            if active_tab == "tab_chat" and cmd not in (
                "q",
                "quit",
                "exit",
                "p",
                "pause",
                "res",
                "resume",
                "k",
                "kill",
                "r",
                "refresh",
                "clear",
                "cls",
                "theme",
                "help",
                "h",
                "?",
                "status",
                "s",
                "steer",
                "queue",
                "dequeue",
                "config",
                "sessions",
                "logs",
            ):
                asyncio.create_task(self._send_inline_chat(cmd_text))
                return
        except Exception:
            pass

        if cmd in ("q", "quit", "exit"):
            self.exit()
        elif cmd in ("p", "pause"):
            await self.action_pause()
        elif cmd in ("res", "resume"):
            activity_log.write("[bold green]▶ Resuming system trading...[/]")
            from monika.application.services.trading_service import TradingService
            from monika.infrastructure.database.db import get_session, init_db

            await init_db()
            async with get_session() as session:
                await TradingService.resume_trading(session, actor="tui_operator")
            try:
                import aiohttp

                settings = load_settings()
                port = settings.get("dashboard", {}).get("port", 8000)
                async with aiohttp.ClientSession() as http_sess:
                    await http_sess.post(
                        f"http://127.0.0.1:{port}/api/v1/actions/resume",
                        timeout=aiohttp.ClientTimeout(total=1.0),
                    )
            except Exception:
                pass
            await self.refresh_data()
        elif cmd in ("k", "kill"):
            self.action_kill()

        elif cmd in ("c", "chat"):
            if len(parts) > 1:
                chat_msg = " ".join(parts[1:])
                try:
                    from textual.widgets import TabbedContent

                    self.query_one("#main_tabs", TabbedContent).active = "tab_chat"
                except Exception:
                    pass
                asyncio.create_task(self._send_inline_chat(chat_msg))
            else:
                await self.action_chat()
        elif cmd in ("r", "refresh"):
            await self.action_refresh()
        elif cmd in ("clear", "cls"):
            activity_log.clear()
            activity_log.write("[dim]Activity log cleared.[/]")
        elif cmd in ("status", "s"):
            activity_log.write(
                f"[bold white]Status:[/] PnL=${self.daily_pnl:.2f}, "
                f"KillSwitch={self.kill_switch}, Paused={self.system_paused}, VIX={self.vix}"
            )
        elif cmd == "theme":
            if len(parts) > 1:
                target_theme = parts[1].lower()
                if self.set_theme(target_theme):
                    activity_log.write(f"[bold {PHOSPHOR_AMBER}] Active theme set to:[/] {target_theme}")
                else:
                    activity_log.write(f"[yellow]Unknown theme '{target_theme}'. Options: {list(THEMES.keys())}[/]")
            else:
                activity_log.write(f"[cyan]Current theme: {self.theme_pack.name}. Available: {list(THEMES.keys())}[/]")
        elif cmd == "steer":
            msg = " ".join(parts[1:])
            self.busy_buffer.submit(msg, InputDelivery.STEER)
            activity_log.write(f"[bold {PHOSPHOR_AMBER}]⟳ Steer directive queued:[/] {msg}")
            self._refresh_status_bar()
        elif cmd in ("queue", "followup"):
            msg = " ".join(parts[1:])
            self.busy_buffer.submit(msg, InputDelivery.FOLLOW_UP)
            activity_log.write(f"[bold {BRASS}]▷ Follow-up directive queued:[/] {msg}")
            self._refresh_status_bar()
        elif cmd == "dequeue":
            restored = self.busy_buffer.dequeue_all()
            activity_log.write(f"[cyan]Restored {len(restored)} message(s) from buffer.[/]")
            self._refresh_status_bar()
        elif cmd == "config":
            section_arg = parts[1] if len(parts) > 1 else None
            try:
                cfg = load_settings()
                if section_arg:
                    for p in section_arg.split("."):
                        if isinstance(cfg, dict) and p in cfg:
                            cfg = cfg[p]
                        else:
                            cfg = f"Path '{section_arg}' not found."
                            break
                import yaml

                preview = yaml.dump(cfg, default_flow_style=False, sort_keys=False)[:600]
                activity_log.write(f"[bold cyan] Config ({section_arg or 'all'}):[/]\n{preview}")
            except Exception as e:
                activity_log.write(f"[red]Failed reading config: {e}[/]")
        elif cmd == "sessions":
            try:
                from sqlalchemy import desc, func, select

                from monika.infrastructure.database.db import get_session
                from monika.infrastructure.database.models import TelegramConversation

                async with get_session() as session:
                    rows = (
                        await session.execute(
                            select(
                                TelegramConversation.telegram_user_id,
                                func.count(TelegramConversation.id).label("cnt"),
                            )
                            .group_by(TelegramConversation.telegram_user_id)
                            .order_by(desc("cnt"))
                            .limit(5)
                        )
                    ).all()
                    if rows:
                        sess_info = ", ".join(f"{r.telegram_user_id} ({r.cnt} msgs)" for r in rows)
                        activity_log.write(f"[bold cyan] Active Sessions:[/] {sess_info}")
                    else:
                        activity_log.write("[dim]No active conversation sessions recorded.[/]")
            except Exception as e:
                activity_log.write(f"[yellow]Sessions lookup: {e}[/]")
        elif cmd == "logs":
            activity_log.write("[cyan] Triggered activity log refresh...[/]")
            await self.refresh_data()
        elif cmd in ("plugin", "plugins"):
            if len(parts) > 1 and parts[1].lower() == "install":
                if len(parts) > 2:
                    from monika.application.plugins.engine.installer import run_pip_install

                    pkg = parts[2]
                    activity_log.write(f"[bold cyan]Installing plugin via pip:[/] {pkg}...")
                    success, out = await asyncio.to_thread(run_pip_install, pkg)
                    if success:
                        activity_log.write(f"[bold green] Successfully installed {pkg}[/]")
                    else:
                        activity_log.write(f"[bold red] Failed to install {pkg}: {out}[/]")
                    await self.refresh_plugins_table()
                else:
                    self.action_install_plugin()
            elif len(parts) > 1 and parts[1].lower() in ("toggle", "on", "off"):
                if len(parts) > 2:
                    target_id = parts[2].lower()
                    from monika.application.plugins.engine.installer import list_all_plugins_status, toggle_plugin_state

                    plugins = {p["id"]: p for p in list_all_plugins_status()}
                    if target_id in plugins:
                        p = plugins[target_id]
                        new_state = (
                            True
                            if parts[1].lower() == "on"
                            else (False if parts[1].lower() == "off" else not p["enabled"])
                        )
                        ok, msg = toggle_plugin_state(target_id, p["category"], new_state)
                        activity_log.write(f"[{'green' if ok else 'red'}]{msg}[/]")
                        await self.refresh_plugins_table()
                    else:
                        activity_log.write(f"[yellow]Plugin '{target_id}' not found in registry.[/]")
                else:
                    activity_log.write("[yellow]Usage: :plugin toggle <id> | :plugin on <id> | :plugin off <id>[/]")
            else:
                self.action_tab_plugins()
        elif cmd in ("help", "h", "?"):
            activity_log.write(
                "[bold cyan]Interactive Command & Keyboard Reference:[/]\n"
                " • [bold white]Tab[/]           : Cycle Active Workspace (Overview, Analysis, Signals, Risk, Performance, Market, Plugins, Chat)\n"
                " • [bold white]t[/]             : Toggle ON/OFF selected plugin (Plugins tab)\n"
                " • [bold white]i[/]             : Install new plugin via pip modal (Plugins tab)\n"
                " • [bold white]plugin [cmd][/]  : Manage plugins (:plugin toggle <id>, :plugin install <pkg>, :plugin on/off <id>)\n"
                " • [bold white]theme [name][/]  : Switch UI theme (retro_vintage, modern_dark, high_contrast, daylight)\n"
                " • [bold white]steer [msg][/]   : Inject mid-stream steering guidance into active analysis cycle\n"
                " • [bold white]queue [msg][/]   : Queue follow-up directive for subsequent cycle evaluation\n"
                " • [bold white]dequeue[/]       : Flush and restore queued input buffer to editor\n"
                " • [bold white]q[/] / [bold white]quit[/]   : Exit trading desk terminal\n"
                " • [bold white]p[/] / [bold white]pause[/]  : Suspend new trade proposal generation\n"
                " • [bold white]res[/] / [bold white]resume[/]: Resume trading operations (clear pause/kill-switch flags)\n"
                " • [bold white]k[/] / [bold white]kill[/]   : Trigger emergency kill switch\n"
                " • [bold white]c[/] / [bold white]chat[/]   : Launch interactive desk chat console\n"
                " • [bold white]r[/] / [bold white]refresh[/]: Force immediate data refresh\n"
                " • [bold white]config [path][/]: Inspect system configuration parameters\n"
                " • [bold white]sessions[/]     : Display active operator conversation sessions\n"
                " • [bold white]status[/]       : Display real-time telemetry and risk metrics"
            )
        else:
            # If not a recognized command, buffer as steer instruction if agent is busy
            self.busy_buffer.submit(cmd_text, InputDelivery.STEER)
            activity_log.write(f"[bold {PHOSPHOR_AMBER}]⟳ Steer directive queued:[/] {cmd_text}")
            self._refresh_status_bar()
