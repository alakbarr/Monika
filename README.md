# Monika — Autonomous MT5 Quantitative Trading Agent

<p align="center">
  <img src="docs/images/01_trading_desk_overview.png" alt="Monika Trading Desk Overview" width="100%" style="border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);" />
</p>

<p align="center">
  <strong>Autonomous Multi-Agent Quantitative Trading System for MetaTrader 5 (MT5)</strong><br />
  <em>Orchestrated by LangGraph &bull; Smart Money Concepts (SMC) &bull; Dialectical Bull/Bear Debate &bull; Deterministic RiskGate &bull; Full-Stack React & TUI Observability</em>
</p>

<p align="center">
  <a href="https://github.com/alakbarr/Monika/actions/workflows/ci.yml"><img src="https://github.com/alakbarr/Monika/actions/workflows/ci.yml/badge.svg" alt="CI Pipeline" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python&logoColor=white" alt="Python 3.11+" /></a>
  <a href="https://langchain-ai.github.io/langgraph/"><img src="https://img.shields.io/badge/Orchestration-LangGraph-1C75BC.svg?logo=langchain&logoColor=white" alt="LangGraph" /></a>
  <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/FastAPI-0.111%2B-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/Frontend-React%2019%20%2B%20Vite-61DAFB.svg?logo=react&logoColor=black" alt="React 19" /></a>
  <a href="https://www.postgresql.org"><img src="https://img.shields.io/badge/Database-PostgreSQL%2016%2B-336791.svg?logo=postgresql&logoColor=white" alt="PostgreSQL 16+" /></a>
  <a href="https://www.metatrader5.com"><img src="https://img.shields.io/badge/Execution-MetaTrader%205-red.svg" alt="MetaTrader 5" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License" /></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/Code%20Style-Ruff-black.svg" alt="Ruff" /></a>
</p>

---

## Executive Overview

**Monika** is an autonomous multi-agent quantitative trading system built specifically for **MetaTrader 5 (MT5)**. Unlike conventional trading bots that rely on static technical indicators or single prompt-completion models, Monika operates as a structured investment committee:

1. **Macroeconomic Grounding (Stage 1)**: Ingests interest rate expectations, inflation metrics (CPI/PCE), labor data (NFP), FRED economic indicators, and news wires to construct a multi-week macroeconomic regime thesis.
2. **Quantitative & Technical Synthesis (Stage 2)**: Detects market microstructure—Fair Value Gaps (FVG), Break of Structure (BOS), Change of Character (CHoCH), and Liquidity Sweeps—cross-referenced with **Google TimesFM 3.0** volatility envelopes.
3. **Dialectical Adversarial Debate**: For every candidate setup, dedicated **Bull** and **Bear** specialist agents debate the thesis in multi-round discourse, cross-examining invalidation levels and risk/reward asymmetry before an arbitration judge (`InvestmentJudge`) computes a calibrated confidence score.
4. **Deterministic Hard Risk Gate**: AI models are **strictly forbidden** from directly transmitting orders to the broker. All signals must pass through an immutable, rule-based `RiskGate` calculating daily drawdown budgets, spread limits, volatility-adjusted position sizing, and correlation caps.
5. **Dual-Execution Engine**: Direct IPC with MetaTrader 5 Terminal via official MetaTrader5 Python API coupled with an MQL5 Expert Advisor bridge (`AIAgent_EA.mq5`) featuring real-time heartbeats and dead-man fail-safe auto-liquidation.

---

## Visual Tour & Interface Showcase

Monika features dual observability interfaces: a modern **React 19 Dashboard** with sub-second WebSocket telemetry, and a lightweight **Textual Terminal UI (TUI)** for headless server deployments.

> [!NOTE]
> All telemetry readings, account balances, and win-rate statistics shown in the showcase interfaces represent paper-trading simulations and diagnostic verification sessions.

### 1. Trading Desk: Main Portfolio Overview
> Real-time portfolio telemetry, floating equity curves, factor dispatch activity, live MT5 open positions, and system health status.

<p align="center">
  <img src="docs/images/01_trading_desk_overview.png" alt="Trading Desk Overview" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Active Capital Tracking**: Monitored Daily PnL, balance curve, total trade volume, and win rate benchmarks.
- **Live MT5 Open Positions**: Real-time tracking of execution tickets across `XAUUSD`, `EURUSD`, and `BTCUSD` with lot sizing and dynamic stop-loss levels.
- **Factor Dispatch Feed**: Real-time event log streaming subagent analysis events, trigger activations, and risk compliance approvals.

---

### 2. Market Intelligence: LangGraph Pipeline DAG
> Interactive visualization of Monika's 7-stage LangGraph state machine orchestrating end-to-end decision cycles.

<p align="center">
  <img src="docs/images/04_market_intelligence_pipeline_dag.png" alt="LangGraph Pipeline DAG" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **7-Stage Stateful Graph**:
  `Stage 1 (Macro Ingestion)` &rarr; `Stage 2 (Microstructure & SMC)` &rarr; `Bullish Specialist` & `Bearish Specialist` &rarr; `Adversarial Debate` &rarr; `Investment Judge` &rarr; `Deterministic Risk Gate` &rarr; `MT5 Execution Service`.
- **Node State Inspector**: Live inspection of inputs, outputs, execution latencies, and state transitions for every autonomous node in the graph.

---

### 3. Ledger & Risk: Hard Limits & Circuit Breakers
> The mechanical capital preservation engine. Deterministic safeguards protecting against drawdown breaches, spread spikes, and execution anomalies.

<p align="center">
  <img src="docs/images/06_ledger_risk_limits.png" alt="Hard Risk Limits and Circuit Breakers" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Analog VU Gauges**: Visual telemetry tracking current Daily Drawdown (`1.2%` vs `3.0%` max ceiling) and Maximum Total Drawdown (`2.8%` vs `6.0%` limit).
- **Circuit Breaker Status**: Active fail-safe that liquidates and suspends trading if daily loss budgets are threatened.
- **Enforced Parameters**: Dynamic position size limits, maximum concurrent open exposure (max 5 positions), minimum Risk:Reward thresholds (`1:2.0`), and spread threshold filters.

---

### 4. Telegraph: Human-In-The-Loop (HITL) Desk Console
> Interactive terminal console for conversational debriefing, manual trade authorization, and audit logs.

<p align="center">
  <img src="docs/images/08_telegraph_desk_console_chat.png" alt="Telegraph Desk Console" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Interactive Macro Dialogue**: Query market context, central bank rate probabilities, and structural trade reasoning on demand.
- **Human-In-The-Loop Approval Cards**: When configured in supervised mode, actionable trade proposals require one-click operator confirmation before MT5 dispatch.
- **Inspection Badges**: Real-time visibility into internal tool calls (`MacroeconomicPrefetch`, `FedWatchCalculator`, `SMCStructureScanner`), database lookups, and latency metrics.

---

<details>
<summary><b>🔍 View Additional Operations & Telemetry Panels (6 Panels)</b></summary>
<br />

#### 5. Trading Desk: Signals & Triggers Matrix
> Precision execution telemetry showing latency benchmarks, executed alpha signals, and active conditional order triggers.

<p align="center">
  <img src="docs/images/02_trading_desk_signals.png" alt="Signals and Triggers Matrix" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Execution Telemetry**: MT5 IPC round-trip latency tracking, fill confirmations, and order ticket matching.
- **Executed Alpha Signals**: Comprehensive execution history detailing asset, ticket, entry, and fill latency.
- **Conditional Trigger Monitor**: Real-time evaluation of pending and successfully fired conditional triggers.

---

#### 6. Trading Desk: Live Market Data & Macro Calendar
> Real-time streaming quotes from the live MetaTrader 5 terminal, market volatility barometers, and high-impact economic calendar.

<p align="center">
  <img src="docs/images/03_trading_desk_market.png" alt="Live Market Data Panel" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Direct MT5 Ticks**: Real-time Bid/Ask quotes for Major FX pairs (`EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`), Commodities (`XAUUSD`, `XTIUSD`), and Crypto (`BTCUSD`).
- **Macro Volatility Barometer**: Live VIX tracking with regime classification (Low/Normal/Elevated/Extreme).
- **Live Economic Releases**: Calendar events scraped directly from financial news sources with impact classifications.

---

#### 7. Market Intelligence: Macroeconomic Intelligence Brief
> AI-synthesized macroeconomic dossier detailing monetary policy expectations, yield curve dynamics, and cross-asset flows.

<p align="center">
  <img src="docs/images/05_market_intelligence_macro_brief.png" alt="Macroeconomic Intelligence Brief" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Central Bank Rate Path Analysis**: Synthesis of Federal Reserve, ECB, and BOJ policy stances with terminal rate projections.
- **Yield Curve & Commodity Dynamics**: Cross-asset impact analysis linking US Treasury yields, safe-haven demand, and energy transit factors.
- **Synthesized Bias Matrix**: Multi-day directional bias tags (Bullish / Neutral / Bearish) informing downstream technical analysis.

---

#### 8. Ledger & Risk: LLM Token Audit & Cost Economics
> Token telemetry and expense tracking across LLM inference calls, caching efficiency, and role-based resource utilization.

<p align="center">
  <img src="docs/images/07_ledger_llm_token_audit.png" alt="LLM Token Audit" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Prompt Caching Telemetry**: High-efficiency caching achieving up to **79.4% cache hit rates**, cutting operational API inference costs.
- **Role-Based Token Breakdown**: Granular accounting of prompt/completion tokens across task roles (`Macro Analyst`, `SMC Specialist`, `Bull Debater`, `Bear Debater`, `Investment Judge`).
- **Multi-Model Provider Routing**: Real-time distribution across Anthropic Claude, Google Gemini, and DeepSeek.

---

#### 9. System Configuration: Dynamic Settings Inspector
> Live configuration management interface displaying active risk limits, model routing matrices, and an integrated YAML editor.

<p align="center">
  <img src="docs/images/09_system_configuration.png" alt="System Configuration Inspector" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Hot-Reloadable Parameters**: Adjust risk tolerances, target assets, and scheduler frequencies without restarting running background tasks.
- **Model Routing Matrix**: Inspect and remap task roles to specific LLM models, temperatures, and fallback providers on the fly.
- **Raw YAML Editor**: Direct control over `settings.yaml` with schema validation.

---

#### 10. Headless Terminal UI (TUI)
> High-performance ASCII/Unicode terminal dashboard built with Textual for low-resource VPS and headless server environments.

<p align="center">
  <img src="docs/images/10_terminal_ui_tui.png" alt="Textual Terminal UI" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Zero GUI Overhead**: Runs directly inside SSH sessions with low memory footprint.
- **Live Sparklines**: Dynamic ASCII mini-charts rendering real-time equity curves and drawdown trajectories.
- **Hotkeys & Console REPL**: Quick keyboard navigation (`Tab`, `1-4`, `q`), integrated command line, and live activity stream.

</details>

---

## Core System Architecture

Monika's architecture is engineered around strict separation of concerns, ensuring deterministic capital safety while leveraging cutting-edge generative intelligence.

```mermaid
flowchart TD
    subgraph DataIngestion ["1. Data Ingestion & Microstructure"]
        MT5[MetaTrader 5 IPC Feed] --> DataHub[Data Aggregator]
        FRED[FRED / Finnhub API] --> DataHub
        News[Financial RSS & Wire News] --> DataHub
        DataHub --> SMC[SMC Indicator Engine<br/>BOS / CHoCH / FVG / Liquidity]
        DataHub --> TimesFM[Google TimesFM 3.0<br/>Volatility Envelopes]
    end

    subgraph LangGraphPipeline ["2. LangGraph Multi-Agent Pipeline"]
        SMC --> S1[Stage 1: Macroeconomic Ingestion]
        TimesFM --> S1
        S1 --> S2[Stage 2: Asset Tactical Synthesis]
        S2 --> Bull[Bull Specialist Agent]
        S2 --> Bear[Bear Specialist Agent]
        Bull <--> Debate[Dialectical Adversarial Debate]
        Bear <--> Debate
        Debate --> Judge[Investment Arbitration Judge]
    end

    subgraph SafetyGate ["3. Hard Deterministic Capital Gate"]
        Judge --> SignalProposal[Raw Alpha Signal Proposal]
        SignalProposal --> RiskGate{Mechanical RiskGate}
        RiskGate -- Breach --> Rejected[Signal Rejected & Logged]
        RiskGate -- Approved --> Sizing[Volatility & Kelly Position Sizer]
    end

    subgraph ExecutionBridge ["4. Dual MT5 Execution Bridge"]
        Sizing --> Dispatcher[Execution Service]
        Dispatcher --> MT5_IPC[Python-MT5 Native Client]
        Dispatcher --> EA_Bridge[MQL5 EA Bridge<br/>Heartbeat & Dead-Man Switch]
        MT5_IPC --> Broker[(Broker Order Book)]
        EA_Bridge --> Broker
    end

    subgraph Observability ["5. Full-Stack Telemetry & Observability"]
        Broker --> Postgres[(PostgreSQL 16+)]
        FastAPI --> WebDash[React 19 Cyber-Dashboard]
        FastAPI --> TUI[Textual Terminal UI]
        FastAPI --> TeleBot[Interactive Telegram Bot]
    end
```

---

## Key Features Breakdown

### 1. Multi-Agent Dialectical Debate Engine
- **Hierarchical Two-Stage Pipeline**: Macro thesis formation runs on an 8-hour schedule; per-asset tactical setups trigger dynamically upon market structure shifts.
- **Adversarial Debaters**: Dedicated Bull and Bear agents are prompted to ruthlessly attack each other's assumptions, identifying hidden liquidity traps, unmitigated order blocks, and economic calendar risks.
- **Calibrated Confidence Judge**: Evaluates argument validity against empirical market microstructure, producing calibrated confidence scores (`0.0 - 1.0`). Setups below `0.70` confidence are automatically pruned.

### 2. Smart Money Concepts (SMC) & Machine Learning
- **Algorithmic Structure Detection**: Automatically maps Break of Structure (BOS), Change of Character (CHoCH), Fair Value Gaps (FVG), Order Blocks, and Liquidity Pools across multiple timeframes (M5, M15, H1, H4, D1).
- **Google TimesFM 3.0 Foundation Model**: Pre-trained zero-shot time-series model predicting expected intraday ranges and dynamic volatility channels.

### 3. Absolute Capital Protection (RiskGate)
- **Zero AI Override**: AI models generate proposals; only deterministic Python code signs and executes orders.
- **Circuit Breakers**: Hard daily loss limits (realized + floating). If breached, all open orders are closed and the system halts trading for the remainder of the session.
- **Mandatory Paper Trading Incubation**: Built-in graduation criteria (`paper_trading.enabled: true`) requiring a minimum of 50 paper trades with &ge;55% win rate before live capital execution can be unlocked.

### 4. Dual MT5 Execution Bridge & EA Fail-Safe
- **Native Python IPC**: Direct connection with the MetaTrader 5 terminal via the official MetaTrader5 Python API for order routing and position queries.
- **MQL5 Fallback Bridge (`AIAgent_EA.mq5`)**: An Expert Advisor running inside MT5 that monitors heartbeat tokens. If Monika's Python process crashes or loses network connectivity, the EA activates its dead-man switch, automatically closing open exposure.

### 5. Multi-Provider LLM Routing & Token Economics
- **Task-Specific Role Routing**: Automatically pairs task complexity with the optimal LLM (e.g., Anthropic Claude 3.5 Sonnet for debate arbitration, Google Gemini 2.5 Flash for high-frequency news analysis, DeepSeek-R1 for mathematical calculations).
- **Prompt Caching Optimization**: Structured system prompts designed for provider cache reuse, delivering up to 80% cache hit rates.

---

## Technical Specifications & Documentation

Comprehensive architectural blueprints, database schemas, and state machine specifications are documented in the repository:

| Document | Purpose |
| :--- | :--- |
| [**System Architecture & Specifications**](trading-agent/spesifikasi_final_ai_trading_agent.md) | Exhaustive 1,000+ line technical specification covering all sub-systems |
| [**Codebase Index (INDEX.md)**](INDEX.md) | Line-referenced catalog of every function, class, and variable |
| [**Directory Structure (STRUKTUR.md)**](STRUKTUR.md) | Complete directory tree and file inventory |

---

## Prerequisites

Before setting up Monika, ensure your environment meets the following requirements:

- **Operating System**: Windows 10/11 or Windows Server (required for native MT5 Terminal execution; Linux supported via Wine or Docker remote bridge)
- **Python**: `3.11` or higher
- **Node.js**: `18.0` or higher & `npm` (for the React Dashboard)
- **PostgreSQL**: `16.0` or higher
- **MetaTrader 5**: Desktop terminal installed with an active broker account (Demo or Live)

---

## Quick Start Installation

### 1. Clone Repository
```bash
git clone https://github.com/alakbarr/Monika.git
cd Monika
```

### 2. Set Up Python Virtual Environment
```bash
# Windows (PowerShell):
python -m venv venv
venv\Scripts\activate

# Linux / macOS:
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Python Dependencies
```bash
pip install --upgrade pip
pip install -r trading-agent/requirements.txt
```

### 4. Build Dashboard Frontend
```bash
cd trading-agent/logging_observability/dashboard/frontend
npm install
npm run build
cd ../../../..
```

### 5. Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```

Open `.env` in your text editor and provide the necessary credentials:
```ini
# ==========================================
# 1. Database & MetaTrader 5 (Required)
# ==========================================
DATABASE_URL=postgresql+asyncpg://monika_user:your_secure_password@localhost:5432/monika_trading
MT5_ACCOUNT=12345678
MT5_PASSWORD=your_mt5_broker_password
MT5_SERVER=YourBroker-Demo
MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe

# ==========================================
# 2. Telegram Bot Supervision (Recommended)
# ==========================================
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_ADMIN_CHAT_ID=987654321
TELEGRAM_ALLOWED_USERS=987654321

# ==========================================
# 3. LLM API Providers & Rotation Pools
# ==========================================
ANTHROPIC_API_KEY=sk-ant-api03-...
GEMINI_API_KEYS=key1,key2,key3
GEMINI_PAID_API_KEY=your_gemini_paid_key
OPENAI_API_KEY=sk-proj-...
DEEPSEEK_API_KEY=sk-...
GROQ_API_KEYS=gsk_...
OPENROUTER_API_KEYS=sk-or-v1-...
OPENROUTER_PAID_API_KEY=sk-or-v1-...

# ==========================================
# 4. Economic, News Search & Model Weights
# ==========================================
FRED_API_KEY=your_fred_api_key
FINNHUB_API_KEY=your_finnhub_api_key
EIA_API_KEY=your_eia_api_key
TAVILY_API_KEYS=tvly-...
HF_TOKEN=hf_...  # For Google TimesFM 3.0 weights download

# ==========================================
# 5. Dashboard & Remote Execution Gateway
# ==========================================
DASHBOARD_PORT=8000
DASHBOARD_SECRET=your_secure_dashboard_token
EXECUTION_SERVICE_URL=http://127.0.0.1:8080
EXECUTION_SERVICE_AUTH_TOKEN=your_gateway_auth_token
```

> [!CAUTION]
> **Never commit `.env` or broker passwords to version control.** Keep your live trading credentials strictly isolated.

---

## Running Monika

### Dry-Run / Paper Trading Mode (Default)
Monika defaults to paper trading mode (`paper_trading.enabled: true`), simulating all orders against live tick data without risking real capital:

**On Windows:**
```cmd
trading-agent\start_agent.bat
```

**On Linux / macOS:**
```bash
bash trading-agent/start_agent.sh
# or via Makefile:
make run
```

### Launching the Textual Terminal UI (TUI)
For an interactive terminal control center:
```bash
# From repository root:
python trading-agent/cli/main.py tui

# Or within trading-agent directory:
cd trading-agent && python cli/main.py tui
```

### Running via Docker Compose
To run the full stack (PostgreSQL database, FastAPI backend, and dashboard) in Docker containers:
```bash
# Launch containers in background
docker compose up -d

# Inspect live agent logs
docker compose logs -f monika-core

# Graceful shutdown
docker compose down
```

---

## Observability & Endpoints

Once the agent is active, access its interfaces at the following endpoints:

| Interface | URL | Description |
| :--- | :--- | :--- |
| **React Dashboard** | [`http://localhost:5173`](http://localhost:5173) | Primary visual trading desk, telemetry, and controls |
| **FastAPI Swagger Docs** | [`http://localhost:8000/api/docs`](http://localhost:8000/api/docs) | Interactive OpenAPI testing and API explorer |
| **ReDoc API Schema** | [`http://localhost:8000/api/redoc`](http://localhost:8000/api/redoc) | Clean formatted API reference documentation |
| **Prometheus Metrics** | [`http://localhost:8000/api/metrics`](http://localhost:8000/api/metrics) | Scrape target for Prometheus & Grafana alerting |

---

## Telegram Remote Command Reference

Supervise and control Monika on the go via the official Telegram bot integration:

| Command | Category | Action |
| :--- | :--- | :--- |
| `/status` | Public | Inspect system health, running tasks, open positions, and risk metrics |
| `/positions` | Public | List open tickets, entry prices, floating PnL, lot sizes, and active SL/TP |
| `/brief` | Public | Display the latest Stage 1 macroeconomic regime analysis summary |
| `/risk` | Public | View active drawdown gauges, circuit breaker states, and risk budget |
| `/vix` | Public | Check current VIX index reading and volatility regime classification |
| `/tokens` | Public | Display cumulative LLM token consumption and prompt cache hit rates |
| `/report` | Public | Export the daily performance ledger, execution audit, and trade summaries |
| `/pause` | Admin | Temporarily halt automated signal intake and trigger evaluation |
| `/resume` | Admin | Resume automated signal intake and scheduling |
| `/run` | Admin | Manually dispatch an immediate end-to-end analysis and debate cycle |
| `/kill` | Admin | **Emergency Circuit Breaker** &mdash; Liquidates active open positions and freezes execution |
| `/help` | Public | List all available interactive bot commands |

---

## Automated Test Suite

Monika is backed by an extensive pytest test suite covering risk calculations, SMC detection, debate arbitration, and MT5 bridges:

```bash
# Run complete test suite (PowerShell):
$env:PYTHONPATH="trading-agent"; python -m pytest trading-agent/tests -v

# Run complete test suite (Linux/macOS):
PYTHONPATH=trading-agent pytest trading-agent/tests -v

# Run targeted risk gate validation:
PYTHONPATH=trading-agent pytest trading-agent/tests/risk/test_risk_gate.py -v
```

---

## Project Structure

```
Monika/
├── docs/                      # Documentation assets and screenshots
│   └── images/                # High-resolution showcase UI screenshots
├── scripts/                   # Administrative, migration, and screenshot tools
├── trading-agent/             # Main application codebase
│   ├── main.py                # Application entrypoint & multi-task orchestrator
│   ├── agent/                 # Lifecycle managers, health monitors, watchdogs
│   ├── analysis/              # Multi-agent debate, SMC calculators, prompt templates
│   │   ├── debate/            # Bull/Bear adversarial debate state machine
│   │   ├── calculators/       # SMC, FVG, BOS/CHoCH, TimesFM alpha, liquidity sweeps
│   │   └── stages/            # Stage 1 Macro & Stage 2 Asset Synthesis
│   ├── cli/                   # Textual Terminal UI (TUI) implementation
│   ├── config/                # settings.yaml, schema validators, hot-reload engine
│   ├── database/              # SQLAlchemy 2.0 async models, repositories, alembic
│   ├── execution/             # MT5 native IPC client & MQL5 EA bridge
│   ├── graph/                 # LangGraph state machine node implementations
│   ├── logging_observability/ # Activity logging, Prometheus metrics, FastAPI backend
│   │   └── dashboard/         # React 19 + Tailwind CSS visual control desk
│   ├── risk/                  # Deterministic RiskGate, position sizing, circuit breakers
│   ├── scheduler/             # Asynchronous task loops (news, triggers, cycles)
│   └── telegram_bot/          # Telegram bot handler and voice memo transcriber
```

---

## Known Limitations & System Boundaries

- **MetaTrader 5 Host Requirement**: The native `MetaTrader5` Python package requires a Windows environment with an active MT5 Desktop Terminal. Linux server deployments require Wine or a networked execution bridge.
- **PostgreSQL 16+ Mandatory**: SQLite is explicitly disallowed in production and paper-trading runs due to async concurrency, transaction advisory locks, and partial index requirements.
- **LLM Operational Overhead**: Multi-agent adversarial debate and macroeconomic synthesis consume API tokens. While prompt caching yields ~80% cache efficiency, active execution incurs API usage costs across providers.
- **Paper-Trading Graduation Gate**: Monika strictly enforces an incubation requirement of at least 50 paper trades with &ge;55% win rate before live broker dispatch can be unmasked.
- **No Financial Guarantees**: Market regimes can shift unexpectedly. Past simulation performance does not guarantee future results.

---

## Community & Governance

- [Contributing Guidelines](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)
- [Changelog](CHANGELOG.md)
- [License (MIT)](LICENSE)

---

## Financial Disclaimer

> [!WARNING]
> **FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY.**
>
> Algorithmic trading and financial market speculation involve significant risk of monetary loss. The developers, authors, and contributors of this software provide no guarantees, warranties, or representations regarding profitability, performance, or financial outcomes. Never trade with money you cannot afford to lose. Always thoroughly validate any trading system on demo accounts under paper trading conditions before committing real capital.

---

<p align="center">
  <sub>Monika Quantitative Trading Engine &bull; Built with LangGraph, FastAPI, and MetaTrader 5</sub>
</p>
