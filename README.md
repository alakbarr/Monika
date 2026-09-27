# Monika — Domain-Specific Trading Agent Harness for MetaTrader 5

<p align="center">
  <img src="docs/images/01_trading_desk_overview.png" alt="Monika Trading Desk Overview" width="100%" style="border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.3);" />
</p>

<p align="center">
  <strong>An open-source multi-agent research harness and execution framework for MetaTrader 5 (MT5)</strong><br />
  <em>Combining macroeconomic synthesis, Smart Money Concepts (SMC), dialectical Bull/Bear debate, and deterministic risk fortresses.</em>
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

## 📌 Project Status & Development Notice

> [!NOTE]
> **Monika is an early-stage experimental research project.**  
> It is an active exploration into how LLM-based reasoning, multi-agent dialectical debate, and macroeconomic data synthesis can be safely integrated into automated trading workflows without surrendering risk control to probabilistic models.
> 
> The codebase is actively evolving. Expect ongoing refinements, architectural iterations, and occasional rough edges. We do not claim institutional perfection or guaranteed profits. Instead, we are building transparent, disciplined engineering foundations in public.
> 
> **We warmly welcome feedback, ideas, bug reports, and contributions!** Whether you are an experienced quantitative developer, an algorithmic trader, an AI researcher, or a hobbyist systems builder, your perspectives and help in improving Monika are deeply appreciated.

---

## 🧭 What is Monika? (The "Agent Harness" Identity)

Monika is not just a hardcoded script with technical indicators, nor is it an unconstrained chatbot blindly clicking buttons in a trading account.

Monika is fundamentally a **Domain-Specific Trading Agent Harness and Multi-Agent Execution Framework for MetaTrader 5 (MT5)**.

### Why an "Agent Harness"?
Large language models are creative, contextual, and persuasive, but they are also probabilistic and prone to hallucinations. Giving an LLM raw access to a broker order book is a recipe for catastrophic capital loss.

An **Agent Harness** surrounds the AI with rigorous boundaries:
1. **Perception Harness:** Ingests, normalizes, and pre-processes financial news, macroeconomic releases (FRED API, calendar data), and order book ticks before presenting them to the model.
2. **Cognitive Orchestration:** Coordinates specialized agent roles (Macro Analyst, Technical Specialist, Bull Debater, Bear Debater, Investment Judge) through a stateful LangGraph pipeline.
3. **Deterministic Safety Fortress (`RiskGate`):** Adheres to the principle **"AI Proposes, Mechanical Fortress Disposes"**. AI agents only generate structured proposals (`SubmitAssetAnalysisSchema`). Orders can only reach the broker after clearing 10 deterministic mathematical safety checks, dynamic volatility-adjusted position sizing, and circuit breakers.
4. **Execution & Fail-Safe Substrate:** Pairs native MetaTrader 5 Python IPC with an independent MQL5 Expert Advisor (`AIAgent_EA.mq5`) acting as a dead-man's switch.
5. **Evaluation & Learning Harness:** Incorporates point-in-time backtesting, model benchmarking (Alpha Arena), and post-trade reflection memory to continually inspect agent behavior against market reality.

---

## 🖥️ User Interfaces & Observability

Monika provides dual observability interfaces designed for clear situational awareness: a Web Dashboard and a Terminal UI (TUI).

> [!TIP]
> All telemetry readings, account balances, and win-rate statistics shown in the screenshots below represent paper-trading simulations and diagnostic verification sessions.

### 1. Web Dashboard (React 19)
Built with React 19, Vite, and Tailwind CSS, the Web Dashboard organizes complex quantitative telemetry into a structured workspace with clear visual controls and real-time monitoring.

<p align="center">
  <img src="docs/images/01_trading_desk_overview.png" alt="Monika Trading Desk Overview" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **Trading Desk Overview:** Real-time portfolio equity curves, open MT5 execution tickets, and factor dispatch feeds.
- **Signals & Triggers Matrix:** Latency benchmarks, pending conditional triggers, and execution history.
- **Live Market Data:** Streaming MT5 quotes, VIX volatility regime gauges, and upcoming economic calendar events.

<p align="center">
  <img src="docs/images/04_market_intelligence_pipeline_dag.png" alt="LangGraph Pipeline DAG" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- **LangGraph State DAG:** Live visual inspection of the multi-agent decision graph, showing node latencies, input/output payloads, and transition states.
- **Hard Risk Limits Panel:** Analog-style VU meters tracking current daily drawdown against maximum loss ceilings.
- **Token Economics Audit:** Granular tracking of prompt and completion tokens, model routing, and prompt cache hit rates (~70–80% efficiency).
- **Telegraph HITL Desk:** Human-In-The-Loop console allowing operators to chat with the agent, review trade rationales, and manually authorize or reject proposed orders.

---

### 2. Terminal UI (TUI)
For lightweight server environments, Linux VPS deployments, or SSH sessions without desktop overhead:

<p align="center">
  <img src="docs/images/10_terminal_ui_tui.png" alt="Terminal UI (TUI)" width="100%" style="border-radius: 8px; border: 1px solid #334155;" />
</p>

- Runs directly inside standard terminal emulators.
- Dynamic ASCII sparkline charts for equity trajectories.
- Keyboard-driven navigation (`Tab`, `1-4`, `q`) and integrated command-line controls.

---

## 🏗️ High-Level System Architecture

```mermaid
flowchart TD
    subgraph DataIngestion ["1. Data Ingestion & Preprocessing"]
        MT5_Data[MetaTrader 5 Ticks & Bars] --> DataAggregator[Data Aggregator]
        MacroFeeds[FRED API / Yield Curves] --> DataAggregator
        NewsRSS[Central Bank Feeds & News RSS] --> DataAggregator
        DataAggregator --> SMC[SMC Microstructure Engine<br/>BOS / CHoCH / FVG / Liquidity]
        DataAggregator --> TimesFM[Google TimesFM 3.0<br/>Quantile Volatility Envelopes]
    end

    subgraph LangGraphPipeline ["2. Cognitive Multi-Agent Pipeline"]
        SMC --> S1[Stage 1: Macro Ingestion & Narrative]
        TimesFM --> S1
        S1 --> S2[Stage 2: Tactical Asset Synthesis]
        S2 --> Bull[Bull Specialist Agent]
        S2 --> Bear[Bear Specialist Agent]
        Bull <--> Debate[Dialectical Adversarial Debate]
        Bear <--> Debate
        Debate --> Judge[Investment Arbitration Judge]
    end

    subgraph RiskGateFortress ["3. Deterministic Safety Fortress"]
        Judge --> RawProposal[Structured Trade Proposal]
        RawProposal --> RiskGate{Mechanical RiskGate<br/>10-Layer Invariant Filter}
        RiskGate -- Breach --> Rejected[Proposal Rejected & Audited]
        RiskGate -- Approved --> Sizer[Deterministic Volatility Sizer]
    end

    subgraph ExecutionLayer ["4. Dual Broker Bridge"]
        Sizer --> Dispatcher[Execution Service]
        Dispatcher --> MT5_IPC[Python-MT5 Native Client]
        Dispatcher --> EA_Bridge[MQL5 EA Dead-Man Switch]
        MT5_IPC --> Broker[(Broker Order Book)]
        EA_Bridge --> Broker
    end

    subgraph ObservabilityLayer ["5. Observability & Interfaces"]
        Broker --> Postgres[(PostgreSQL 16+ Database)]
        Postgres --> FastAPI[FastAPI Backend]
        FastAPI --> WebDash[React 19 Web Dashboard]
        FastAPI --> TUI[Terminal UI (TUI)]
        FastAPI --> TeleBot[Telegram Bot & Omnichannel Gateway]
    end
```

---

## 🛡️ Core Safety & Architectural Principles

### 1. "AI Proposes, Mechanical Fortress Disposes"
AI agents generate analytical hypotheses, but they possess **zero direct authority** to execute trades. Every trade proposal must clear an immutable, deterministic `RiskGate` that verifies:
- Daily drawdown budget limits (realized + floating).
- Volatility-adjusted lot sizing (maximum risk per trade strictly capped).
- Maximum concurrent open position count (default: 5).
- High-impact economic news window proximity ($\pm 15$ minutes).
- Cross-asset portfolio correlation thresholds.
- Spread expansion filters and weekend gap risk quarantines.

### 2. MQL5 Expert Advisor Dead-Man's Switch
To guard against Python runtime crashes, operating system freezes, or network dropouts, an independent Expert Advisor (`AIAgent_EA.mq5`) runs directly inside the MetaTrader 5 terminal. The EA monitors a local heartbeat file updated continuously by Monika. If the heartbeat stops refreshing for longer than the tolerance window (default: 120s), the EA automatically intervenes to protect active capital.

### 3. Mandatory Paper Trading Graduation Gate
Monika boots in paper trading mode by default (`paper_trading.enabled: true`). The system strictly enforces an incubation requirement of at least **50 validated paper trades** with an overall win rate $\ge 55\%$ before live broker order routing can be unlocked.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Operating System:** Windows 10/11 or Windows Server (required for native MT5 Terminal execution; Linux VPS supported via Wine / Docker bridge).
- **Python:** `3.11` or higher.
- **Node.js:** `18.0` or higher and `npm` (for the React Dashboard).
- **PostgreSQL:** `16.0` or higher.
- **MetaTrader 5:** Desktop Terminal installed with an active broker account (Demo recommended).

---

### 2. Installation

```bash
# Clone the repository
git clone https://github.com/alakbarr/Monika.git
cd Monika

# Create and activate Python virtual environment
# On Windows:
python -m venv venv
venv\Scripts\activate

# On Linux / macOS:
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r trading-agent/requirements.txt

# Build the Web Dashboard
cd trading-agent/logging_observability/dashboard/frontend
npm install
npm run build
cd ../../../..
```

---

### 3. Configuration

Copy the example environment configuration:
```bash
cp .env.example .env
```

Open `.env` in a secure editor and provide your credentials. Alternatively, run our interactive setup wizard:
```bash
python trading-agent/cli/main.py setup
```

Key environment settings include:
```ini
# Database & MetaTrader 5 (Required)
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/monika_trading
MT5_ACCOUNT=12345678
MT5_PASSWORD=your_mt5_password
MT5_SERVER=YourBroker-Demo
MT5_PATH=C:/Program Files/MetaTrader 5/terminal64.exe

# LLM Providers (At least one required; multi-provider supported)
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEYS=key1,key2
OPENROUTER_API_KEYS=sk-or-...

# Supervision & Observability (Recommended)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_ADMIN_CHAT_ID=987654321
```

> [!CAUTION]
> **Never commit your `.env` file or broker passwords to version control.** Keep your live credentials isolated at all times.

---

### 4. Running Monika

#### Windows Startup Script (Recommended)
Launches the agent daemon, web dashboard, and gateway in separate terminal tabs:
```cmd
trading-agent\start_agent.bat
```

#### Linux / macOS Startup
```bash
bash trading-agent/start_agent.sh
```

#### Terminal UI (TUI)
To monitor running telemetry directly from your terminal:
```bash
python trading-agent/cli/main.py tui
```

#### Running via Docker Compose
To launch PostgreSQL and the background environment in Docker:
```bash
docker compose up -d
```

---

## 🕹️ CLI Command Reference

Monika features a comprehensive CLI suite (`trading-agent/cli/main.py`):

| Command | Action |
| :--- | :--- |
| `python -m cli.main run` | Launch the autonomous trading agent daemon. |
| `python -m cli.main status` | Check system health, uptime, and active task states. |
| `python -m cli.main positions` | List open MT5 tickets, floating PnL, and active stops. |
| `python -m cli.main analyze [SYMBOL]` | Run an immediate on-demand analysis cycle for a given asset. |
| `python -m cli.main chat` | Start an interactive terminal chat session with the agent. |
| `python -m cli.main doctor` | Perform pre-flight environment diagnostics and health checks. |
| `python -m cli.main setup` | Run the interactive terminal setup wizard. |
| `python -m cli.main pause` | Temporarily halt automated order intake. |
| `python -m cli.main resume` | Resume automated order intake. |
| `python -m cli.main kill` | Emergency circuit breaker: close all positions and halt. |
| `python -m cli.main tui` | Open the full-screen Terminal UI (TUI). |

---

## 📱 Telegram Remote Bot Commands

| Command | Role | Description |
| :--- | :--- | :--- |
| `/status` | Public | View system health, open positions, and risk metrics. |
| `/positions` | Public | List active tickets, lot sizes, and floating PnL. |
| `/brief` | Public | Display the latest Stage 1 macroeconomic synthesis brief. |
| `/risk` | Public | View active drawdown gauges and circuit breaker states. |
| `/vix` | Public | Check current VIX volatility reading and regime status. |
| `/tokens` | Public | Inspect LLM token consumption and cache hit rates. |
| `/pause` | Admin | Pause automated trade intake. |
| `/resume` | Admin | Resume automated trade intake. |
| `/kill` | Admin | **Emergency Circuit Breaker:** Liquidate active positions and halt. |
| `/help` | Public | Show all available interactive commands. |

---

## 🧪 Testing & Verification

We enforce continuous test coverage across risk calculations, market structure detection, debate arbitration, and broker bridges:

```bash
# Run complete test suite (PowerShell):
$env:PYTHONPATH="trading-agent"; python -m pytest trading-agent/tests -v

# Run complete test suite (Linux/macOS):
PYTHONPATH=trading-agent pytest trading-agent/tests -v

# Run targeted risk gate validation:
PYTHONPATH=trading-agent pytest trading-agent/tests/risk/test_risk_gate.py -v
```

---

## 📂 Repository Structure

```
Monika/
├── PRD.md                     # Project Requirements Document (Comprehensive Spec)
├── README.md                  # System overview, quickstart, and interfaces
├── DESIGN.md                  # Web Dashboard design specifications
├── CONTRIBUTING.md            # Guidelines for open-source contributions
├── CODE_OF_CONDUCT.md         # Community code of conduct
├── SECURITY.md                # Security policy and vulnerability disclosure
├── INDEX.md                   # Exhaustive codebase index with line citations
├── STRUCTURE.md               # Directory inventory and file tree
├── deploy/                    # Linux VPS deployment assets (Wine, Docker, guides)
├── docs/                      # Screenshots, architecture diagrams, assets
├── scripts/                   # Migration, benchmark, and administrative scripts
└── trading-agent/             # Core application codebase
    ├── main.py                # Top-level orchestrator & asyncio runtime
    ├── agent/                 # Lifecycle managers, health monitors, watchdogs
    ├── analysis/              # Multi-agent debate, SMC calculators, prompt templates
    ├── backtest/              # Point-in-time, walk-forward, and Monte Carlo backtesting
    ├── benchmark/             # Alpha Arena, model registry, prompt evolution
    ├── cli/                   # Terminal UI (TUI) and CLI subcommands
    ├── config/                # settings.yaml, schema validators, hot-reload engine
    ├── database/              # SQLAlchemy 2.0 async models, migrations, advisory locks
    ├── evals/                 # Hostile market scenario probes & simulation clocks
    ├── execution/             # Native MT5 client, MQL5 EA bridge, execution service
    ├── gateway/               # Omnichannel router (Telegram, Discord, Slack, ACP)
    ├── graph/                 # LangGraph state machine node implementations
    ├── harness/               # Universal plugin engine, lifecycle & event bus
    ├── indicators/            # Classical indicators, SMC structures, Google TimesFM 3.0
    ├── logging_observability/ # Structured activity logs, Prometheus, React 19 Web Dashboard
    ├── risk/                  # Deterministic RiskGate, sizing, circuit breakers
    ├── scheduler/             # Background task loops (news, triggers, cycles, guardians)
    ├── skills/                # Unified skills runtime & continuous learning playbooks
    └── telegram_bot/          # Telegram bot handler & interactive keyboards
```

---

## ⚠️ Known Limitations

1. **MetaTrader 5 Native Reliance:** The native `MetaTrader5` Python package requires a Windows environment with an active MT5 Desktop Terminal. Linux server deployments require Wine or network RPC containers.
2. **PostgreSQL Mandatory:** SQLite is disallowed due to async concurrency, advisory locking, and partial unique index requirements.
3. **LLM Latency & Operational Costs:** Dialectical multi-agent debate requires multiple API inference turns. A full analysis cycle takes between 15 and 45 seconds, making this architecture unsuitable for sub-second High-Frequency Trading (HFT). Active execution also incurs LLM token usage costs across providers.
4. **Early-Stage Codebase:** As an exploratory prototype under active development, edge cases and unexpected behaviors can occur. Testing on demo accounts is strictly mandatory.

---

## 🤝 Contributing & Community Collaboration

Monika is an open-source initiative, and we believe that resilient trading software is built through open collaboration, thorough testing, and community feedback.

- **Found a bug or calculation error?** Please submit a detailed [GitHub Issue](https://github.com/alakbarr/Monika/issues).
- **Have architectural suggestions?** Share your thoughts in [GitHub Discussions](https://github.com/alakbarr/Monika/discussions).
- **Want to contribute code?** Check out our [Contributing Guidelines](CONTRIBUTING.md) and submit a pull request!

---

## 📜 Financial & Research Disclaimer

> [!WARNING]
> **FOR RESEARCH AND EDUCATIONAL PURPOSES ONLY.**
>
> Algorithmic trading and financial market speculation involve significant risk of monetary loss. The developers, authors, and contributors of this software provide no guarantees, warranties, or representations regarding profitability, performance, or financial outcomes. Never trade with money you cannot afford to lose. Always thoroughly validate any trading system on demo accounts under paper trading conditions before committing real capital.

---

<p align="center">
  <sub>Monika Quantitative Trading Agent Harness &bull; Built with LangGraph, FastAPI, and MetaTrader 5</sub>
</p>
