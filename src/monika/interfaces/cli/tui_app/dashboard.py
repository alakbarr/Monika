# ==============================================================================
# File: interfaces/cli/tui_app/dashboard.py
# Description: Core TradingDashboard App for Monika Rich Terminal Dashboard
# ==============================================================================

import asyncio
import os
import time
from typing import Any, ClassVar, Dict, List, Optional, Set

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
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

from monika.core.config.settings import load_settings
from monika.interfaces.cli.analysis_tree import AnalysisCycleTree
from monika.interfaces.cli.busy_input import BusyInputBuffer, InputDelivery
from monika.interfaces.cli.theme import (
    MUTED,
    PHOSPHOR_AMBER,
    ThemePack,
    build_tui_css,
    get_theme,
)
from monika.interfaces.cli.tui_app.constants import (
    COMMAND_SUGGESTIONS,
    DEFAULT_API_URL,
    DETERMINISTIC_RISK_CHECKS,
)
from monika.interfaces.cli.tui_app.mixins import (
    ActionsMixin,
    DataSyncMixin,
    NavigationMixin,
    PluginsBenchmarkMixin,
    WebSocketMixin,
)
from monika.interfaces.cli.tui_app.widgets import LiveTickerBanner, StatusBar


class TradingDashboard(
    NavigationMixin,
    PluginsBenchmarkMixin,
    DataSyncMixin,
    WebSocketMixin,
    ActionsMixin,
    App,
):
    """
    Rich terminal dashboard for Monika AI Trading Agent using Textual.

    Features:
    - Tabbed view: Overview, Analysis, Signals, Risk, Performance, Market, Plugins, Benchmark, Chat
    - Live position table (WebSocket or REST polling fallback)
    - LangGraph 7-node analysis tree with sparklines
    - Interactive command bar with autocomplete and dual-queue steer/follow-up
    - Multi-theme engine (retro_vintage, modern_dark, high_contrast, daylight)
    - Keybindings: q quit, p pause, k kill, c chat, r refresh, Tab switch tabs
    """

    TITLE = "TradeAgent — Terminal Dashboard"

    BINDINGS = [
        Binding("f1", "help", "F1 Help", show=True),
        Binding("f2", "tab_overview", "F2 Desk", show=True),
        Binding("f3", "tab_analysis", "F3 Intel", show=True),
        Binding("f4", "tab_performance", "F4 Perf", show=True),
        Binding("f5", "tab_chat", "F5 Chat", show=True),
        Binding("f6", "tab_plugins", "F6 Plug", show=True),
        Binding("f8", "pause", "F8 Pause", show=True),
        Binding("f9", "kill", "F9 Kill", show=True),
        Binding("f10", "quit", "F10 Quit", show=True),
        Binding("tab", "switch_tab", "Next Tab", show=False),
        Binding("shift+tab", "prev_tab", "Prev Tab", show=False),
        Binding("1", "tab_overview", "Overview", show=False),
        Binding("2", "tab_analysis", "Analysis", show=False),
        Binding("3", "tab_performance", "Performance", show=False),
        Binding("4", "tab_chat", "Chat", show=False),
        Binding("q", "quit", "Quit", show=False),
        Binding("p", "pause", "Pause Trading", show=False),
        Binding("c", "chat", "Chat Mode", show=False),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("t", "toggle_plugin", "Toggle ON/OFF", show=False),
        Binding("i", "install_plugin", "Install Plugin", show=False),
        Binding("colon", "focus_input", "Command Bar", show=False),
        Binding("escape", "blur_input", "Unfocus Bar", show=False),
        Binding("ctrl+c", "quit", "Quit", show=False),
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
        **kwargs: Any,
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
        self.theme_pack: ThemePack = get_theme(theme_name)
        TradingDashboard.CSS = build_tui_css(self.theme_pack)

        # Dual-queue busy input buffer (default 'one-at-a-time' per Q1)
        self.busy_buffer = BusyInputBuffer(default_mode=InputDelivery.STEER, delivery_mode="one-at-a-time")

        self._start_time = time.time()
        self._seen_activity_ids: Set[Any] = set()
        self._seen_analysis_ids: Set[Any] = set()
        self._ws_status = "[OFFLINE] Disconnected"
        self._ws_task: Optional[asyncio.Task[Any]] = None
        self._quotes: Dict[str, float] = {}
        self._cached_tokens: int = 0
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._cost_usd: float = 0.0
        self._context_used: int = 0
        self._context_max: int = 200000
        self._cache_hit_rate: float = 0.0
        self._budget_tier: str = "T1 (100%)"

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
        self._refresh_lock = asyncio.Lock()
        self._inline_chat_agent: Optional[Any] = None
        self.terminal_width: int = 100
        self._positions_narrow_mode: bool = False

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
            with TabPane("Market", id="tab_market"):
                with Horizontal(id="market_horizontal"):
                    with Vertical(id="market_macro_container"):
                        yield Static("MACRO CALENDAR & SENTIMENT", classes="panel_title")
                        yield DataTable(id="market_table", zebra_stripes=True)
                    with Vertical(id="market_rates_container"):
                        yield Static("CENTRAL BANK & YIELD CURVE", classes="panel_title")
                        yield DataTable(id="market_rates_table", zebra_stripes=True)
            with TabPane("Plugins", id="tab_plugins"):
                with Vertical(id="plugins_container"):
                    yield Static(
                        "PLUG-IN HARNESS & MARKETPLACE LEDGER (Press [t] to toggle ON/OFF, [i] to install via pip)",
                        classes="panel_title",
                    )
                    yield DataTable(id="plugins_table", zebra_stripes=True)
            with TabPane("Benchmark", id="tab_benchmark"):
                with Vertical(id="benchmark_container"):
                    yield Static(
                        "LLM MODEL LAB & BENCHMARK LEADERBOARD (Press [b] to switch, [r] to refresh)",
                        classes="panel_title",
                    )
                    yield DataTable(id="benchmark_table", zebra_stripes=True)
            with TabPane("Chat", id="tab_chat"):
                with Vertical(id="chat_tab_container"):
                    yield Static("INTERACTIVE DESK CONSOLE (Press 'c' for full screen)", classes="panel_title")
                    yield RichLog(id="inline_chat_log", wrap=True, highlight=True, markup=True)
        yield Input(
            id="cmd_input",
            placeholder="Commands: [s]tatus [p]ause [res]ume [k]ill [c]hat [r]efresh [plugin] [config] [theme] [steer] [queue] [help] [q]uit",
            suggester=SuggestFromList(COMMAND_SUGGESTIONS + ["plugin", "plugins", "install"], case_sensitive=False),
        )
        yield StatusBar(id="status_bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize UI widgets, start WebSocket listener and polling timer."""
        # Setup DataTable with progressive width budgeting
        table = self.query_one("#positions_table", DataTable)
        self._positions_narrow_mode = getattr(self, "terminal_width", 100) < 90
        if self._positions_narrow_mode:
            table.add_columns("Symbol", "Side", "Lots", "Entry", "PnL")
        else:
            table.add_columns("ID", "Type", "Symbol", "Side", "Lots", "Entry", "SL", "TP", "PnL")

        # Setup Signals Table
        signals_table = self.query_one("#signals_table", DataTable)
        signals_table.add_columns("ID", "Symbol", "Side", "Confidence", "Price", "SL", "TP", "Status", "Timestamp")

        # Setup Risk Table
        risk_table = self.query_one("#risk_table", DataTable)
        risk_table.add_columns("Risk Metric", "Current Value", "Safety Threshold", "Status")
        risk_table.add_rows(DETERMINISTIC_RISK_CHECKS)

        # Setup Performance Table
        perf_table = self.query_one("#perf_table", DataTable)
        perf_table.add_columns("Metric", "Value", "Benchmark / Limit")
        perf_table.add_rows(
            [
                ("Total Trades", "0", "≥ 50 (Protocol Minimum)"),
                ("Win Rate", "0.0%", "≥ 55.0%"),
                ("Profit Factor", "0.00", "≥ 1.50"),
                ("Max Daily Drawdown", "0.0%", "≤ 3.0%"),
                ("Max Consecutive Losses", "0", "≤ 3 (Circuit Breaker)"),
            ]
        )

        # Setup Market Table
        market_table = self.query_one("#market_table", DataTable)
        market_table.add_columns("Time", "Currency", "Macro Event", "Impact", "Forecast", "Actual")
        market_table.add_rows(
            [
                ("03:00 UTC", "JPY", "Bank of Japan (BoJ) Interest Rate Decision", "HIGH", "1.25%", "—"),
                ("06:00 UTC", "GBP", "UK Core Retail Sales (MoM)", "MEDIUM", "-0.2%", "—"),
                ("13:15 UTC", "USD", "US Industrial Production (MoM)", "MEDIUM", "0.3%", "—"),
                ("14:00 UTC", "USD", "US Leading Economic Index (MoM)", "MEDIUM", "0.1%", "—"),
            ]
        )

        # Setup Market Rates Table
        market_rates_table = self.query_one("#market_rates_table", DataTable)
        market_rates_table.add_columns("Benchmark", "Rate / Yield", "Spread / Bias", "Outlook")
        market_rates_table.add_rows(
            [
                ("FOMC Fed Funds", "5.25% - 5.50%", "Hold: 85.2%", "Dovish Pause"),
                ("US Treasury 2Y", "4.15%", "Tenor Benchmark", "Neutral"),
                ("US Treasury 10Y", "4.38%", "2s10s: +0.23%", "Normal Curve"),
                ("Fear & Greed Index", "50 / 100", "Neutral", "Balanced"),
            ]
        )

        # Setup Activity Log
        log = self.query_one("#activity_log", RichLog)
        log.write(
            f"[bold {PHOSPHOR_AMBER}][ INITIALIZATION ][/] Monika Terminal TUI Active (Theme: {self.theme_pack.name})"
        )
        log.write(f"[dim {MUTED}]Connecting to market data feed...[/]")

        # Setup Analysis Detail Log
        analysis_log = self.query_one("#analysis_detail_log", RichLog)
        analysis_log.write(f"[dim {MUTED}]Analysis pipeline ready for cycle execution stream...[/]")

        # Setup Inline Chat Log
        inline_chat = self.query_one("#inline_chat_log", RichLog)
        inline_chat.write(f"[bold {PHOSPHOR_AMBER}][ DESK CONSOLE ][/] Monika Autonomous AI Desk Console Ready.")
        inline_chat.write(
            f"[dim {MUTED}]Type your query in the bottom input bar to chat inline, or press 'c' for full overlay.[/]\n"
        )

        # Setup Plugins Table
        plugins_table = self.query_one("#plugins_table", DataTable)
        plugins_table.cursor_type = "row"
        plugins_table.add_columns("ID", "Name", "Category", "Ver", "Origin", "Status", "Description")
        asyncio.create_task(self.refresh_plugins_table())

        # Setup Benchmark Table
        bench_table = self.query_one("#benchmark_table", DataTable)
        bench_table.cursor_type = "row"
        bench_table.add_columns("Rank", "Model", "Avg Score", "Pass Rate", "Avg Latency", "Avg Cost", "Tasks")
        asyncio.create_task(self.refresh_benchmark_table())

        # Initial refresh
        await self.refresh_data()

        # Start periodic polling timer
        self.set_interval(self.refresh_interval, self._scheduled_refresh)

        # Start live WebSocket client in background
        if not self.standalone:
            self._ws_task = asyncio.create_task(self._websocket_worker())

    async def on_unmount(self) -> None:
        """Cleanup WebSocket task on exit."""
        if self._ws_task and not self._ws_task.done():
            self._ws_task.cancel()
