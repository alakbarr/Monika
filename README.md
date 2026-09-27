# Monika — Autonomous Multi-Agent Trading Harness & Execution Engine for MetaTrader 5

<p align="center">
  <img src="docs/images/01_trading_desk_overview.png" alt="Monika Trading Desk Overview" width="100%" style="border-radius: 8px; box-shadow: 0 4px 25px rgba(0,0,0,0.4);" />
</p>

<p align="center">
  <strong>An institutional-grade, open-source multi-agent research harness and automated execution substrate for MetaTrader 5 (MT5).</strong><br />
  <em>Unifying macroeconomic synthesis, Smart Money Concepts (SMC) order flow, dialectical Bull/Bear adversarial debate, and an unbypassable mechanical risk fortress.</em>
</p>

<p align="center">
  <a href="https://github.com/alakbarr/Monika/actions/workflows/ci.yml"><img src="https://github.com/alakbarr/Monika/actions/workflows/ci.yml/badge.svg" alt="CI Pipeline" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?logo=python&logoColor=white" alt="Python 3.11+" /></a>
  <a href="https://langchain-ai.github.io/langgraph/"><img src="https://img.shields.io/badge/Orchestration-LangGraph-1C75BC.svg?logo=langchain&logoColor=white" alt="LangGraph" /></a>
  <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/Backend-FastAPI-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/Frontend-React%2019%20%2B%20Vite-61DAFB.svg?logo=react&logoColor=black" alt="React 19" /></a>
  <a href="https://www.postgresql.org"><img src="https://img.shields.io/badge/Database-PostgreSQL%2016%2B-336791.svg?logo=postgresql&logoColor=white" alt="PostgreSQL 16+" /></a>
  <a href="https://www.metatrader5.com"><img src="https://img.shields.io/badge/Execution-MetaTrader%205-red.svg" alt="MetaTrader 5" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License" /></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/Code%20Style-Ruff-black.svg" alt="Ruff" /></a>
</p>

---

## 📌 Executive Summary & Project Status

> [!NOTE]
> **Monika is an active quantitative research project and experimental trading harness.**  
> It represents an engineering exploration into how generative Large Language Models (LLMs), dialectical multi-agent debates, and macroeconomic knowledge graphs can be safely integrated into automated trading workflows without ever surrendering risk control or capital authority to non-deterministic models.
>
> **The codebase is shared openly in the spirit of collaborative systems engineering.** We make no claims of turnkey institutional perfection, push-button riches, or guaranteed alpha. What we provide is a rigorous, fail-closed software architecture where probabilistic AI models can hypothesize while deterministic mathematical fortresses enforce immutable capital protection.
>
> 💡 *We warmly welcome feedback, bug reports, and architectural contributions from quantitative developers, systematic traders, AI researchers, and hobbyist engineers alike!*

---

## 🧭 Table of Contents

- [1. What is Monika? (The "Agent Harness" Concept)](#-1-what-is-monika-the-agent-harness-concept)
  - [The Core Dilemma: Bots vs. Naive Generative AI](#the-core-dilemma-bots-vs-naive-generative-ai)
  - [The Monika Solution: Fail-Closed Architecture](#the-monika-solution-fail-closed-architecture)
  - [The Five Non-Negotiable Core Principles](#the-five-non-negotiable-core-principles)
- [2. Who is Monika For? (Target Personas)](#-2-who-is-monika-for-target-personas)
- [3. What Can You Get from Monika? (Tangible Benefits & Features)](#-3-what-can-you-get-from-monika-tangible-benefits--features)
  - [Pillar I: Macroeconomic Intelligence & News Surprise Ingestion](#pillar-i-macroeconomic-intelligence--news-surprise-ingestion)
  - [Pillar II: Microstructure, Order Flow & SMC Engine](#pillar-ii-microstructure-order-flow--smc-engine)
  - [Pillar III: Dialectical Multi-Agent Adversarial Debate](#pillar-iii-dialectical-multi-agent-adversarial-debate)
  - [Pillar IV: The Unbypassable 10-Layer RiskGate Fortress](#pillar-iv-the-unbypassable-10-layer-riskgate-fortress)
  - [Pillar V: Hybrid Quant Alpha & Centralized Signal Arbitration](#pillar-v-hybrid-quant-alpha--centralized-signal-arbitration)
  - [Pillar VI: Dual-Bridge Execution & MQL5 Dead-Man's Switch](#pillar-vi-dual-bridge-execution--mql5-dead-mans-switch)
  - [Pillar VII: Omnichannel Supervision, Memory & Continuous Learning](#pillar-vii-omnichannel-supervision-memory--continuous-learning)
- [4. Visual Tour & Observability Suite](#-4-visual-tour--observability-suite)
  - [Web Dashboard (React 19 + Vite)](#1-web-dashboard-react-19--vite)
  - [Terminal User Interface (TUI)](#2-terminal-user-interface-tui)
- [5. System Architecture & Workflow Pipeline](#-5-system-architecture--workflow-pipeline)
  - [End-to-End Decision Flow](#end-to-end-decision-flow)
  - [Concurrent Autonomous Schedulers](#the-18-concurrent-background-schedulers)
- [6. Supported Asset Universe & LLM Ecosystem](#-6-supported-asset-universe--llm-ecosystem)
- [7. Practical Getting Started Guide](#-7-practical-getting-started-guide)
  - [Prerequisites & System Requirements](#1-prerequisites--system-requirements)
  - [Installation from Source](#2-installation-from-source)
  - [Database Setup & Alembic Migrations](#3-database-setup--alembic-migrations)
  - [Environment Configuration (.env)](#4-environment-configuration-env)
  - [Pre-Flight Health Verification (Doctor)](#5-pre-flight-health-verification-doctor)
  - [Running Monika](#6-running-monika)
- [8. CLI & Telegram Command Reference](#-8-cli--telegram-command-reference)
- [9. Testing, Backtesting & Evaluation Suite](#-9-testing-backtesting--evaluation-suite)
- [10. Frequently Asked Questions (FAQ)](#-10-frequently-asked-questions-faq)
- [11. Repository Structure](#-11-repository-structure)
- [12. Contributing, Security & Community](#-12-contributing-security--community)
- [13. Financial & Research Disclaimer](#-13-financial--research-disclaimer)

---

## 💡 1. What is Monika? (The "Agent Harness" Concept)

### The Core Dilemma: Bots vs. Naive Generative AI

Automated trading has historically been split between two flawed paradigms:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ TRADITIONAL BOTS (EAs / Scripts)           NAIVE GENERATIVE AI CHATBOTS                │
├─────────────────────────────────────────┬──────────────────────────────────────────────┤
│ ❌ Rigid & brittle rules (MA crosses)   │ ❌ Prone to severe mathematical hallucinations│
│ ❌ Completely blind to macroeconomic    │ ❌ Fabricates invalid stops, targets, or lots│
│    context, speeches, and news shocks   │ ❌ Suffers from sycophancy & confirmation bias│
│ ❌ Whipsawed during regime transitions  │ ❌ High latency and catastrophic lack of      │
│    and high-impact event volatility     │    hard capital boundaries                   │
└─────────────────────────────────────────┴──────────────────────────────────────────────┘
```

### The Monika Solution: Fail-Closed Architecture

Monika bridges this divide by treating generative AI not as an unconstrained executioner, but as a **contextual perception and analytical drafting organ** confined inside an **Agent Harness**:

> ### 🛡️ **"AI Proposes, Mechanical Fortress Disposes"**
>
> In Monika, an LLM possesses **zero authority** to touch broker order books. The AI can only generate structured hypotheses (`SubmitAssetAnalysisSchema`). Before any trade can materialize as a broker ticket, it must clear an unbypassable, deterministic mathematical fortress (`RiskGate`) that calculates exact position sizing, inspects portfolio drawdown budgets, and cross-checks high-impact news windows.
>
> If there is any discrepancy, missing data feed, or risk limit breach, the system deterministically defaults to **`NO TRADE`** or **`WAIT`**.

```mermaid
flowchart LR
    A[Unstructured Feeds & News] --> B[Perception Ingestion]
    C[Verified Tick/Bar Data] --> D[Deterministic SMC & Math]
    B --> E[LangGraph Multi-Agent Debate]
    D --> E
    E --> F[Structured Trade Proposal]
    F --> G{Mechanical RiskGate Fortress}
    G -- Passed --> H[Deterministic Volatility Sizer]
    G -- Failed --> I[Rejected & Audited]
    H --> J[MetaTrader 5 Native IPC]
    J --> K[MQL5 Dead-Man EA Watchdog]
```

### The Five Non-Negotiable Core Principles

1. **Fail-Closed Execution:** Any unhandled exception, missing data source, API timeout, or ambiguity triggers an immediate, safe abort to `WAIT` / `NO TRADE`. Capital survival always trumps trade frequency.
2. **Strict Separation of Concerns:** LLMs handle qualitative synthesis, sentiment contextualization, and adversarial argument; deterministic Python modules handle all floating-point math, indicator extraction, ATR calculations, and lot sizing.
3. **Capital Preservation Over Alpha:** Cash is a valid position. When markets are choppy, spread-widened, or heading into tier-1 central bank decisions, defensive patience is explicitly rewarded.
4. **Absolute Auditability:** Every single prompt payload, reasoning step, debate argument, judicial confidence score, token dollar cost, and broker order ticket is permanently persisted to PostgreSQL.
5. **Dual-Layer Execution Resiliency:** A native Python IPC bridge handles order routing, while an independent MQL5 Expert Advisor (`AIAgent_EA.mq5`) monitors a continuous heartbeat file inside the MT5 terminal to act as an automated dead-man's switch.

---

## 👥 2. Who is Monika For? (Target Personas)

| Target Persona | Key Pain Points Addressed | How Monika Solves Them |
| :--- | :--- | :--- |
| **Quantitative Developers & Quants** | Disjointed tech stacks, lack of macro awareness in quant algorithms, difficulty integrating modern multi-modal LLM APIs with MT5. | Complete async Python framework, modular indicators (SMC, FVG, L2 DOM, TimesFM), typed event bus, Kahn's topological plugin engine, and native MT5 IPC. |
| **Systematic & Algorithmic Traders** | Getting stopped out during news spread spikes, emotional overtrading, catastrophic EA crashes during VPS network dropouts. | 10-layer deterministic `RiskGate`, mandatory news blackout windows, dynamic volatility-adjusted sizing, and an MQL5 dead-man's switch. |
| **AI & NLP Researchers** | Hallucinations in financial reasoning, single-prompt confirmation bias, excessive LLM token costs in multi-turn dialogues. | Stateful LangGraph workflow, dialectical Bull/Bear adversarial debate, impartial Investment Judge calibration, and KV prompt caching optimizations (~70–80% hit rates). |
| **Self-Hosted Operators & Prop Traders** | Needing 24/7 autonomous monitoring with remote human-in-the-loop (HITL) kill switches and transparent observability. | Comprehensive React 19 Web Dashboard, terminal TUI, interactive Telegram bot with one-tap emergency `/kill`, and hard daily drawdown circuit breakers tailored for prop firm rules. |

---

## 💎 3. What Can You Get from Monika? (Tangible Benefits & Features)

Monika is structured into **seven core operational pillars**:

### Pillar I: Macroeconomic Intelligence & News Surprise Ingestion
- **Automated Macro Feeds:** Continuous background ingestion of central bank announcements (Federal Reserve, ECB, BoE, BoJ), US Treasury yield curves via the FRED API, and thematic economic data.
- **Active Calendar Poller:** Monitors upcoming tier-1 releases (CPI, Non-Farm Payrolls, FOMC, GDP). As a scheduled release approaches, polling frequency accelerates to capture reported figures within seconds.
- **15-Minute News Settlement & Economic Surprise:** Imposes a mandatory trading blackout $\pm 15$ minutes around high-impact events to avoid catastrophic spread widening. After 15 minutes, calculates the *economic surprise index* ($\text{actual} - \text{forecast}$) to update currency narrative biases.
- **Thematic Currency Digests:** Scrapes global financial news (Reuters, Bloomberg, FXStreet, CoinDesk) and clusters headlines into currency-specific briefs, filtering out noise.

### Pillar II: Microstructure, Order Flow & SMC Engine
- **Smart Money Concepts (SMC):** Deterministic extraction of market milestones:
  - Swing Highs and Lows (Fractal pivots).
  - Break of Structure (BOS) and Change of Character (CHoCH).
  - Fair Value Gaps (FVG) tracked across lifecycles: unfilled, partially filled, and mitigated.
  - Liquidity Pools (buy-side and sell-side liquidity clusters).
- **Order Flow & Microstructure Metrics:**
  - Real Level-2 Depth of Market (DOM) analysis with Order Book Imbalance (OBI).
  - Cumulative Volume Delta (CVD) with automatic fallback to Lee-Ready synthetic tick rule.
  - Volume-Synchronized Probability of Toxicity (VPIN), Kyle's Lambda, and Amihud illiquidity metrics.
- **Deep Learning Forecasting (Google TimesFM 3.0):** Optional integration with Google's foundation time-series model to calculate forward-looking quantile volatility bands ($q_{0.1}$ to $q_{0.9}$) for adaptive intraday boundaries.

### Pillar III: Dialectical Multi-Agent Adversarial Debate
Rather than relying on a single prompt that suffers from confirmation bias, candidate trade setups undergo structured adversarial debate inside a LangGraph state machine:

```
             ┌─────────────────────────────────────────────────────────┐
             │                STAGE 2: TACTICAL SYNTHESIS              │
             └────────────────────────────┬────────────────────────────┘
                                          │
                  ┌───────────────────────┴───────────────────────┐
                  ▼                                               ▼
         ┌───────────────────┐                         ┌───────────────────┐
         │   Bull Analyst    │                         │   Bear Analyst    │
         │ (Upside Catalysts,│                         │(Downside Threats, │
         │  Support Defense) │                         │  Order Block Risk)│
         └─────────┬─────────┘                         └─────────┬─────────┘
                   │                                             │
                   └───────────────► ┌─────────┐ ◄───────────────┘
                                     │ Debate  │  Delta Watermarks &
                                     │ Council │  (pass) Protocol
                                     └────┬────┘
                                          │
                                          ▼
                             ┌─────────────────────────┐
                             │    Investment Judge     │
                             │ Dynamic Regime Weights  │
                             │   (Trending/Ranging/    │
                             │    Volatile via VIX)    │
                             └────────────┬────────────┘
                                          ▼
                             Calibrated Confidence Score
                                     [0.0 - 1.0]
```

- **Bull Analyst:** Defends long arguments or stress-tests short proposals, citing order book absorption, CVD divergences, and support zones.
- **Bear Analyst:** Highlights overhead supply barriers, unmitigated order blocks, liquidity traps, and adverse macro head-winds.
- **Token-Efficient Deliberation:** Implements **Delta Watermarks** (agents only receive new arguments since their last turn) and a **`(pass)` protocol** (agents pass when their thesis is satisfied), preventing $O(N^2)$ quadratic token inflation.
- **Impartial Investment Judge:** Evaluates arguments against a dynamic `REGIME_WEIGHT_MATRIX` weighted by current market regime and VIX levels, producing a calibrated confidence score ($0.0 - 1.0$).
- **Deterministic Coordinate Snapping:** Automatically snaps any slightly drifting LLM price coordinates to validated swing levels or FVG bounds.

### Pillar IV: The Unbypassable 10-Layer RiskGate Fortress
Every trade proposal must clear all 10 independent checks:

1. **System Operational Status Check:** Verifies trading is not globally paused or in maintenance mode.
2. **Positive Lot & Parameter Validity:** Validates non-zero lot calculations and correct SL/TP orientation.
3. **Daily Realized & Floating Drawdown Ceiling:** Hard limit (default max 4.0% daily / 6.0% weekly).
4. **Maximum Concurrent Open Positions:** Limits overall portfolio exposure (default max 5 positions).
5. **Single-Symbol Exposure Cap:** Prevents stacking multiple directional positions on the same pair.
6. **High-Impact News Proximity Filter:** Blocks new order entries within $\pm 15$ minutes of tier-1 events.
7. **Portfolio Heat & Cross-Asset Correlation:** Limits correlated currency exposure (e.g., EURUSD and GBPUSD simultaneously).
8. **Maximum Broker Spread Threshold:** Blocks execution during illiquid market rollovers or spread widening.
9. **Minimum Risk-to-Reward Ratio (RRR):** Enforces a strict mathematical edge (default minimum $1:1.3$ or $1:2.0$).
10. **Weekend Gap Risk Quarantine:** Automatically closes or suspends new trades late Friday UTC.

### Pillar V: Hybrid Quant Alpha & Centralized Signal Arbitration
- **Parallel Deterministic Quant Runners (`EdgeStrategyRunner`):** Runs quantitative algorithms concurrently with the LLM pipeline:
  - `btc_donchian_breakout`: Adaptive Donchian channel breakouts for Bitcoin.
  - `gap_fade`: Weekend and opening gap mean-reversion.
  - `liquidity_sweep_edge`: High-probability false breakout sweeps.
  - `tsm_momentum`: Multi-timeframe trend-following momentum.
  - `xau_trend_engine`: Specialized institutional trend model for Gold.
- **Centralized `SignalArbitrator`:** Reconciles signals from quantitative models and LLM debates:
  - *Concordant Agreement:* Both quant and LLM agree $\rightarrow$ confidence boost and risk multiplier applied.
  - *Conflict Suppression:* Quant and LLM clash $\rightarrow$ trade is defensively suppressed (`AVOID`).
  - *Defensive Override:* Elevated volatility or VIX forces defensive sizing or trade cancellation.

### Pillar VI: Dual-Bridge Execution & MQL5 Dead-Man's Switch
- **Native MetaTrader 5 Python IPC:** Sub-millisecond direct communication with the MT5 terminal on Windows hosts.
- **MQL5 EA Dead-Man's Switch (`AIAgent_EA.mq5`):** Running directly inside the MT5 terminal, this independent Expert Advisor continuously monitors a shared `heartbeat.txt` written by Monika every 20 seconds. If the Python process crashes, operating system locks up, or network fails (> 120 seconds stale), the EA automatically intervenes to protect open capital.
- **Mandatory Paper Trading Graduation Gate:** Default configuration strictly enforces paper trading (`paper_trading.enabled: true`). Live capital execution requires accumulating at least **50 validated paper trades** with a verified win rate $\ge 55\%$.

### Pillar VII: Omnichannel Supervision, Memory & Continuous Learning
- **4-Layer Cognitive Memory Architecture:**
  - *Layer 0 (Soul):* Immutable core trading philosophy and risk identities.
  - *Layer 1 (Macro Reality):* Verified geopolitical, central bank, and yield curve baselines.
  - *Layer 2 (Chronicle):* Ongoing timeline of macroeconomic regimes and shifts.
  - *Layer 3 (Episodic Reflection):* Post-trade reflections evaluating whether executed setups unfolded as expected, distilling lessons into persistent storage.
- **Omnichannel Gateway:** Multi-platform routing engine supporting Telegram, Discord, Slack, and the Agent Client Protocol (ACP).

---

## 🖥️ 4. Visual Tour & Observability Suite

> [!TIP]
> All telemetry readings, account balances, and win-rate statistics shown in the screenshots below represent paper-trading simulations and diagnostic verification sessions.

### 1. Web Dashboard (React 19 + Vite)

The web dashboard provides a control center for monitoring live agent cognition and execution telemetry.

#### Trading Desk Overview & Equity Growth
Real-time portfolio equity curves, open MT5 execution tickets, factor dispatch feeds, and daily profit/loss meters.

<p align="center">
  <img src="docs/images/01_trading_desk_overview.png" alt="Monika Trading Desk Overview" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

---

#### Market Intelligence & LangGraph Pipeline DAG
Interactive visualization of the LangGraph state machine. Inspect node execution latencies, input/output JSON schemas, and live transitions from Macro Stage 1 to Asset Synthesis Stage 2.

<p align="center">
  <img src="docs/images/04_market_intelligence_pipeline_dag.png" alt="LangGraph Pipeline DAG" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

---

#### Signals Matrix & Streaming Market Feed
Real-time tracking of pending conditional triggers (liquidity sweeps, zone retests), latency benchmarks, and active quote depth.

<p align="center">
  <img src="docs/images/02_trading_desk_signals.png" alt="Signals Matrix" width="49%" style="border-radius: 8px; border: 1px solid #334155;" />
  <img src="docs/images/03_trading_desk_market.png" alt="Streaming Market Data" width="49%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

---

#### Hard Risk Limits & Token Economics Audit
- **Left:** Analog-style VU gauges tracking daily drawdown budgets, portfolio heat, and circuit breaker health.
- **Right:** Granular tracking of LLM prompt/completion tokens, model provider routing, and prompt cache hit rates (~70–80% cost savings).

<p align="center">
  <img src="docs/images/06_ledger_risk_limits.png" alt="Hard Risk Limits" width="49%" style="border-radius: 8px; border: 1px solid #334155;" />
  <img src="docs/images/07_ledger_llm_token_audit.png" alt="Token Economics Audit" width="49%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

---

#### Telegraph HITL Desk & System Configuration
- **Left:** Human-In-The-Loop (HITL) interactive console allowing operators to converse with the agent, inspect trade rationales, and manually confirm or veto proposed orders.
- **Right:** Dynamic system configuration editor with hot-reloading support.

<p align="center">
  <img src="docs/images/08_telegraph_desk_console_chat.png" alt="Telegraph Console Chat" width="49%" style="border-radius: 8px; border: 1px solid #334155;" />
  <img src="docs/images/09_system_configuration.png" alt="System Configuration" width="49%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

---

### 2. Terminal User Interface (TUI)

For lightweight environments, headless servers, Linux VPS nodes, or remote SSH sessions:

<p align="center">
  <img src="docs/images/10_terminal_ui_tui.png" alt="Terminal UI (TUI)" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- Built with **Textual** and **Rich** for zero-dependency terminal rendering.
- Real-time ASCII sparkline equity trajectories and position tables.
- Keyboard-driven navigation (`Tab`, `1-4`, `q`) and integrated command-line controls.

---

## 🏗️ 5. System Architecture & Workflow Pipeline

### End-to-End Decision Flow

```mermaid
flowchart TD
    subgraph S1_Perception ["1. Ingestion & Preprocessing"]
        Ticks[MT5 Market Ticks & OHLCV Bars] --> DataHub[Data Hub]
        Macro[FRED API / Yield Curves] --> DataHub
        News[News RSS & Central Bank Feeds] --> DataHub
        DataHub --> SMC_Eng[SMC Engine: BOS, CHoCH, FVG, L2 DOM]
        DataHub --> TimesFM_Eng[Google TimesFM 3.0 Volatility Bounds]
    end

    subgraph S2_Cognition ["2. Cognitive Reasoning (LangGraph)"]
        DataHub --> S1_Macro[Stage 1: Macroeconomic Grounding Brief]
        SMC_Eng --> S2_Asset[Stage 2: Tactical Asset Synthesis]
        TimesFM_Eng --> S2_Asset
        S1_Macro --> S2_Asset
        S2_Asset --> BullAgent[Bull Specialist Persona]
        S2_Asset --> BearAgent[Bear Specialist Persona]
        BullAgent <--> AdversarialDebate[Dialectical Adversarial Debate]
        BearAgent <--> AdversarialDebate
        AdversarialDebate --> JudgeAgent[Investment Arbitration Judge]
        JudgeAgent --> Proposal[Structured Trade Proposal]
    end

    subgraph S3_Fortress ["3. Mechanical Risk Fortress"]
        Proposal --> RiskGate{Deterministic RiskGate<br/>10-Layer Checkpoint Filter}
        QuantRunner[EdgeStrategyRunner<br/>Quant Alphas] --> SignalArb[Centralized Signal Arbitrator]
        RiskGate -- Failed --> AuditReject[Rejected & Persisted to DB]
        RiskGate -- Passed --> Sizer[Deterministic Volatility Sizer]
        SignalArb --> Sizer
    end

    subgraph S4_Execution ["4. Execution & Watchdogs"]
        Sizer --> ExecService[Execution Service]
        ExecService --> MT5_IPC[Native MetaTrader 5 Python IPC]
        ExecService --> EA_Bridge[MQL5 EA Dead-Man Switch]
        MT5_IPC --> BrokerOrder[Broker Order Book]
        EA_Bridge --> BrokerOrder
    end

    subgraph S5_Observability ["5. Observability & Memory"]
        BrokerOrder --> Postgres[(PostgreSQL 16+ Database)]
        Postgres --> FastAPI_Svc[FastAPI Telemetry Backend]
        FastAPI_Svc --> WebUI[React 19 Web Dashboard]
        FastAPI_Svc --> TUI_Cli[Terminal UI - Textual]
        FastAPI_Svc --> TelegramDaemon[Telegram Bot & HITL]
        BrokerOrder --> MemoryReflect[Episodic Reflection & Learning]
    end
```

### The 18+ Concurrent Background Schedulers

Monika coordinates multiple asynchronous tasks orchestrated via Python's `asyncio` event loop:

| Task Component | Interval | Primary Responsibility |
| :--- | :--- | :--- |
| `GraphCycleScheduler` | Every 6–8 hrs | Executes the full LangGraph macro analysis and multi-asset debate cycle. |
| `NewsWatcher` | Every 5 min | Polls breaking news feeds and triggers rapid ad-hoc re-evaluations on tier-1 events. |
| `TriggerChecker` | Every 2 min | Checks pending conditional orders (price sweep confirmations, FVG retests). |
| `ActiveCalendarPoller` | Real-time | Accelerates polling around high-impact economic releases (CPI, NFP, FOMC). |
| `PostReleaseAnalyzer` | Post-event | Analyzes economic surprise indices after the mandatory 15-minute settlement window. |
| `PositionGuardian` | Every 5 min | Inspects open positions and closes them before high-impact news if configured. |
| `TrailingStopManager` | Every 30 sec | Dynamic trailing stop adjustments (breakeven locks, ATR ratchet). |
| `FlashCrashDetector` | Every 30 sec | Detects sudden price travel ($>5\times$ ATR in 30s) and trails stops to breakeven. |
| `EdgeStrategyRunner` | Continuous | Executes deterministic quant alpha models (Donchian, Gap Fade, Sweeps). |
| `HeartbeatManager` | Every 20 sec | Writes timestamps to `heartbeat.txt` for the MQL5 EA dead-man's switch. |
| `OrderReconciler` | Every 5 min | Resolves discrepancies between database records and live MT5 broker tickets. |
| `PositionExitReviewer` | Event-driven | Triggers post-exit reflections to extract empirical lessons into Layer 3 memory. |
| `PositionSupervisor` | Every 1 min | Monitors total margin utilization, portfolio heat, and aggregate leverage. |
| `MarketDataScheduler` | Continuous | Ingests live tick data, OHLCV bars, and DOM Level-2 book depth. |
| `MacroDataScheduler` | Periodic | Refreshes FRED yield curves, inflation indices, and central bank speeches. |
| `DigestSliceScheduler` | Hourly | Summarizes accumulated news headlines into clean thematic digests. |
| `TelegramBot` | Continuous | Long-polling Telegram interface for alerts, status, and HITL authorization. |
| `Dashboard API` | Daemon | High-performance FastAPI REST & WebSocket server powering the frontend. |

---

## 🌐 6. Supported Asset Universe & LLM Ecosystem

### Supported Asset Universe
Configured via `trading-agent/config/settings.yaml`, Monika natively supports:
- **Commodities:** `XAUUSD` (Spot Gold), `XTIUSD` (WTI Crude Oil), `XBRUSD` (Brent Crude Oil).
- **Major Forex:** `EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`.
- **Cryptocurrencies:** `BTCUSD` (Bitcoin).

### Multi-Provider LLM Routing Architecture (Decoupled Task-Role Design)

Monika separates analytical logic from specific AI models. **Zero model names are hardcoded into the codebase.** Every analytical module requests an abstract role (e.g. `get_client_for_task("stage1_fundamental")`), and the runtime dynamically resolves the model from `trading-agent/config/settings.yaml`.

This decoupled architecture gives you complete freedom to **experiment, benchmark, and hot-swap models** across any provider at any time without modifying a single line of Python code.

#### 1. Task Complexity Tiers
Analytical tasks are organized into four functional complexity tiers:

- **Tier 1: Macro & Deep Narrative Synthesis** (`stage1_fundamental`, `stage1_escalation`, `deep_research`)  
  *Characteristics:* High-context reasoning, synthesizing central bank policy shifts, yield curve trends, and multi-source global news. Best suited for high-reasoning, large-context foundation models.
- **Tier 2: Tactical Asset Synthesis & Adversarial Debate** (`stage2_per_asset`, `debate_bull`, `debate_bear`, `debate_judge`)  
  *Characteristics:* Strict JSON schema compliance, microstructure/SMC chart alignment, adversarial cross-examination, and calibrated confidence scoring ($0.0 - 1.0$). Best suited for disciplined, high-fidelity reasoning models.
- **Tier 3: High-Frequency Verification & Prescreening** (`stage1_shadow_check`, `stage2_prescreen`, `news_classification`, `fundamental_verifier`)  
  *Characteristics:* Sub-second validation, rapid headline filtering, and structural sanity checks executed before spinning up heavier debate pipelines. Best suited for ultra-fast, zero-cost, or lightweight inference engines.
- **Tier 4: Operator & Telegram Interaction** (`chat_telegram`, `report_synthesizer`)  
  *Characteristics:* Conversational explanations of trade setups, command parsing, and Human-in-the-Loop (HITL) authorization dialogs with tool-calling capabilities.

#### 2. Automated Multi-Tier Fallback Cascades
Every task role in `settings.yaml` supports an ordered chain of fallbacks (`fallback_1`, `fallback_2`, `fallback_3`, etc.). If a provider experiences rate limits (HTTP 429), API outages, or token exhaustion, Monika automatically cascades down to subsequent providers in milliseconds, guaranteeing high system availability.

#### 3. Configuring Your Preferred Models
To assign or test different models, simply update `trading-agent/config/settings.yaml`:

```yaml
llm:
  task_roles:
    stage1_fundamental:
      primary: your-preferred-macro-model       # e.g., your favorite frontier reasoning model
      fallback_1: your-fast-backup-model        # e.g., low-latency secondary model
      fallback_2: openrouter/free               # e.g., zero-cost community fallback
      max_tokens: 16384
      temperature: 0.0

    debate_judge:
      primary: your-preferred-arbitration-model # e.g., impartial reasoning model
      fallback_1: your-backup-model
      max_tokens: 6144
      temperature: 0.0

    stage2_prescreen:
      primary: your-fastest-prescreen-model     # e.g., high-throughput verification engine
      fallback_1: your-lightweight-fallback
      max_tokens: 1024
      temperature: 0.0
```

#### 4. Supported Provider Protocols
Monika natively interfaces with a wide spectrum of providers:
- **Google Gemini API:** Native Google SDK with multi-key rotation and thinking budget controls.
- **Groq API:** Ultra-low latency inference for fast-turn fallbacks and rapid tool calls.
- **OpenRouter & 9Router:** Unified gateway to hundreds of frontier and open-source models with prompt caching and free-tier options.
- **Anthropic, OpenAI, DeepSeek:** Native and OpenAI-compatible REST endpoints.
- **Ollama:** On-premise, fully private local execution for air-gapped environments.



---

## 🚀 7. Practical Getting Started Guide

### 1. Prerequisites & System Requirements
- **Operating System:** Windows 10/11 or Windows Server (required for native MT5 Terminal execution; Linux supported via Wine / Docker container in `deploy/`).
- **Python:** `3.11` or higher.
- **Database:** PostgreSQL `16.0` or higher (mandatory for async concurrency and advisory locks).
- **Node.js:** `18.0` or higher and `npm` (for the React Web Dashboard).
- **Broker:** MetaTrader 5 Desktop Terminal installed with an active demo account.

---

### 2. Installation from Source

```bash
# 1. Clone the repository
git clone https://github.com/alakbarr/Monika.git
cd Monika

# 2. Create and activate a Python virtual environment
# Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

# Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install --upgrade pip
pip install -r trading-agent/requirements.txt

# 4. Build the Web Dashboard frontend
cd trading-agent/logging_observability/dashboard/frontend
npm install
npm run build
cd ../../../..
```

---

### 3. Database Setup & Alembic Migrations

Ensure your PostgreSQL service is running, create an empty database:
```sql
CREATE DATABASE monika_trading;
```

Run database migrations to generate all required tables and indexes:
```bash
cd trading-agent
alembic upgrade head
cd ..
```

---

### 4. Environment Configuration (`.env`)

Copy the template configuration file:
```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in your credentials:
```ini
# Database Connection (PostgreSQL 16+)
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/monika_trading

# MetaTrader 5 Configuration
MT5_ACCOUNT=12345678
MT5_PASSWORD=YourDemoPassword
MT5_SERVER=MetaQuotes-Demo
MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe

# LLM Providers (Gemini and/or OpenRouter/Groq recommended)
GEMINI_API_KEYS=AIzaSyKey1,AIzaSyKey2
OPENROUTER_API_KEYS=sk-or-v1-...
GROQ_API_KEY=gsk_...
# Optional / Upstream Providers
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-proj-...
TYPESAFE_API_KEY=ts_...

# Optional Data Feeds & Sentiment
FRED_API_KEY=your_fred_api_key
FINNHUB_API_KEY=your_finnhub_api_key

# Remote Telegram Supervision (Recommended)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_ADMIN_CHAT_ID=123456789
```

> [!CAUTION]
> **Never commit your `.env` file to version control.** It is protected by `.gitignore` by default.

---

### 5. Pre-Flight Health Verification (Doctor)

Before launching the autonomous daemon, verify that all systems, database connections, MT5 IPC bridges, and API credentials are functional:

```bash
python trading-agent/cli/main.py doctor
```

The Doctor utility verifies:
- PostgreSQL connection & Alembic migration status.
- MetaTrader 5 path existence and account authentication.
- LLM API key validity and connectivity.
- MQL5 heartbeat folder read/write permissions.

---

### 6. Running Monika

#### Option A: One-Click Startup Script (Windows)
Launches the background trading daemon, web dashboard, and gateway in separate terminal tabs:
```cmd
trading-agent\start_agent.bat
```

#### Option B: One-Click Startup Script (Linux / macOS)
```bash
bash trading-agent/start_agent.sh
```

#### Option C: Interactive CLI Daemon (Paper Mode)
```bash
python trading-agent/cli/main.py run --mode paper
```

#### Option D: Terminal UI (TUI) Mode
To open the real-time terminal telemetry interface:
```bash
python trading-agent/cli/main.py tui
```

#### Option E: Containerized Deployment (Docker Compose)
To launch PostgreSQL and the background environment in Docker:
```bash
docker compose up -d
```

---

## 🕹️ 8. CLI & Telegram Command Reference

### CLI Command Suite (`trading-agent/cli/main.py`)

| Command | Action / Purpose |
| :--- | :--- |
| `python -m cli.main setup` | Interactive terminal wizard to configure `.env` and broker settings. |
| `python -m cli.main doctor` | Diagnostic health check verifying DB, MT5, and API keys. |
| `python -m cli.main run` | Launches the autonomous trading agent daemon. |
| `python -m cli.main status` | Displays system status, active background tasks, and account equity. |
| `python -m cli.main positions` | Lists open MT5 positions, lots, floating PnL, and active stops. |
| `python -m cli.main analyze [SYMBOL]` | Runs an on-demand analysis cycle for a specified asset (e.g. `XAUUSD`). |
| `python -m cli.main chat` | Starts an interactive chat REPL with the agent assistant. |
| `python -m cli.main ask "QUERY"` | Executes a one-shot market or system query and exits. |
| `python -m cli.main pause` | Temporarily halts new trade proposal execution. |
| `python -m cli.main resume` | Resumes automated trade execution. |
| `python -m cli.main kill` | **Emergency Circuit Breaker:** Liquidates all active positions and halts the daemon. |
| `python -m cli.main tui` | Opens the full-screen interactive Terminal UI (Textual). |
| `python -m cli.main backtest` | Launches the historical point-in-time backtesting engine. |
| `python -m cli.main benchmark` | Runs the Alpha Arena LLM model comparison benchmark. |

---

### Telegram Remote Bot Commands

| Command | Access Level | Description |
| :--- | :--- | :--- |
| `/status` | Public | View system health, open positions, floating PnL, and risk state. |
| `/positions`| Public | List open tickets, entry prices, stop losses, and take profits. |
| `/brief` | Public | Display the latest Stage 1 macroeconomic narrative brief. |
| `/risk` | Public | Inspect current daily drawdown gauges and circuit breaker status. |
| `/vix` | Public | View current market volatility reading and active regime mode. |
| `/tokens` | Public | Check LLM token usage, cost expenditure, and cache hit rates. |
| `/run` | Admin | Manually trigger an immediate multi-agent analysis cycle. |
| `/pause` | Admin | Pause automated trade intake with optional reason. |
| `/resume` | Admin | Resume automated trade intake. |
| `/close <ticket>` | Admin | Close a specific open ticket (requires confirmation). |
| `/kill` | Admin | **Emergency Circuit Breaker:** Liquidate all active positions and halt immediately. |
| `/help` | Public | Display command menu and usage instructions. |

---

## 🧪 9. Testing, Backtesting & Evaluation Suite

### Running Automated Tests
Monika enforces rigorous test coverage across risk calculations, SMC indicator logic, debate arbitration, and broker execution bridges:

```bash
# Run full test suite (PowerShell):
$env:PYTHONPATH="trading-agent"; python -m pytest trading-agent/tests -v

# Run full test suite (Linux/macOS):
PYTHONPATH=trading-agent pytest trading-agent/tests -v

# Run targeted RiskGate validation tests:
PYTHONPATH=trading-agent pytest trading-agent/tests/risk/test_risk_gate.py -v

# Run SMC market structure tests:
PYTHONPATH=trading-agent pytest trading-agent/tests/indicators/test_structure.py -v
```

### Point-in-Time Backtesting Engine
Test strategies against historical market conditions without lookahead bias:
```bash
python trading-agent/cli/main.py backtest --symbol XAUUSD --days 30
```

### Alpha Arena Model Benchmarking
Compare reasoning quality, confidence calibration, and token efficiency across different LLM providers using historical market fixtures:
```bash
python trading-agent/cli/main.py benchmark --models model_a,model_b,model_c
```

---

## ❓ 10. Frequently Asked Questions (FAQ)

### Q: What is Monika in one sentence?
**A:** Monika is a domain-specific multi-agent trading harness for MetaTrader 5 that combines macroeconomic synthesis and SMC order flow with dialectical Bull/Bear debate, guarded by an unbypassable mechanical risk fortress.

### Q: Is Monika guaranteed to be profitable?
**A:** **No.** Financial markets are non-linear, unpredictable, and subject to structural regime shifts. Monika is engineered to enforce extreme risk discipline and capital preservation, but no software can eliminate market risk.

### Q: Why can't I just connect ChatGPT or Claude directly to MetaTrader 5?
**A:** Unconstrained LLMs suffer from mathematical hallucinations, cannot calculate accurate lot sizes or pip values, suffer from confirmation bias, and lack emergency circuit breakers. Monika provides the essential *harness*—handling data normalization, multi-agent cross-examination, and deterministic mathematical risk filtering.

### Q: Why is PostgreSQL required instead of SQLite?
**A:** Monika coordinates 18+ concurrent asynchronous background tasks. SQLite suffers from write lock contention under high async loads. Furthermore, Monika relies on PostgreSQL advisory locks and partial unique indexes to guarantee that no duplicate orders can ever be submitted for the same asset signal.

### Q: Why does Monika refuse to start without Paper Trading mode?
**A:** Safety is the primary architectural directive. Monika enforces `paper_trading.enabled: true` by default. Switching to live money execution requires accumulating at least 50 validated paper trades with an overall win rate $\ge 55\%$.

### Q: How much does it cost in LLM API fees to run Monika?
**A:** Because Monika utilizes KV prompt caching (~70–80% cache hit rate), delta watermarks, and routes high-frequency prescreening to zero-cost or lightweight models while reserving heavier models for complex escalation, operating costs typically range between **$0.50 – $2.00 per day** under normal continuous operation (and can be $0 if leveraging local Ollama or free-tier community providers).

### Q: Can I run Monika on a Linux VPS?
**A:** Yes. While the official `MetaTrader5` Python package is a Windows C-extension, Monika provides a containerized Wine/Docker RPC solution in `deploy/Dockerfile.mt5-wine` and `deploy/vps_deployment_guide.md`.

---

## 📁 11. Repository Structure

```
Monika/
├── PRD.md                     # Project Requirements Document (Comprehensive Spec)
├── README.md                  # System overview, quickstart, and interfaces
├── DESIGN.md                  # Web Dashboard design specifications
├── CONTRIBUTING.md            # Guidelines for open-source contributions
├── CODE_OF_CONDUCT.md         # Community code of conduct
├── SECURITY.md                # Security policy and vulnerability disclosure
├── INDEX.md                   # Exhaustive codebase index with line citations
├── STRUCTURE.md               # Complete directory inventory and file tree
├── deploy/                    # Linux VPS deployment assets (Wine, Docker, guides)
├── docs/                      # UI screenshots, architecture diagrams, assets
├── scripts/                   # Migration, benchmark, and administrative scripts
└── trading-agent/             # Core application codebase
    ├── main.py                # Top-level orchestrator & asyncio runtime
    ├── agent/                 # Lifecycle managers, health monitors, watchdogs
    ├── analysis/              # Multi-agent debate, SMC calculators, prompt templates
    │   ├── arbitration/       # SignalArbitrator (Quant Alpha vs. LLM Debate)
    │   ├── calculators/       # Economic surprise, FVG, volume profile, TimesFM
    │   ├── debate/            # Bull Analyst, Bear Analyst, Investment Judge
    │   ├── memory/            # 4-Layer Memory (Soul, Macro, Chronicle, Reflection)
    │   └── providers/         # Multi-provider LLM clients & KV prompt caching
    ├── backtest/              # Point-in-time, walk-forward, and Monte Carlo engine
    ├── benchmark/             # Alpha Arena, model registry, prompt evolution
    ├── cli/                   # Terminal UI (TUI) and comprehensive CLI subcommands
    ├── config/                # settings.yaml, schema validators, hot-reload engine
    ├── database/              # SQLAlchemy 2.0 async models, migrations, advisory locks
    ├── evals/                 # Hostile market scenario probes & simulation clocks
    ├── execution/             # Native MT5 client, MQL5 EA bridge, execution service
    ├── gateway/               # Omnichannel router (Telegram, Discord, Slack, ACP)
    ├── graph/                 # LangGraph state machine node implementations
    ├── harness/               # Universal plugin engine, lifecycle & event bus
    ├── indicators/            # Classical indicators, SMC structures, Google TimesFM 3.0
    ├── logging_observability/ # Structured activity logs, Prometheus, React 19 Web Dashboard
    ├── risk/                  # Deterministic RiskGate (10 layers), sizing, circuit breakers
    ├── scheduler/             # 18+ Background task loops (news, triggers, cycles, guardians)
    ├── scrapers/              # Scraping engines (Calendars, FRED, News RSS, Sentiment)
    ├── skills/                # Unified skills runtime & continuous learning playbooks
    └── telegram_bot/          # Telegram bot handler & interactive keyboards
```

---

## 🤝 12. Contributing, Security & Community

We believe the most resilient trading software is built through public peer review, transparent engineering, and collective scrutiny.

- **Found a bug or risk calculation error?** Please submit a detailed [GitHub Issue](https://github.com/alakbarr/Monika/issues).
- **Have architectural suggestions?** Join the conversation in [GitHub Discussions](https://github.com/alakbarr/Monika/discussions).
- **Want to contribute code?** Check out our [Contributing Guidelines](CONTRIBUTING.md) and submit a pull request!
- **Security Vulnerabilities:** Please review our [Security Policy](SECURITY.md) to report vulnerabilities privately.

---

## ⚖️ 13. Financial & Research Disclaimer

> [!CAUTION]
> **STRICTLY FOR RESEARCH, EDUCATIONAL, AND EXPERIMENTAL PURPOSES ONLY.**
>
> Financial speculation and trading in foreign exchange, commodities, cryptocurrencies, and leveraged instruments carry a **substantial risk of financial loss**.
>
> The developers, authors, and contributors of Monika make no claims, promises, warranties, or representations regarding profitability, performance, or fitness for real-money trading.
>
> **Never risk capital you cannot comfortably afford to lose.** Always validate algorithmic software extensively under paper-trading or demo-account conditions before considering live capital deployment.

---

<p align="center">
  <sub>Monika Quantitative Trading Agent Harness &bull; Built with LangGraph, FastAPI, and MetaTrader 5</sub>
</p>
