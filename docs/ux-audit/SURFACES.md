# SURFACES — Inventarisasi Lengkap Antarmuka Monika

Daftar lengkap 44 surface hasil penelusuran kode (`navigation.ts`, `App.tsx`, komponen UI/Overlays, dan `cli/tui*.py`).

| ID | Nama & Komponen | Arketipe | Entry Path / Trigger | Required States | Tugas Kritis | Status It.1 |
|---|---|---|---|---|---|---|
| **WEB-SHELL-HEADER** | Header Taskbar (`Header.tsx`) | A10 Shell | Persistent Topbar | default, live-mode, paper-mode, disconnected | T1 | Terinventarisasi |
| **WEB-SHELL-SIDEBAR** | Sidebar Navigation (`Sidebar.tsx`) | A10 Shell | Persistent Left Nav | expanded, collapsed, active-item, hover | — | Terinventarisasi |
| **WEB-SHELL-STATUSBAR** | Global Status Bar (`GlobalStatusBar.tsx`) | A10 Shell | Persistent Bottom Bar | normal, warning, halted, disconnected | T1, T4 | Terinventarisasi |
| **WEB-SHELL-BREADCRUMB** | Breadcrumb Bar (`BreadcrumbBar.tsx`) | A10 Shell | Sub-header strip | default | — | Terinventarisasi |
| **WEB-SHELL-TICKER** | Live Ticker Ribbon (`TickerTape.tsx`) | A10 Shell | Sub-header ticker | live, waiting-quotes | T1 | Terinventarisasi |
| **WEB-TRD-OVERVIEW** | Trading Desk Overview (`OverviewTab`) | A1 Monitor | Nav: Workspace 1 > Tab 1 (`Key 1`) | populated, empty, loading, error, stale | T1 | Terinventarisasi |
| **WEB-TRD-POSITIONS** | Position Ledger (`PositionsTable.tsx`) | A2 Ledger | Nav: Workspace 1 > Tab 2 | populated, empty, loading, error, stale | T1, T3 | Terinventarisasi |
| **WEB-TRD-SIGNALS** | Signals & Triggers (`SignalsTriggersPanel.tsx`) | A3 Queue | Nav: Workspace 1 > Tab 3 | live, empty, stale, expired-grouped | T2 | Terinventarisasi |
| **WEB-TRD-MARKET** | Market Data Terminal (`MarketDataPanel.tsx`) | A7 Chart/A2 | Nav: Workspace 1 > Tab 4 | populated, loading, error, symbol-selected | — | Terinventarisasi |
| **WEB-INT-GRAPH** | Pipeline DAG Visualizer (`GraphVisualizerPanel.tsx`) | A7 Chart/A8 | Nav: Workspace 2 > Tab 1 (`Key 2`) | idle, running-cycle, completed, node-selected | T5 | Terinventarisasi |
| **WEB-INT-DEBATES** | Debate Arbitration (`DebateOutcomesPanel.tsx`) | A4 Reading | Nav: Workspace 2 > Tab 2 | populated, empty, round-expanded | T5 | Terinventarisasi |
| **WEB-INT-ANALYSIS** | Market Analysis Grid (`AnalysisGrid.tsx`) | A4 Reading/A7 | Nav: Workspace 2 > Tab 3 | populated, empty, loading, timeframe-selected | — | Terinventarisasi |
| **WEB-INT-BRIEF** | Macro Intelligence Brief (`BriefTab`) | A4 Reading | Nav: Workspace 2 > Tab 4 | populated, empty | T5 | Terinventarisasi |
| **WEB-INT-MEMORY** | Memory Vault (`MemoryBrowserPanel.tsx`) | A4 Reading/A6 | Nav: Workspace 2 > Tab 5 | populated, empty, layer-filtered | — | Terinventarisasi |
| **WEB-INT-SKILLS** | Crystallized Skills (`SkillManagerPanel.tsx`) | A4 Reading/A2 | Nav: Workspace 2 > Tab 6 | populated, empty, skill-detail | — | Terinventarisasi |
| **WEB-INT-BENCHMARK** | Model Benchmark Lab (`BenchmarkPanel.tsx`) | A7 Chart/A2 | Nav: Workspace 2 > Tab 7 | populated, empty, loading, filter-active | — | Terinventarisasi |
| **WEB-LED-PERFORMANCE** | P&L Performance (`PerformancePanel.tsx`) | A7 Chart/A2 | Nav: Workspace 3 > Tab 1 (`Key 3`) | populated, empty, loading, period-filtered | T1 | Terinventarisasi |
| **WEB-LED-EDGE** | Edge & Expectancy (`EdgeMetricsPanel.tsx`) | A7 Chart/A1 | Nav: Workspace 3 > Tab 2 | populated, empty, loading | T1 | Terinventarisasi |
| **WEB-LED-RISK** | Risk Fortress (`RiskPanel.tsx`) | A8 Health/A6 | Nav: Workspace 3 > Tab 3 | normal, warning, breached, stale | T1, T5 | Terinventarisasi |
| **WEB-LED-TOKENS** | LLM Token Audit (`TokenAuditPanel.tsx`) | A2 Ledger/A7 | Nav: Workspace 3 > Tab 4 | populated, empty, loading, range-selected | — | Terinventarisasi |
| **WEB-LED-BACKTEST** | Historical Backtest (`BacktestPanel.tsx`) | A7 Chart/A6 | Nav: Workspace 3 > Tab 5 | idle, running, completed, error | — | Terinventarisasi |
| **WEB-TEL-CHAT** | Desk Chat REPL (`AgentChatPanel.tsx`) | A5 Console | Nav: Workspace 4 > Tab 1 (`Key 4`) | idle, streaming, error, approval-pending | — | Terinventarisasi |
| **WEB-TEL-TERMINAL** | Terminal PTY Shell (`TerminalPanel.tsx`) | A5 Console | Nav: Workspace 4 > Tab 2 | connected, disconnected, resized | — | Terinventarisasi |
| **WEB-TEL-SESSIONS** | Session History (`SessionBrowserPanel.tsx`) | A2 Ledger/A4 | Nav: Workspace 4 > Tab 3 | populated, empty, session-selected | — | Terinventarisasi |
| **WEB-TEL-OBSERVABILITY**| Dispatch Audit Log (`ObservabilityPanel.tsx`) | A3 Feed | Nav: Workspace 4 > Tab 4 | live-stream, paused, filtered-empty | T5 | Terinventarisasi |
| **WEB-SYS-CONFIG** | Configuration Settings (`ConfigEditorPanel.tsx`) | A6 Settings | Nav: Workspace 5 > Tab 1 (`Key 5`) | pristine, dirty, saving, invalid | — | Terinventarisasi |
| **WEB-SYS-PLUGINS** | Plugin Marketplace (`PluginManagerPanel.tsx`) | A2 Ledger/A6 | Nav: Workspace 5 > Tab 2 | populated, empty, installing, error | — | Terinventarisasi |
| **WEB-SYS-DIAGNOSTICS** | Host Diagnostics (`SystemPanel.tsx`) | A8 Health | Nav: Workspace 5 > Tab 3 | healthy, degraded, down | T5 | Terinventarisasi |
| **WEB-OVL-BOOT** | CRT Boot Sequence (`BootSequence.tsx`) | A9 Overlay | Initial App Mount | running, completed, skipped | — | Terinventarisasi |
| **WEB-OVL-PALETTE** | Command Palette (`CommandPalette.tsx`) | A9 Overlay | `Cmd+K` / `Ctrl+K` | open, query-typed, empty-results | — | Terinventarisasi |
| **WEB-OVL-ERROR** | Error Alert Window (`App.tsx`) | A9 Overlay | Global Error State | visible, dismissed | — | Terinventarisasi |
| **WEB-OVL-WEEKEND** | Weekend Gap Warning (`WeekendGapBanner.tsx`) | A9 Overlay | Active Friday UTC | visible, closed | T1 | Terinventarisasi |
| **WEB-DRW-MOBILE-NAV** | Mobile Drawer (`MobileNavDrawer.tsx`) | A9 Overlay | Hamburger click `<1024px` | open, closed, tab-selected | — | Terinventarisasi |
| **WEB-DRW-MANUAL-ORDER** | Manual Order Drawer (`ManualOrderDrawer.tsx`) | A9 Overlay/A6 | Tombol "Manual Order" | open, validating, submitting, error | T3 | Terinventarisasi |
| **WEB-DLG-DOSSIER** | Trade Decision Dossier (`DecisionDossierModal.tsx`) | A9 Overlay/A4 | Klik sinyal / posisi | open, loaded, error | T2 | Terinventarisasi |
| **WEB-DLG-CONFIG-DIFF** | Config Diff Viewer (`ConfigDiffModal.tsx`) | A9 Overlay | Tombol "Preview Diff" di Config | open, diff-shown, applied | — | Terinventarisasi |
| **WEB-DLG-APPROVAL** | Human Action Approval (`ApprovalModal.tsx`) | A9 Overlay | Pending sensitive execution | open, approved, rejected | — | Terinventarisasi |
| **WEB-DLG-CONFIRM** | Action Confirmation (`ConfirmModal.tsx`) | A9 Overlay | Mutasi destruktif / Kill | open, confirmed, cancelled | T4 | Terinventarisasi |
| **WEB-DLG-SHORTCUTS** | Keyboard Shortcuts (`KeyboardShortcutsPanel.tsx`)| A9 Overlay | Shortcut `?` | open, closed | — | Terinventarisasi |
| **TUI-DASH-OVERVIEW** | TUI Overview (`cli/tui.py`) | A1 Monitor | Command: `python -m cli.main tui` | populated, empty, stale | T1 | Terinventarisasi |
| **TUI-DASH-TREE** | TUI Analysis Tree (`cli/analysis_tree.py`) | A7 Chart/A8 | TUI Tab `Tree` | running-cycle, completed | T5 | Terinventarisasi |
| **TUI-DASH-PERF** | TUI Performance (`cli/tui.py`) | A7 Chart/A2 | TUI Tab `Perf` | populated, empty | T1 | Terinventarisasi |
| **TUI-DASH-SIGNALS** | TUI Candidate Signals (`cli/tui.py`) | A3 Queue | TUI Tab `Signals` | live, empty | T2 | Terinventarisasi |
| **TUI-DASH-RISK** | TUI Risk & Drawdown (`cli/tui.py`) | A8 Health/A1 | TUI Tab `Risk` | normal, warning, breached | T1, T5 | Terinventarisasi |
| **TUI-DASH-CHAT** | TUI Inline Chat (`cli/tui.py`) | A5 Console | TUI Tab `Chat` | idle, input-active, response | — | Terinventarisasi |
| **TUI-DASH-KILLMODAL** | TUI Kill Modal (`KillConfirmModalScreen`) | A9 Overlay | Tombol `k` di TUI | open, confirmed, cancelled | T4 | Terinventarisasi |
| **TUI-CHAT-STANDALONE** | TUI Standalone Chat (`cli/tui_chat.py`) | A5 Console | Command: `python -m cli.main chat`| idle, streaming, error | — | Terinventarisasi |
| **TUI-WIZARD-SETUP** | Interactive Setup Wizard (`cli/setup_wizard.py`) | A6 Settings | Command: `python -m cli.main setup`| interactive, validating, done | — | Terinventarisasi |
| **TUI-DOCTOR** | Host Health Diagnostics (`cli/doctor.py`) | A8 Health | Command: `python -m cli.main doctor`| checking, passed, failed | T5 | Terinventarisasi |
| **TUI-ONBOARDING** | Trader Onboarding (`cli/onboarding_trader.py`) | A6 Settings | Command: `python -m cli.main setup`| interactive, saving, complete | — | Terinventarisasi |
