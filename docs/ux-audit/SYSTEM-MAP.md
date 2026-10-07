# System Map: Monika Workstation UI/UX

> **Status:** Baselined & Verified  
> **Target:** Algorithmic Trading Desk Operator Console (Web Dashboard + Textual TUI)  
> **Aesthetic Boundary:** 1990s Vintage OS Workstation (Locked Dual-Mode: Taupe/Cream ⇄ Obsidian/Parchment)

---

## 1. Operator Persona
- **Role:** Quantitative Trading Desk Operator & Risk Officer.
- **Mental Mandate:** *"Am I safe? What needs me now? What is my exposure?"*
- **Operating Context:** Fast-paced multi-asset monitoring (Forex, Commodities, Indices on MT5), managing algorithmic LangGraph multi-agent execution, validating trade theses, intervening during market anomalies or macro news shocks.
- **Cognitive Requirement:** Zero cognitive ambiguity; sub-3 second situational assessment; absolute separation of probabilistic reasoning and deterministic execution; uncompromising trust in numbers.

---

## 2. The Five Critical Tasks

| # | Task | Objective & Latency Budget | Primary Surface |
|---|---|---|---|
| **T1** | **Assess State** | Verify engine state, broker connection, operational mode (`PAPER` vs `LIVE`), daily P&L, drawdown vs limit, and net exposure in **≤ 3 seconds with 0 clicks**. | Header Taskbar + Cockpit Bar |
| **T2** | **Respond to Signal** | Inspect active trading proposal, check thesis freshness and confidence, open decision dossier, and execute or dismiss within **≤ 15 seconds**. | Overview › Latest Dispatches + Dossier Modal |
| **T3** | **Manual Order** | Execute manual market/limit order with pre-trade lot sizing, SL/TP bounds, and RiskGate safety clearance via keyboard and mouse in **≤ 10 seconds**. | Manual Order Drawer (`⚡ NEW ORDER`) |
| **T4** | **Halt Everything** | Trigger global emergency kill switch / pause from any workspace, instantly liquidating or freezing positions, verified by high-contrast feedback. | Global Kill Switch (`[⏻ HALT]` / `F9` / `Ctrl+Shift+K`) |
| **T5** | **Diagnose Silence** | Rapidly answer *"Why are there no trades?"* by identifying active gate blocks (RiskGate, news blackout, spread filter, stale quotes, or LLM errors) in **≤ 2 navigations**. | Telegraph Log + Risk Circuit Breakers (`[SYS]` / `[LED]`) |

---

## 3. Surface Inventory

### 3.1 Web Dashboard (React 19 + TypeScript + Vite)
- **Host Viewport Targets:** 1920×1080 (Primary Workstation), 1440×900, 1280×720, 1024×768 (Tablet/Compact), 768×1024, 390×844 (Mobile Drawer).
- **Global Shell:** `Header.tsx` (Top Taskbar), `Sidebar.tsx` (5 Folders Navigator), `BreadcrumbBar.tsx`, `TickerTape.tsx`, `GlobalStatusBar.tsx` (Footer), `CommandPalette.tsx` (`Cmd+K`).
- **5 Canonical Workspaces (`24 Sub-Tabs`):**
  1. `[TRD] Trading Desk (Key: 1)`: `overview` (Default Cockpit + Ledger + Dispatches + Log), `positions` (Full Table), `signals` (Rule Triggers), `market` (Live Quotes & Charts), `terminal` (PTY Bridge).
  2. `[INT] Intelligence Room (Key: 2)`: `graph` (LangGraph DAG Visualizer), `debates` (Bull vs Bear), `brief` (Macro Markdown), `analysis` (Factor Grid), `skills` (Skill Manager), `memory` (Cognitive Memory Store).
  3. `[LED] Ledger & Risk (Key: 3)`: `performance` (Equity & Win Rate), `edge` (Expectancy & R:R), `risk` (RiskGate Matrix), `tokens` (LLM Token Audit), `backtest` (Backtest Engine), `benchmark` (Model Quadrant).
  4. `[TEL] Telegraph & Chat (Key: 4)`: `chat` (Agent REPL), `sessions` (Session Browser), `observability` (Telemetry & Traces).
  5. `[SYS] System Station (Key: 5)`: `config` (Settings.yaml Editor), `system` (Host Doctor & Health), `plugins` (Plugin Manager).

### 3.2 Terminal UI (Python 3.11+ Textual)
- **Target Dimensions:** 80×24 (Constrained ANSI), 120×40 (Standard Terminal), 200×50 (Ultra-Wide).
- **Color Depth Tiers:** Truecolor (24-bit RGB), 256-color, 16-color ANSI, `NO_COLOR` (Monochrome Accessible).
- **Entry Point:** `trading-agent/cli/tui.py` (`python -m cli.main tui`).
- **Screens & Tabs:** `Overview` (Positions DataTable + Telegraph RichLog), `Analysis` (AnalysisCycleTree + Arbitration Log), `Signals` (Real-Time Signals DataTable), `Risk` (RiskGate Breakers DataTable), `Chat` (Dual-Queue REPL), `Help` (`F1`).

---

## 4. Technology Stack & Directory Map

```
D:\Monika\
├── trading-agent/
│   ├── cli/
│   │   ├── tui.py                     # Textual Terminal UI Entrypoint & App Structure
│   │   ├── theme.py                   # TUI ANSI/RGB Theme Engine (retro_vintage, daylight)
│   │   ├── analysis_tree.py           # LangGraph Cycle Tree Widget
│   │   └── busy_input.py              # Dual-queue busy buffer (steer vs follow-up)
│   └── logging_observability/dashboard/
│       ├── routes/                    # FastAPI Backend REST & WebSocket Handlers
│       └── frontend/                  # React 19 SPA
│           ├── src/
│           │   ├── theme/
│           │   │   └── tokens.ts      # Canonical Design Tokens Dictionary
│           │   ├── index.css          # CSS Variables (:root Light/Dark), Resets, Vintage Classes
│           │   ├── App.tsx            # Main Shell, Workspace Routing, Global Hotkeys
│           │   ├── store/
│           │   │   └── dashboardStore.ts # Central Zustand State Management
│           │   ├── lib/
│           │   │   ├── api.ts         # REST API Client (Axios)
│           │   │   ├── formatters.ts  # Precision Numerical & Date Formatters
│           │   │   └── soundEffects.ts# Web Audio API Synthesizer
│           │   ├── components/
│           │   │   ├── layout/        # Header, Sidebar, GlobalStatusBar, BreadcrumbBar
│           │   │   ├── panels/        # CockpitBar, PositionsTable, ActivityFeed, AnalysisGrid
│           │   │   └── ui/            # WindowFrame, TypewriterButton, SegmentedProgressBar, etc.
```
