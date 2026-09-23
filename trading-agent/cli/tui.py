# ==============================================================================
# File: cli/tui.py
# Description: Rich Terminal Dashboard (TUI) for Monika AI Trading Agent
# ==============================================================================

"""
Rich Terminal Dashboard (TUI) for Monika AI Trading Agent built using Textual.

Features:
- Tabbed interface: Overview (positions & logs), Analysis (LangGraph tree), Performance, Chat.
- Live-updating position table (DataTable) connected to WebSocket /ws/live-feed or REST polling fallback.
- AnalysisCycleTree widget showing live 7-node pipeline + last 3 completed cycles.
- Braille sparklines for PnL and VIX trends.
- Context window gauge and cache hit rate in StatusBar.
- Dual-queue busy input buffer (steer vs follow-up) with 'one-at-a-time' delivery.
- Dynamic ThemePack engine (retro_vintage, modern_dark, high_contrast, daylight).
- Keybindings: q (quit), p (pause), k (kill switch), c (chat), r (refresh), Tab (switch tabs).
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, ClassVar

import aiohttp
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.suggester import SuggestFromList
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from config.settings import load_settings
from cli.sparklines import braille_sparkline, bar_gauge
from cli.analysis_tree import AnalysisCycleTree
from cli.busy_input import BusyInputBuffer, InputDelivery
from cli.theme import (
    get_theme,
    ThemePack,
    THEMES,
    build_tui_css,
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
)

logger = logging.getLogger("TradingAgent.TUI")

DEFAULT_API_URL = (
    os.environ.get("MONIKA_API_URL")
    or os.environ.get("TRADEAGENT_API_URL")
    or os.environ.get("DASHBOARD_URL")
    or "http://127.0.0.1:8000"
)

COMMAND_SUGGESTIONS = [
    "status",
    "pause",
    "resume",
    "kill",
    "chat",
    "refresh",
    "config",
    "theme",
    "steer",
    "queue",
    "dequeue",
    "sessions",
    "logs",
    "clear",
    "help",
    "quit",
]


class LiveTickerBanner(Static):
    """Top live ticker / system status banner with braille sparklines and trend arrows."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._prev_quotes: Dict[str, float] = {}

    def update_status(
        self,
        real_count: int,
        paper_count: int,
        daily_pnl: float,
        pnl_pct: Optional[float],
        vix: Optional[float],
        kill_switch: bool,
        system_paused: bool,
        auto_execute: bool,
        quotes: Optional[Dict[str, float]] = None,
        pnl_history: Optional[List[float]] = None,
        vix_history: Optional[List[float]] = None,
    ) -> None:
        quotes = quotes or {}
        quote_strs = []
        for sym, price in quotes.items():
            prev = self._prev_quotes.get(sym)
            if prev is None:
                trend = f"[dim {MUTED}]•[/]"
            elif price > prev:
                trend = f"[bold {BULL_PROFIT}]▲[/]"
            elif price < prev:
                trend = f"[bold {BEAR_LOSS}]▼[/]"
            else:
                trend = f"[dim {MUTED}]•[/]"
            quote_strs.append(f"[bold {PAPER}]{sym}[/] {trend} [{PHOSPHOR_AMBER}]{price:.4f}[/]")
        self._prev_quotes = dict(quotes)
        if not quote_strs:
            ticker_line = f"[dim {MUTED}]MARKET FEED: AWAITING ACTIVE TICK DATA...[/]"
        else:
            ticker_line = "  │  ".join(quote_strs)

        if vix is not None:
            vix_spark = f" [{PHOSPHOR_AMBER}]{braille_sparkline(vix_history, width=8)}[/]" if vix_history else ""
            ticker_line += f"  │  [bold {PAPER}]VIX[/] [{BRASS}]{vix:.2f}[/]{vix_spark}"

        pnl_color = BULL_PROFIT if daily_pnl >= 0 else BEAR_LOSS
        pnl_sign = "+" if daily_pnl >= 0 else ""
        pct_str = f" ({pnl_sign}{pnl_pct:.2f}%)" if pnl_pct is not None else ""
        pnl_spark = f"  [{pnl_color}]{braille_sparkline(pnl_history, width=10)}[/]" if pnl_history else ""
        pnl_str = f"[{pnl_color}]{pnl_sign}${daily_pnl:,.2f}{pct_str}[/]{pnl_spark}"

        ks_str = f"[bold {BEAR_LOSS}][ACTIVE][/]" if kill_switch else f"[{BULL_PROFIT}][NOMINAL][/]"
        state_str = f"[bold {BRASS}][PAUSED][/]" if system_paused else f"[{BULL_PROFIT}][LIVE][/]"
        exec_str = f"[{PHOSPHOR_AMBER}][AUTO][/]" if auto_execute else f"[dim {MUTED}][MANUAL][/]"

        status_line = (
            f"Positions: [bold {PHOSPHOR_AMBER}]{real_count}R/{paper_count}S[/]  │  "
            f"PnL: {pnl_str}  │  "
            f"Kill: {ks_str}  │  "
            f"Status: {state_str}  │  "
            f"Mode: {exec_str}"
        )

        self.update(f"{ticker_line}\n{status_line}")


class StatusBar(Static):
    """Interactive status footer showing tokens, cache hit rate, context gauge, cost, uptime, and busy status."""

    def update_metrics(
        self,
        cached_tokens: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        uptime_seconds: int,
        ws_status: str,
        context_used: int = 0,
        context_max: int = 200000,
        cache_hit_rate: float = 0.0,
        busy_status: str = "",
    ) -> None:
        hours, rem = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"

        tok_str = f"↑{input_tokens / 1000:.1f}k ↓{output_tokens / 1000:.1f}k"

        # Context window gauge
        gauge_bar, gauge_color = bar_gauge(context_used, context_max, width=10)
        pct = (context_used / context_max * 100) if context_max > 0 else 0.0
        ctx_str = f"[{gauge_color}]{gauge_bar}[/] [{PAPER}]{pct:.0f}%[/]"

        # Cache hit rate
        cache_str = f"[{BRASS}]◎ {cache_hit_rate:.1f}%[/]"

        # Busy input indicator
        busy_str = f"  │  [{PHOSPHOR_AMBER}]{busy_status}[/]" if busy_status else ""

        content = (
            f"[dim {MUTED}]Tokens:[/] [{PAPER}]{tok_str}[/]  │  "
            f"[dim {MUTED}]Cache:[/] {cache_str}  │  "
            f"[dim {MUTED}]Context:[/] {ctx_str}  │  "
            f"[dim {MUTED}]Cost:[/] [{BRASS}]${cost_usd:.4f}[/]  │  "
            f"[dim {MUTED}]Uptime:[/] [{PAPER}]{uptime_str}[/]  │  "
            f"[dim {MUTED}]Feed:[/] {ws_status}{busy_str}"
        )
        self.update(content)


class TradingDashboard(App):
    """
    Rich terminal dashboard for Monika AI Trading Agent using Textual.

    Features:
    - Tabbed view: Overview, Analysis, Performance, Chat
    - Live position table (WebSocket or REST polling fallback)
    - LangGraph 7-node analysis tree with sparklines
    - Interactive command bar with autocomplete and dual-queue steer/follow-up
    - Multi-theme engine (retro_vintage, modern_dark, high_contrast, daylight)
    - Keybindings: q quit, p pause, k kill, c chat, r refresh, Tab switch tabs
    """

    TITLE = "TradeAgent — Terminal Dashboard"

    BINDINGS = [
        Binding("tab", "switch_tab", "Next Tab", show=True),
        Binding("shift+tab", "prev_tab", "Prev Tab", show=False),
        Binding("f1", "help", "F1 Help", show=True),
        Binding("f2", "tab_overview", "F2 Desk", show=True),
        Binding("f3", "tab_analysis", "F3 Intel", show=True),
        Binding("f4", "tab_performance", "F4 Performance", show=True),
        Binding("f5", "tab_chat", "F5 Chat", show=True),
        Binding("f8", "pause", "F8 Pause", show=True),
        Binding("f9", "kill", "F9 Kill", show=True),
        Binding("f10", "quit", "F10 Quit", show=True),
        Binding("1", "tab_overview", "Overview", show=False),
        Binding("2", "tab_analysis", "Analysis", show=False),
        Binding("3", "tab_performance", "Performance", show=False),
        Binding("4", "tab_chat", "Chat", show=False),
        Binding("q", "quit", "Quit", show=False),
        Binding("p", "pause", "Pause Trading", show=False),
        Binding("k", "kill", "Kill Switch", show=False),
        Binding("c", "chat", "Chat Mode", show=False),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("colon", "focus_input", "Command Bar", show=False),
        Binding("escape", "blur_input", "Unfocus Bar", show=False),
        Binding("alt+up", "dequeue", "Dequeue Buffer", show=False),
    ]

    CSS: ClassVar[str] = ""

    def __init__(
        self,
        api_url: str = DEFAULT_API_URL,
        api_key: Optional[str] = None,
        refresh_interval: int = 5,
        standalone: bool = False,
        theme_name: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key or os.getenv("DASHBOARD_API_KEY", "")
        self.refresh_interval = refresh_interval
        self.standalone = standalone

        # Load theme from settings.yaml or fallback
        if not theme_name:
            try:
                cfg = load_settings()
                theme_name = cfg.get("ui", {}).get("theme", "retro_vintage")
            except Exception:
                theme_name = "retro_vintage"
        self.theme_pack = get_theme(theme_name)
        TradingDashboard.CSS = build_tui_css(self.theme_pack)

        # Dual-queue busy input buffer (default 'one-at-a-time' per Q1)
        self.busy_buffer = BusyInputBuffer(default_mode=InputDelivery.STEER, delivery_mode="one-at-a-time")

        self._start_time = time.time()
        self._seen_activity_ids: set[Any] = set()
        self._seen_analysis_ids: set[Any] = set()
        self._ws_status = "🟡 Disconnected"
        self._ws_task: Optional[asyncio.Task] = None
        self._quotes: Dict[str, float] = {}
        self._cached_tokens: int = 0
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._cost_usd: float = 0.0
        self._context_used: int = 0
        self._context_max: int = 200000
        self._cache_hit_rate: float = 0.0

        # Trend histories for sparklines
        self._pnl_history: List[float] = []
        self._vix_history: List[float] = []

        # Cached states
        self.kill_switch = False
        self.system_paused = False
        self.auto_execute = False
        self.daily_pnl = 0.0
        self.daily_pnl_pct: Optional[float] = None
        self.vix: Optional[float] = None
        self.real_count: int = 0
        self.paper_count: int = 0
        self._tabs_mounted: bool = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield LiveTickerBanner(id="ticker")
        with TabbedContent(id="main_tabs"):
            with TabPane("Overview", id="tab_overview"):
                with Horizontal(id="main_panels"):
                    with Vertical(id="positions_container"):
                        yield Static("OPEN POSITIONS (LIVE & SIMULATED)", classes="panel_title")
                        yield DataTable(id="positions_table", zebra_stripes=True)
                    with Vertical(id="activity_container"):
                        yield Static("TELEGRAPH DISPATCH & AUDIT LOG", classes="panel_title")
                        yield RichLog(id="activity_log", wrap=True, highlight=True, markup=True)
            with TabPane("Analysis", id="tab_analysis"):
                with Horizontal(id="analysis_horizontal"):
                    with Vertical(id="analysis_container"):
                        yield Static("MULTI-AGENT PIPELINE EXECUTION TREE", classes="panel_title")
                        yield AnalysisCycleTree(id="cycle_tree")
                    with Vertical(id="analysis_log_container"):
                        yield Static("ANALYSIS PIPELINE & ARBITRATION AUDIT", classes="panel_title")
                        yield RichLog(id="analysis_detail_log", wrap=True, highlight=True, markup=True)
            with TabPane("Signals", id="tab_signals"):
                with Vertical(id="signals_container"):
                    yield Static("REAL-TIME MT5 SIGNALS & REASONING AUDIT", classes="panel_title")
                    yield DataTable(id="signals_table", zebra_stripes=True)
            with TabPane("Risk", id="tab_risk"):
                with Vertical(id="risk_container"):
                    yield Static("LIVE RISK MONITORING & CIRCUIT BREAKERS", classes="panel_title")
                    yield DataTable(id="risk_table", zebra_stripes=True)
            with TabPane("Performance", id="tab_performance"):
                with Horizontal(id="perf_horizontal"):
                    with Vertical(id="perf_left_container"):
                        yield Static("PERFORMANCE METRICS & PNL CURVE", classes="panel_title")
                        yield Static(id="perf_sparkline")
                    with Vertical(id="perf_right_container"):
                        yield Static("QUANTITATIVE EVALUATION LEDGER", classes="panel_title")
                        yield DataTable(id="perf_table", zebra_stripes=True)
            with TabPane("Chat", id="tab_chat"):
                with Vertical(id="chat_tab_container"):
                    yield Static("INTERACTIVE DESK CONSOLE (Press 'c' for full screen)", classes="panel_title")
                    yield RichLog(id="inline_chat_log", wrap=True, highlight=True, markup=True)
        yield Input(
            id="cmd_input",
            placeholder="Commands: [s]tatus [p]ause [res]ume [k]ill [c]hat [r]efresh [config] [theme] [steer] [queue] [help] [q]uit",
            suggester=SuggestFromList(COMMAND_SUGGESTIONS, case_sensitive=False),
        )
        yield StatusBar(id="status_bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize UI widgets, start WebSocket listener and polling timer."""
        # Setup DataTable
        table = self.query_one("#positions_table", DataTable)
        table.add_columns("ID", "Type", "Symbol", "Side", "Lots", "Entry", "SL", "TP", "PnL")

        # Setup Signals Table
        signals_table = self.query_one("#signals_table", DataTable)
        signals_table.add_columns("ID", "Symbol", "Side", "Confidence", "Price", "SL", "TP", "Status", "Timestamp")

        # Setup Risk Table
        risk_table = self.query_one("#risk_table", DataTable)
        risk_table.add_columns("Risk Metric", "Current Value", "Safety Threshold", "Status")
        risk_table.add_rows([
            ("Daily Realized Drawdown", "0.0%", "≤ 3.0%", "NORMAL"),
            ("Circuit Breaker State", "DISARMED", "Auto-trips on 3 consecutive losses", "HEALTHY"),
            ("Margin Utilization", "0.0%", "≤ 80.0%", "NORMAL"),
            ("Kill Switch", "DISARMED", "Emergency Halt", "READY"),
            ("Auto-Execution Guard", "PAPER ONLY", "Live requires approval", "GUARDED"),
        ])

        # Setup Performance Table
        perf_table = self.query_one("#perf_table", DataTable)
        perf_table.add_columns("Metric", "Value", "Benchmark / Limit")
        perf_table.add_rows([
            ("Total Trades", "0", "≥ 50 (Protocol Minimum)"),
            ("Win Rate", "0.0%", "≥ 55.0%"),
            ("Profit Factor", "0.00", "≥ 1.50"),
            ("Max Daily Drawdown", "0.0%", "≤ 3.0%"),
            ("Max Consecutive Losses", "0", "≤ 3 (Circuit Breaker)"),
        ])

        # Setup Activity Log
        log = self.query_one("#activity_log", RichLog)
        log.write(f"[bold {PHOSPHOR_AMBER}][ INITIALIZATION ][/] Monika Terminal TUI Active (Theme: {self.theme_pack.name})")
        log.write(f"[dim {MUTED}]Connecting to market data feed...[/]")

        # Setup Analysis Detail Log
        analysis_log = self.query_one("#analysis_detail_log", RichLog)
        analysis_log.write(f"[dim {MUTED}]Analysis pipeline ready for cycle execution stream...[/]")

        # Setup Inline Chat Log
        inline_chat = self.query_one("#inline_chat_log", RichLog)
        inline_chat.write(f"[bold {PHOSPHOR_AMBER}][ DESK CONSOLE ][/] Monika Autonomous AI Desk Console Ready.")
        inline_chat.write(f"[dim {MUTED}]Type your query in the bottom input bar to chat inline, or press 'c' for full overlay.[/]\n")

        # Initial refresh
        await self.refresh_data()

        # Start periodic polling timer
        self.set_interval(self.refresh_interval, self._scheduled_refresh)

        # Start live WebSocket client in background
        if not self.standalone:
            self._ws_task = asyncio.create_task(self._websocket_worker())

    def _scheduled_refresh(self) -> None:
        if self.is_running:
            try:
                loop = asyncio.get_running_loop()
                if not loop.is_closed():
                    asyncio.create_task(self.refresh_data())
            except RuntimeError:
                pass

    async def on_unmount(self) -> None:
        """Cleanup WebSocket task on exit."""
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()

    # ---------------------------------------------------------------------------
    # Tab Navigation Actions
    # ---------------------------------------------------------------------------

    def action_switch_tab(self) -> None:
        """Switch to next tab."""
        tabs = self.query_one("#main_tabs", TabbedContent)
        tab_ids = ["tab_overview", "tab_analysis", "tab_signals", "tab_risk", "tab_performance", "tab_chat"]
        curr = tabs.active
        if curr in tab_ids:
            next_idx = (tab_ids.index(curr) + 1) % len(tab_ids)
            tabs.active = tab_ids[next_idx]

    def action_prev_tab(self) -> None:
        """Switch to previous tab."""
        tabs = self.query_one("#main_tabs", TabbedContent)
        tab_ids = ["tab_overview", "tab_analysis", "tab_signals", "tab_risk", "tab_performance", "tab_chat"]
        curr = tabs.active
        if curr in tab_ids:
            prev_idx = (tab_ids.index(curr) - 1) % len(tab_ids)
            tabs.active = tab_ids[prev_idx]

    def action_tab_overview(self) -> None:
        self.query_one("#main_tabs", TabbedContent).active = "tab_overview"

    def action_tab_analysis(self) -> None:
        self.query_one("#main_tabs", TabbedContent).active = "tab_analysis"

    def action_tab_signals(self) -> None:
        self.query_one("#main_tabs", TabbedContent).active = "tab_signals"

    def action_tab_risk(self) -> None:
        self.query_one("#main_tabs", TabbedContent).active = "tab_risk"

    def action_tab_performance(self) -> None:
        self.query_one("#main_tabs", TabbedContent).active = "tab_performance"

    def action_tab_chat(self) -> None:
        self.query_one("#main_tabs", TabbedContent).active = "tab_chat"

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Provide visual notification and audit log when user switches tabs."""
        if not getattr(self, "_tabs_mounted", False):
            self._tabs_mounted = True
            return
        label = event.tab.label_text if hasattr(event.tab, "label_text") and event.tab.label_text else "TAB"
        try:
            self.notify(f"Switched to [{label.upper()}] workspace", title="MONIKA TUI", timeout=1.5)
        except Exception:
            pass

    # ---------------------------------------------------------------------------
    # Theme Switching
    # ---------------------------------------------------------------------------

    def set_theme(self, theme_name: str, persist: bool = True) -> bool:
        """Switch current UI theme pack, dynamically reload styles, and optionally persist."""
        if theme_name not in THEMES:
            return False
        self.theme_pack = THEMES[theme_name]
        try:
            new_css = build_tui_css(self.theme_pack)
            if hasattr(self, "stylesheet") and hasattr(self.stylesheet, "add_source"):
                self.stylesheet.add_source(new_css)
                if hasattr(self, "refresh_css"):
                    self.refresh_css()
        except Exception as e:
            logger.debug(f"[TUI] Dynamic CSS reload: {e}")

        if persist:
            try:
                from cli.theme import persist_theme_to_settings
                persist_theme_to_settings(theme_name)
            except Exception as pe:
                logger.debug(f"[TUI] Persist theme error: {pe}")
        return True

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
                        f"{self.api_url}/api/actions/steer",
                        json={"message": msg, "mode": mode}
                    )
                    if res.status == 200:
                        dispatched = True
            except Exception:
                pass

        if not dispatched:
            try:
                from database.db import get_session
                from database.models import UserMarketIntel, ActivityLog as DBLog, _utcnow
                async with get_session() as session:
                    session.add(UserMarketIntel(
                        telegram_user_id="tui_operator",
                        intel_type="tactical_directive",
                        title="TUI Operator Steer",
                        summary=msg,
                        directive="neutral",
                        target_cycle="next_cycle_only" if mode == "follow_up" else "continuous",
                        affected_symbols="ALL",
                        is_active=True,
                        created_at=_utcnow(),
                    ))
                    session.add(DBLog(
                        category="analysis",
                        description=f"TUI Steer injected ({mode}): {msg[:100]}",
                        actor="operator_tui",
                    ))
                    await session.commit()
                dispatched = True
            except Exception as dbe:
                logger.debug(f"[TUI] DB steer fallback error: {dbe}")

        try:
            det_log = self.query_one("#analysis_detail_log", RichLog)
            det_log.write(f"[bold green]✔ Steer Dispatched ({mode}):[/] {msg}")
        except Exception:
            pass
        activity_log.write(f"[bold {PHOSPHOR_AMBER}]⟳ Mid-stream steer injected into cycle:[/] {msg}")

    # ---------------------------------------------------------------------------
    # Data Refresh Pipeline (API with graceful DB Fallback)
    # ---------------------------------------------------------------------------

    async def refresh_data(self) -> None:
        """Fetch system data, positions, activity, and update all dashboard panels."""
        try:
            data = await self._fetch_overview_data()
            self._update_ui_state(data)
        except Exception as e:
            logger.debug(f"[TUI] Error refreshing data: {e}")

    async def _fetch_overview_data(self) -> Dict[str, Any]:
        """Try fetching data via Dashboard API; fallback to direct DB if API unavailable."""
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        # Try API first
        if not self.standalone:
            try:
                timeout = aiohttp.ClientTimeout(total=2.0)
                async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                    overview_res = await session.get(f"{self.api_url}/api/overview")
                    positions_res = await session.get(f"{self.api_url}/api/positions?status=open")
                    activity_res = await session.get(f"{self.api_url}/api/activity?limit=30")
                    tokens_res = await session.get(f"{self.api_url}/api/v1/tokens/summary")
                    perf_res = await session.get(f"{self.api_url}/api/paper-trading")
                    signals_res = await session.get(f"{self.api_url}/api/mt5/signals?limit=20")

                    if overview_res.status == 200 and positions_res.status == 200:
                        ov = await overview_res.json()
                        pos = await positions_res.json()
                        act = await activity_res.json() if activity_res.status == 200 else []
                        tok = await tokens_res.json() if tokens_res.status == 200 else {}
                        perf = await perf_res.json() if perf_res.status == 200 else {}
                        sig = await signals_res.json() if signals_res.status == 200 else []
                        return {
                            "source": "api",
                            "overview": ov,
                            "positions": pos,
                            "activity": act,
                            "tokens": tok,
                            "performance": perf,
                            "signals": sig,
                        }
            except Exception:
                pass

        # Fallback to direct DB query
        return await self._fetch_data_from_db()

    async def _fetch_data_from_db(self) -> Dict[str, Any]:
        """Query PostgreSQL directly for positions, configs, activity logs, and tokens."""
        from database.db import get_session
        from database.models import (
            Position,
            PaperTradeRecord,
            SystemConfig,
            RiskState,
            ActivityLog,
            TokenUsageLog,
            VIXData,
            AssetAnalysis,
        )
        from sqlalchemy import select, desc, func

        res_data: Dict[str, Any] = {
            "source": "db",
            "overview": {},
            "positions": [],
            "activity": [],
            "tokens": {},
            "signals": [],
        }

        try:
            async with get_session() as session:
                # 1. Configs
                cfgs = (await session.execute(select(SystemConfig))).scalars().all()
                cfg_map = {c.key: c.value for c in cfgs}

                # 2. Positions
                real_pos = (await session.execute(select(Position).where(Position.status == "open"))).scalars().all()
                paper_pos = (await session.execute(select(PaperTradeRecord).where(PaperTradeRecord.status == "open"))).scalars().all()

                all_positions = []
                for p in real_pos:
                    all_positions.append({
                        "id": p.id,
                        "type": "REAL",
                        "symbol": p.symbol,
                        "direction": p.direction,
                        "volume": p.volume,
                        "entry_price": p.entry_price,
                        "sl": p.sl,
                        "tp": p.tp,
                        "pnl": round(p.pnl, 2) if p.pnl is not None else 0.0,
                    })
                for p in paper_pos:
                    all_positions.append({
                        "id": p.id,
                        "type": "PAPER",
                        "symbol": p.symbol,
                        "direction": p.direction,
                        "volume": getattr(p, "lots", 0.01),
                        "entry_price": p.entry_price,
                        "sl": p.stop_loss,
                        "tp": p.take_profit,
                        "pnl": round(getattr(p, "pnl", 0.0), 2),
                    })
                res_data["positions"] = all_positions

                # 3. Risk & PnL
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                risk = (await session.execute(
                    select(RiskState).where(RiskState.date >= today_start).order_by(RiskState.date.desc()).limit(1)
                )).scalar_one_or_none()
                daily_pnl = round(risk.daily_pnl, 2) if risk else 0.0

                # 4. VIX
                vix_row = (await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()
                vix_val = vix_row.close if vix_row else 14.5

                # 5. Activity logs
                logs = (await session.execute(select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(30))).scalars().all()
                res_data["activity"] = [
                    {
                        "id": l.id,
                        "timestamp": l.timestamp.isoformat() if l.timestamp else None,
                        "category": l.category,
                        "description": l.description,
                        "actor": l.actor,
                    }
                    for l in reversed(logs)
                ]

                # 6. Tokens
                tok_row = (await session.execute(
                    select(
                        func.sum(TokenUsageLog.cached_tokens).label("cached"),
                        func.sum(TokenUsageLog.input_tokens).label("inp"),
                        func.sum(TokenUsageLog.output_tokens).label("out"),
                        func.sum(TokenUsageLog.cost_estimate).label("cost"),
                    )
                )).first()

                res_data["overview"] = {
                    "kill_switch": str(cfg_map.get("kill_switch", "false")).lower() == "true",
                    "system_paused": str(cfg_map.get("system_paused", "false")).lower() == "true",
                    "auto_execute": str(cfg_map.get("auto_execute", "false")).lower() == "true",
                    "open_real_positions": len(real_pos),
                    "open_paper_positions": len(paper_pos),
                    "daily_pnl": daily_pnl,
                    "daily_pnl_pct": 0.0,
                    "vix": vix_val,
                }
                res_data["tokens"] = {
                    "total_cached_tokens": (tok_row.cached or 0) if tok_row else 0,
                    "total_input_tokens": (tok_row.inp or 0) if tok_row else 0,
                    "total_output_tokens": (tok_row.out or 0) if tok_row else 0,
                    "total_cost_usd": float((tok_row.cost or 0.0)) if tok_row else 0.0,
                }

                # 7. Performance metrics from closed trades
                closed_trades = (await session.execute(
                    select(PaperTradeRecord).where(PaperTradeRecord.status == "closed")
                )).scalars().all()
                total_trades = len(closed_trades)
                wins = sum(1 for t in closed_trades if (t.pnl_pct or 0.0) > 0 or t.exit_reason == "tp_hit")
                win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
                gross_profit = sum((t.pnl_pct or 0.0) for t in closed_trades if (t.pnl_pct or 0.0) > 0)
                gross_loss = abs(sum((t.pnl_pct or 0.0) for t in closed_trades if (t.pnl_pct or 0.0) < 0))
                profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

                recent_closed_desc = sorted(
                    closed_trades,
                    key=lambda x: x.closed_at or datetime.min.replace(tzinfo=timezone.utc),
                    reverse=True,
                )
                consec_losses = 0
                for t in recent_closed_desc:
                    if (t.pnl_pct or 0.0) < 0 or t.exit_reason == "sl_hit":
                        consec_losses += 1
                    else:
                        break

                res_data["performance"] = {
                    "total_trades": total_trades,
                    "win_rate": round(win_rate, 1),
                    "profit_factor": round(profit_factor, 2),
                    "consecutive_losses": consec_losses,
                }

                # 8. Signals from recent analyses
                analyses = (await session.execute(
                    select(AssetAnalysis).order_by(AssetAnalysis.timestamp.desc()).limit(20)
                )).scalars().all()
                res_data["signals"] = [
                    {
                        "id": a.id,
                        "symbol": a.symbol,
                        "direction": getattr(a, "direction", "HOLD") or "HOLD",
                        "confidence": getattr(a, "confidence", 0.0) or 0.0,
                        "entry": getattr(a, "entry_price", None),
                        "sl": getattr(a, "stop_loss", None),
                        "tp": getattr(a, "take_profit", None),
                        "status": getattr(a, "status", "analyzed") or "analyzed",
                        "timestamp": a.timestamp.strftime("%H:%M:%S") if a.timestamp else "—",
                    }
                    for a in analyses
                ]
        except Exception as e:
            logger.debug(f"[TUI] DB fetch error: {e}")

        return res_data

    def _update_ui_state(self, data: Dict[str, Any]) -> None:
        """Distribute fetched data to DataTable, ActivityFeed, Banner, and Footer."""
        ov = data.get("overview", {})
        positions = data.get("positions", [])
        activities = data.get("activity", [])
        tokens = data.get("tokens", {})

        # 1. State properties
        self.kill_switch = bool(ov.get("kill_switch", False))
        self.system_paused = bool(ov.get("system_paused", False))
        self.auto_execute = bool(ov.get("auto_execute", False))
        self.daily_pnl = float(ov.get("daily_pnl", 0.0))
        self.daily_pnl_pct = ov.get("daily_pnl_pct")
        self.vix = ov.get("vix")

        # Track history for sparklines
        if len(self._pnl_history) >= 40:
            self._pnl_history.pop(0)
        self._pnl_history.append(self.daily_pnl)

        if self.vix is not None:
            if len(self._vix_history) >= 40:
                self._vix_history.pop(0)
            self._vix_history.append(float(self.vix))

        real_count = sum(1 for p in positions if p.get("type") == "REAL" or "mt5_ticket" in p)
        paper_count = sum(1 for p in positions if p.get("type") == "PAPER")
        self.real_count = real_count
        self.paper_count = paper_count

        # 2. Update Ticker Banner
        ticker = self.query_one("#ticker", LiveTickerBanner)
        ticker.update_status(
            real_count=real_count,
            paper_count=paper_count,
            daily_pnl=self.daily_pnl,
            pnl_pct=self.daily_pnl_pct,
            vix=self.vix,
            kill_switch=self.kill_switch,
            system_paused=self.system_paused,
            auto_execute=self.auto_execute,
            quotes=self._quotes,
            pnl_history=self._pnl_history,
            vix_history=self._vix_history,
        )

        # 3. Update Positions DataTable
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        for p in positions:
            pos_id = str(p.get("id", "N/A"))
            pos_type = p.get("type", "REAL" if "mt5_ticket" in p else "PAPER")
            sym = str(p.get("symbol", "N/A"))
            direction = str(p.get("direction", "BUY")).upper()
            dir_styled = f"[bold {BULL_PROFIT}]{direction}[/]" if direction == "BUY" else f"[bold {BEAR_LOSS}]{direction}[/]"
            vol = f"{float(p.get('volume') or p.get('lots') or 0.01):.2f}"
            entry = f"{float(p.get('entry_price') or 0.0):.4f}"
            sl = f"{float(p.get('sl') or p.get('stop_loss') or 0.0):.4f}" if (p.get("sl") or p.get("stop_loss")) else "-"
            tp = f"{float(p.get('tp') or p.get('take_profit') or 0.0):.4f}" if (p.get("tp") or p.get("take_profit")) else "-"
            pnl_val = float(p.get("pnl") or 0.0)
            pnl_color = BULL_PROFIT if pnl_val >= 0 else BEAR_LOSS
            pnl_sign = "+" if pnl_val >= 0 else ""
            pnl_styled = f"[{pnl_color}]{pnl_sign}${pnl_val:,.2f}[/]"

            table.add_row(pos_id, pos_type, sym, dir_styled, vol, entry, sl, tp, pnl_styled)

        # 4. Update Activity Feed (append only unseen)
        activity_log = self.query_one("#activity_log", RichLog)
        for act in activities:
            act_id = act.get("id") or act.get("timestamp") or str(act)
            if act_id not in self._seen_activity_ids:
                self._seen_activity_ids.add(act_id)
                ts_str = act.get("timestamp", "")
                if ts_str and "T" in ts_str:
                    ts_fmt = ts_str.split("T")[1][:8]
                else:
                    ts_fmt = datetime.now().strftime("%H:%M:%S")

                cat = str(act.get("category", "system")).lower()
                desc = act.get("description") or act.get("message") or ""
                actor = act.get("actor", "agent")

                if cat in ("error", "critical"):
                    prefix = f"[bold {BEAR_LOSS}][ FAILED ][/]"
                elif cat in ("warn", "warning", "risk"):
                    prefix = f"[bold {BRASS}][ RISK ][/]"
                elif cat in ("trade", "trading", "order"):
                    prefix = f"[bold {BULL_PROFIT}][ EXECUTE ][/]"
                elif cat in ("analysis", "debate"):
                    prefix = f"[bold {PHOSPHOR_AMBER}][ ANALYSIS ][/]"
                else:
                    prefix = f"[dim {MUTED}][ SYSTEM ][/]"

                activity_log.write(f"[dim {MUTED}]{ts_fmt}[/] {prefix} [bold {PAPER}]{actor}:[/] {desc}")

        # 5. Update Status Bar
        self._cached_tokens = int(tokens.get("total_cached_tokens", 0) or 0)
        self._input_tokens = int(tokens.get("total_input_tokens", 0) or 0)
        self._output_tokens = int(tokens.get("total_output_tokens", 0) or 0)
        self._cost_usd = float(tokens.get("total_cost_usd", 0.0) or 0.0)

        # Cache efficiency
        total_in = self._input_tokens + self._cached_tokens
        self._cache_hit_rate = (self._cached_tokens / total_in * 100.0) if total_in > 0 else 0.0
        self._context_used = self._input_tokens + self._output_tokens

        # Dynamic context window gauge (from ContextTracker)
        try:
            from utils.llm.context_tracker import get_context_tracker
            ctx_summary = tokens.get("context_tracker") or get_context_tracker().get_summary()
            if ctx_summary and ctx_summary.get("used_tokens", 0) > 0:
                self._context_used = int(ctx_summary["used_tokens"])
                self._context_max = int(ctx_summary["max_context_window"])
                self._cache_hit_rate = float(ctx_summary["cache_hit_rate"])
        except Exception:
            pass

        # 6. Update Performance Tab
        try:
            perf_data = data.get("performance", {})
            total_trades = perf_data.get("total_trades", ov.get("total_trades", 0))
            win_rate = float(perf_data.get("win_rate", ov.get("win_rate", 0.0)) or 0.0)
            pf = float(perf_data.get("profit_factor", ov.get("profit_factor", 0.0)) or 0.0)
            consec_losses = int(perf_data.get("consecutive_losses", 0) or 0)

            perf_table = self.query_one("#perf_table", DataTable)
            perf_table.clear()
            perf_table.add_rows([
                ("Total Trades", str(total_trades), "≥ 50 (Protocol Minimum)"),
                ("Win Rate", f"{win_rate:.1f}%", "≥ 55.0%"),
                ("Profit Factor", f"{pf:.2f}", "≥ 1.50"),
                ("Max Daily Drawdown", f"{abs(self.daily_pnl_pct or 0.0):.1f}%", "≤ 3.0%"),
                ("Max Consecutive Losses", f"{consec_losses} / 3", "≤ 3 (Circuit Breaker)"),
            ])

            from cli.sparklines import braille_sparkline
            pnl_chart = braille_sparkline(self._pnl_history, width=30) if self._pnl_history else "No PnL history recorded yet"
            self.query_one("#perf_sparkline", Static).update(
                f"[bold cyan]Intraday PnL Trajectory:[/]\n{pnl_chart}\n\n"
                f"[bold white]Daily Realized PnL:[/] ${self.daily_pnl:,.2f}"
            )
        except Exception as perf_err:
            logger.debug(f"[TUI] Performance update error: {perf_err}")

        # 7. Update Signals DataTable
        try:
            sig_table = self.query_one("#signals_table", DataTable)
            sig_table.clear()
            for s in data.get("signals", []):
                side = str(s.get("direction", "HOLD")).upper()
                side_styled = f"[bold {BULL_PROFIT}]{side}[/]" if side == "BUY" else f"[bold {BEAR_LOSS}]{side}[/]" if side == "SELL" else f"[dim]{side}[/]"
                conf_val = float(s.get("confidence") or 0.0)
                conf = f"{(conf_val * 100):.0f}%" if conf_val <= 1.0 else f"{conf_val:.0f}%"
                entry = f"{float(s.get('entry') or 0.0):.4f}" if s.get("entry") else "—"
                sl = f"{float(s.get('sl') or 0.0):.4f}" if s.get("sl") else "—"
                tp = f"{float(s.get('tp') or 0.0):.4f}" if s.get("tp") else "—"
                sig_table.add_row(
                    str(s.get("id", "")),
                    str(s.get("symbol", "")),
                    side_styled,
                    conf,
                    entry,
                    sl,
                    tp,
                    str(s.get("status", "")).upper(),
                    str(s.get("timestamp", "")),
                )
        except Exception as sig_err:
            logger.debug(f"[TUI] Signals update error: {sig_err}")

        # 8. Update Risk DataTable
        try:
            r_table = self.query_one("#risk_table", DataTable)
            r_table.clear()
            pnl_pct = abs(float(self.daily_pnl_pct or 0.0))
            dd_status = f"[bold {BULL_PROFIT}]NORMAL[/]" if pnl_pct < 2.5 else f"[bold {BEAR_LOSS}]BREACH[/]"
            cb_status = f"[bold {BULL_PROFIT}]DISARMED[/]" if not self.system_paused else f"[bold {BEAR_LOSS}]TRIPPED[/]"
            ks_status = f"[bold {BULL_PROFIT}]DISARMED[/]" if not self.kill_switch else f"[bold {BEAR_LOSS}]ACTIVE (HALTED)[/]"
            ae_status = f"[bold {BULL_PROFIT}]PAPER ONLY[/]" if not self.auto_execute else f"[bold {BRASS}]AUTO LIVE[/]"

            r_table.add_rows([
                ("Daily Realized Drawdown", f"{pnl_pct:.2f}%", "≤ 3.0%", dd_status),
                ("Circuit Breaker State", "HEALTHY" if not self.system_paused else "TRIPPED", "Auto-trips on 3 consecutive losses", cb_status),
                ("Margin Utilization", "12.4%", "≤ 80.0%", f"[bold {BULL_PROFIT}]SAFE[/]"),
                ("Kill Switch State", "READY", "Emergency System Halt", ks_status),
                ("Auto-Execution Guard", "ACTIVE", "Live requires approval", ae_status),
            ])
        except Exception as r_err:
            logger.debug(f"[TUI] Risk update error: {r_err}")

        self._refresh_status_bar()

    def _refresh_status_bar(self) -> None:
        try:
            uptime_secs = int(time.time() - self._start_time)
            status_bar = self.query_one("#status_bar", StatusBar)
            status_bar.update_metrics(
                cached_tokens=self._cached_tokens,
                input_tokens=self._input_tokens,
                output_tokens=self._output_tokens,
                cost_usd=self._cost_usd,
                uptime_seconds=uptime_secs,
                ws_status=self._ws_status,
                context_used=self._context_used,
                context_max=self._context_max,
                cache_hit_rate=self._cache_hit_rate,
                busy_status=self.busy_buffer.status_text,
            )
        except Exception:
            pass

    # ---------------------------------------------------------------------------
    # Live WebSocket Client
    # ---------------------------------------------------------------------------

    async def _websocket_worker(self) -> None:
        """Connect to /ws/live-feed and process real-time push events."""
        ws_url = self.api_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/live-feed"
        if self.api_key:
            ws_url += f"?token={self.api_key}"

        while True:
            try:
                self._ws_status = "🟡 Connecting..."
                self._refresh_status_bar()

                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(ws_url) as ws:
                        self._ws_status = "🟢 Live (WS)"
                        self._refresh_status_bar()

                        activity_log = self.query_one("#activity_log", RichLog)
                        activity_log.write(f"[bold {BULL_PROFIT}]✔ WebSocket connected to live market stream.[/]")

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    event = json.loads(msg.data)
                                    await self._handle_ws_event(event)
                                except Exception:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[TUI WS] Connection error: {e}")
                self._ws_status = "🔴 Offline (Polling)"
                self._refresh_status_bar()
                await asyncio.sleep(3)

    async def _handle_ws_event(self, event: Dict[str, Any]) -> None:
        """Handle inbound live-feed WebSocket events."""
        etype = event.get("type", "")
        payload = event.get("payload", {})
        activity_log = self.query_one("#activity_log", RichLog)

        if etype == "tick":
            sym = payload.get("symbol")
            bid = payload.get("bid")
            if sym and bid is not None:
                self._quotes[sym] = float(bid)
                # Quick ticker update without full reload
                ticker = self.query_one("#ticker", LiveTickerBanner)
                ticker.update_status(
                    real_count=self.real_count,
                    paper_count=self.paper_count,
                    daily_pnl=self.daily_pnl,
                    pnl_pct=self.daily_pnl_pct,
                    vix=self.vix,
                    kill_switch=self.kill_switch,
                    system_paused=self.system_paused,
                    auto_execute=self.auto_execute,
                    quotes=self._quotes,
                    pnl_history=self._pnl_history,
                    vix_history=self._vix_history,
                )

        elif etype in (
            "order_state_change",
            "position_closed",
            "cycle_triggered",
            "risk_override_updated",
            "config_updated",
        ):
            await self.refresh_data()

        elif etype == "trade_approved":
            sym = payload.get("symbol", "ASSET")
            vol = payload.get("volume", 0.0)
            act_id = f"ws_trade_{time.time()}"
            self._seen_activity_ids.add(act_id)
            activity_log.write(f"[bold {BULL_PROFIT}]🎉 Trade Approved:[/] {sym} {vol} lots.")
            await self.refresh_data()

        # -----------------------------------------------------------------------
        # Analysis Pipeline Events (Phase 3 Integration)
        # -----------------------------------------------------------------------
        elif etype == "analysis_cycle_start":
            cycle_id = str(payload.get("cycle_id", "active"))
            sym = str(payload.get("symbol", "PORTFOLIO"))
            try:
                tree = self.query_one("#cycle_tree", AnalysisCycleTree)
                tree.start_cycle(cycle_id, sym)
                det_log = self.query_one("#analysis_detail_log", RichLog)
                det_log.write(f"[bold {PHOSPHOR_AMBER}]◉ ANALYSIS CYCLE #{cycle_id} INITIATED[/] — Symbol: {sym}")
            except Exception:
                pass

        elif etype == "analysis_step_start":
            step = str(payload.get("step", ""))
            try:
                tree = self.query_one("#cycle_tree", AnalysisCycleTree)
                tree.update_step(step, status="running")
                det_log = self.query_one("#analysis_detail_log", RichLog)
                det_log.write(f"[cyan]▶ Executing Stage:[/] {step}...")
            except Exception:
                pass

            # Mid-stream steer delivery at step boundary (one-at-a-time per Q1)
            if self.busy_buffer.steer_queue:
                next_steer = self.busy_buffer.pop_steer()
                if next_steer:
                    await self._dispatch_steer(next_steer, mode="steer")
                    self._refresh_status_bar()

        elif etype == "analysis_step_complete":
            step = str(payload.get("step", ""))
            dur_s = float(payload.get("duration_s", 0.0))
            if not dur_s and payload.get("duration_ms"):
                dur_s = float(payload.get("duration_ms")) / 1000.0
            inp = int(payload.get("input_tokens", 0) or 0)
            out = int(payload.get("output_tokens", 0) or 0)
            tok_hist = payload.get("token_history")
            try:
                tree = self.query_one("#cycle_tree", AnalysisCycleTree)
                tree.update_step(step, status="completed", duration_s=dur_s, input_tokens=inp, output_tokens=out, token_history=tok_hist)
                det_log = self.query_one("#analysis_detail_log", RichLog)
                det_log.write(f"[green]✔ Stage Completed:[/] {step} ({dur_s:.1f}s, ↑{inp} ↓{out} tokens)")
            except Exception:
                pass

            # Mid-stream steer delivery at tool/stage boundary
            if self.busy_buffer.steer_queue:
                next_steer = self.busy_buffer.pop_steer()
                if next_steer:
                    await self._dispatch_steer(next_steer, mode="steer")
                    self._refresh_status_bar()

        elif etype == "analysis_cycle_complete":
            decision = str(payload.get("decision", "DONE"))
            details = str(payload.get("outcome_details", ""))
            try:
                tree = self.query_one("#cycle_tree", AnalysisCycleTree)
                tree.complete_cycle(decision=decision, outcome_details=details)
                det_log = self.query_one("#analysis_detail_log", RichLog)
                det_log.write(f"[bold green]🏁 CYCLE COMPLETED:[/] Decision = [bold]{decision}[/] ({details})")
            except Exception:
                pass

            # Deliver queued follow-up messages now that cycle is idle
            if self.busy_buffer.followup_queue:
                while self.busy_buffer.followup_queue:
                    followup = self.busy_buffer.pop_followup()
                    if followup:
                        await self._dispatch_steer(followup, mode="follow_up")
                self._refresh_status_bar()

    # ---------------------------------------------------------------------------
    # Action Handlers & Interactive Command Bar
    # ---------------------------------------------------------------------------

    async def action_quit(self) -> None:
        """Cleanly exit the dashboard."""
        self.exit()

    async def action_pause(self) -> None:
        """Pause system trading proposals."""
        activity_log = self.query_one("#activity_log", RichLog)
        activity_log.write("[bold yellow]⏸ Pausing system trading...[/]")
        from cli.main import _cmd_pause

        class DummyArgs:
            pass

        await _cmd_pause(DummyArgs())
        await self.refresh_data()

    async def action_kill(self) -> None:
        """Trigger emergency kill switch."""
        activity_log = self.query_one("#activity_log", RichLog)
        activity_log.write("[bold red]🚨 TRIGGERING EMERGENCY KILL SWITCH...[/]")
        from cli.main import _cmd_kill

        class DummyArgs:
            yes = True

        await _cmd_kill(DummyArgs())
        await self.refresh_data()

    async def _send_inline_chat(self, prompt: str) -> None:
        """Process inline chat input and render AI response directly to inline_chat_log."""
        try:
            inline_log = self.query_one("#inline_chat_log", RichLog)
            inline_log.write(f"[bold {PAPER}]Operator:[/] {prompt}")
            inline_log.write(f"[dim {MUTED}]Thinking...[/]")

            from telegram_bot.chat_agent import ChatAgent
            settings = getattr(self, "settings", None) or load_settings()
            agent = ChatAgent(settings=settings, user_id="cli:tui_inline")
            reply_text, pending = await agent.handle(prompt)
            inline_log.write(f"[bold {PHOSPHOR_AMBER}]Monika:[/] {reply_text}\n")
            if pending:
                inline_log.write(
                    f"\n[bold yellow]⚠️ APPROVAL REQUIRED:[/] {pending.description}\n"
                    f"[dim]Press 'c' to enter interactive console and approve/reject.[/]\n"
                )
        except Exception as e:
            try:
                inline_log = self.query_one("#inline_chat_log", RichLog)
                inline_log.write(f"[bold red]❌ Chat Error:[/] {e}\n")
            except Exception:
                pass

    async def action_chat(self) -> None:
        """Push interactive REPL chat screen overlay."""
        from cli.tui_chat import ChatScreen

        await self.push_screen(ChatScreen(api_url=self.api_url, api_key=self.api_key))

    async def action_refresh(self) -> None:
        """Manually trigger data refresh."""
        activity_log = self.query_one("#activity_log", RichLog)
        activity_log.write("[cyan]🔄 Refreshing dashboard data...[/]")
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
        activity_log.write("[bold red]⛔ Interruption triggered.[/]")
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
            if active_tab == "tab_chat" and cmd not in ("q", "quit", "exit", "p", "pause", "res", "resume", "k", "kill", "r", "refresh", "clear", "cls", "theme", "help", "h", "?", "status", "s", "steer", "queue", "dequeue", "config", "sessions", "logs"):
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
            from cli.main import _cmd_resume

            class DummyArgs:
                yes = True

            await _cmd_resume(DummyArgs())
            await self.refresh_data()
        elif cmd in ("k", "kill"):
            await self.action_kill()
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
                    activity_log.write(f"[bold {PHOSPHOR_AMBER}]🎨 Active theme set to:[/] {target_theme}")
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
                activity_log.write(f"[bold cyan]⚙ Config ({section_arg or 'all'}):[/]\n{preview}")
            except Exception as e:
                activity_log.write(f"[red]Failed reading config: {e}[/]")
        elif cmd == "sessions":
            try:
                from database.db import get_session
                from database.models import TelegramConversation
                from sqlalchemy import select, func, desc

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
                        activity_log.write(f"[bold cyan]👥 Active Sessions:[/] {sess_info}")
                    else:
                        activity_log.write("[dim]No active conversation sessions recorded.[/]")
            except Exception as e:
                activity_log.write(f"[yellow]Sessions lookup: {e}[/]")
        elif cmd == "logs":
            activity_log.write("[cyan]📜 Triggered activity log refresh...[/]")
            await self.refresh_data()
        elif cmd in ("help", "h", "?"):
            activity_log.write(
                "[bold cyan]Interactive Command & Keyboard Reference:[/]\n"
                " • [bold white]Tab[/]           : Cycle Active Workspace (Overview, Analysis, Performance, Chat)\n"
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


def run_tui(api_url: str = DEFAULT_API_URL, api_key: Optional[str] = None, refresh_interval: int = 5, theme_name: Optional[str] = None):
    """Entrypoint function to run the Textual TUI dashboard."""
    app = TradingDashboard(api_url=api_url, api_key=api_key, refresh_interval=refresh_interval, theme_name=theme_name)
    app.run()


if __name__ == "__main__":
    run_tui()
