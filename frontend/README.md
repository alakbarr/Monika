# Monika Web Dashboard — React 19 + TypeScript + Vite

> **Official Web Cockpit & Telemetry Interface for Monika Algorithmic Trading Framework**

The Monika Web Dashboard is an institutional-grade, high-density web cockpit designed for monitoring automated market analysis, real-time paper and live positions, multi-agent adversarial debates, risk bounds, model benchmarks, and execution telemetry in MetaTrader 5.

---

## 1. Architectural Highlights

- **Framework**: Built with **React 19** and **Vite 6** utilizing TypeScript for strict type safety.
- **Visual Design System**: Implements the **Swiss Liquid Glass & Editorial Precision** specification ([`DESIGN.md`](../DESIGN.md)) with dual-mode support (Alabaster Light and Graphite Obsidian Dark).
- **Chart Engines**:
  - [TradingView Lightweight Charts v5](https://tradingview.github.io/lightweight-charts/): Multi-timeframe candlestick rendering, SMC liquidity overlays, Fair Value Gaps (FVG), and order blocks.
  - [Recharts v2](https://recharts.org/): Interactive portfolio equity monument, drawdown curves, token expenditure audits, and factor heatmaps.
- **Embedded Terminal**: [xterm.js v6](https://xtermjs.org/) integration with PTY WebSocket bridge for headless terminal access and interactive shell sessions.
- **State Management**: [Zustand](https://github.com/pmndrs/zustand) stores with real-time WebSocket subscriptions to `/ws/telemetry` and `/ws/agent-chat`.
- **OpenAPI Type Sync**: Automatically synchronized types generated from FastAPI backend schemas via `scripts/generate_openapi_types.py`.

---

## 2. Spatial Chapters & Tab Directory

The dashboard organizes 23 analytical panels and 5 modal overlays into 5 top-level editorial chapters accessible via the bottom floating dock bar or keyboard shortcuts (`1`–`5`):

### Chapter I: Capital (Portofolio & Eksekusi)
- **`overview` (01_trading_desk_overview)**: 64px Sculptural Equity Monument, 6-cell telemetry ribbon, live interactive equity curve, and recent execution events.
- **`positions` (02_position_ledger)**: Active and historical positions ledger, entry price, stop-loss, take-profit, unrealized PnL, and manual order drawer (`+ NEW ORDER`).
- **`signals` (03_signals_triggers)**: Active MT5 signals, pending conditional price triggers, and quantitative edge candidate matrix.
- **`market` (04_market_data)**: Streaming tick quotes, multi-timeframe OHLCV bars, Level-2 Depth of Market (DOM), and spread monitors.

### Chapter II: Journal (Inteligensi & Deliberasi)
- **`graph` (05_pipeline_dag_flow)**: Interactive LangGraph StateMachine DAG visualizer with execution node waterfalls and latency telemetry.
- **`debates` (06_debate_arbitration)**: Multi-turn Bull vs. Bear dialectical debate transcripts, judicial confidence scores, and arbitration verdicts.
- **`analysis` (07_market_analysis)**: Stage 2 asset synthesis reports, technical indicators, and coordinate snapping geometry.
- **`brief` (08_macro_intel_brief)**: Stage 1 macroeconomic narrative brief, central bank policy expectations (FedWatch, ECB, BOJ), and calendar releases.
- **`memory` (09_memory_vault)**: 4-layer cognitive memory browser (Soul, Macro Reality, Chronicle, Post-Trade Reflections).
- **`skills` (10_crystallized_skills)**: Repository of autonomously crystallized trading skills and playbook rules.

### Chapter III: Risk (Benteng Mekanikal & Limit)
- **`performance` (12_pnl_performance)**: Equity curve progression, Sharpe ratio, Sortino ratio, max drawdown, and profit factor.
- **`edge` (13_edge_expectancy)**: Win-rate expectancy, payoff ratio, and rolling edge degradation tracker (`7d`, `14d`, `30d`).
- **`risk` (14_risk_limits)**: 30+ deterministic RiskGate checks, daily/weekly drawdown meters, correlation heat, and 50-trade graduation gate.

### Chapter IV: Lab (Riset & Model Benchmark)
- **`benchmark` (11_model_benchmark_lab)**: Multi-model tournament leaderboard (Alpha Arena), reasoning latency, schema compliance, and Elo ratings.
- **`tokens` (15_token_audit)**: Granular token expenditure tracking, prompt cache hit rates, cost per model, and multi-horizon budget governor.
- **`backtest` (16_historical_backtest)**: Point-in-time historical backtest engine with zero-lookahead candle stepping and Monte Carlo equity simulations.

### Chapter V: Atelier (Konfigurasi & Sistem)
- **`chat` (17_desk_chat_repl)**: Interactive conversational REPL with agent assistant, prompt tool calling, and market thesis queries.
- **`terminal` (18_terminal_pty)**: Full xterm.js PTY console terminal session.
- **`sessions` (19_session_history)**: Historical chat and deliberation session archive.
- **`observability` (20_dispatch_audit_log)**: OpenTelemetry trace waterfall, execution logs, and delivery ledger.
- **`config` (21_config_settings)**: Live YAML settings editor with atomic validation, diff inspection, and hot-reload.
- **`plugins` (22_plugin_marketplace)**: Universal Plugin Engine manager, discovery, and lifecycle controller.
- **`system` (23_host_diagnostics)**: System doctor health status, CPU/RAM utilization, database connections, and broker latency.

### Overlays & Modals
- **Command Palette** (`Ctrl+K` / `Cmd+K`): Instant search and navigation across all tabs, assets, and commands.
- **Keyboard Shortcuts** (`?`): Cheat sheet of universal navigation hotkeys.
- **Emergency Halt Modal**: Instant confirmation modal to halt automated trading or trigger liquidation.
- **Manual Order Drawer**: Direct lot-sized manual order creation passing through RiskGate.
- **CRT Boot Sequence**: Optional retro CRT startup overlay visualizer.

---

## 3. Development & Build

### Prerequisites
- Node.js 18 LTS or newer
- npm 9+

### Setup
```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start development server (with HMR)
npm run dev

# Lint codebase with Oxlint
npm run lint

# Build production bundle with TypeScript verification
npm run build

# Preview production build locally on port 4173
npm run preview
```

---

## 4. Automated Screenshot & Visual Regression Testing

Monika includes Playwright automation scripts to capture high-resolution screenshots of all 23 tabs and 5 overlays in both Light and Dark modes:

```bash
# 1. Build and preview frontend
npm run build
npm run preview &

# 2. Run automated Playwright screenshot capture (from repo root)
node scripts/capture_dashboard_screenshots.js
```
The captured screenshots are saved directly to `docs/images/dashboard/`.
