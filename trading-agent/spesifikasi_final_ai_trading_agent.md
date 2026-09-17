# System Architecture & Master Specification: Monika AI Trading Platform
### Autonomous High-Performance Algorithmic Trading Platform: Hybrid Multi-Provider LLM & Quantitative Engine

> **Document Status**: *Living Master Specification (Single Source of Truth)*  
> **System Release**: v1.0.0 (Institutional Multi-Provider & Hybrid Quant-LLM Production Architecture)  
> **Execution Gateway**: MetaTrader 5 (MT5 Terminal via MetaTrader5 Python API + MQL5 EA Bridge)  
> **Persistence Layer**: PostgreSQL 16+ (Async SQLAlchemy 2.0 + Asyncpg + Alembic Migrations)  
> **Cognitive Orchestration**: LangGraph StateGraph + Multi-Agent Dialectical Debate + Multi-Provider LLM Fabric (OpenRouter, Gemini, Groq, Anthropic, OpenAI, DeepSeek, Ollama)

---

## 0. Document Usage & System Governance

This document serves as the technical **Single Source of Truth (SSOT)** for the entire Monika AI Trading Agent ecosystem. It is the primary authoritative reference for software engineers and AI coding assistants prior to architectural design, feature implementation, debugging, or modifying codebase components.

### Operational Philosophy & Decision Hierarchy
1. **Rule-Based Determinism as Supreme Authority**:
   Financial order dispatch, modification, and liquidation decisions are never fully delegated to probabilistic LLMs. AI models act strictly as structured hypothesis generators and multi-perspective market analysts; deterministic backend modules (`RiskGate`, `PositionSizer`, `SignalArbitrator`) hold absolute veto authority.
2. **Hybrid Quantitative & Cognitive Synthesis**:
   Signals originating from deterministic quantitative strategies (`EdgeStrategyRunner`) and synthesized cognitive reasoning outputs (`GraphCycleScheduler`) are reconciled concurrently via `SignalArbitrator`.
3. **Paper Trading Accumulation Gate vs. Live Mode**:
   The platform strictly mandates the accumulation of at least **50 paper trades** with a minimum win rate of **55%** before live execution (`auto_execute: true`) can be unlocked. Startup verification enforces a *Hard Safety Gate* that immediately aborts execution if these empirical performance criteria are unmet while `--dry-run` is disabled.

---

## 1. Non-Negotiable Core Principles & Financial Safety Doctrine

The following core principles are absolute and cannot be bypassed under any operational circumstance:

1. **"AI Proposes, Backend Disposes" (Fail-Closed Architecture)**:
   The LLM generates a structured proposal (`SubmitAssetAnalysisSchema`) containing directional bias (`buy`/`sell`/`wait`/`avoid`), entry zone, stop loss, and take profit levels. This proposal must pass exhaustive deterministic mathematical filters (`RiskGate`) before conversion into an `MT5Signal` or broker order.
2. **Mandatory Backend Deterministic Calculations**:
   All technical indicators (ATR, Moving Averages, RSI, MACD, Pivot Points, ADR), lot sizing formulas, and structural market zones (Fair Value Gaps, Order Blocks, Liquidity Sweeps) are computed exclusively by deterministic Python modules or `pandas-ta`. LLMs are strictly forbidden from calculating lot sizing or pips distances from prompt text.
3. **Exhaustive Auditability & Non-Volatile Persistence**:
   Every tool execution, token expenditure, prompt payload, Bull/Bear debate argument, judicial verdict, and broker execution ticket is committed to PostgreSQL (`activity_log`, `token_usage_logs`, `decision_reflections`, `candidate_lessons`).
4. **Independent Multi-Tier Kill Switch System**:
   - *Tier 1 (Manual via Telegram / CLI)*: `/kill` or `/pause` commands halt active trading operations immediately.
   - *Tier 2 (Drawdown Hysteresis Circuit Breaker)*: Floating drawdown monitors trigger an automated emergency shutdown if daily drawdown breaches the tolerance threshold (3.0%) across two consecutive checks.
   - *Tier 3 (Flash Crash Circuit Breaker)*: Extreme volatility detectors (ATR multiple $\ge 5.0$ or price movement exceeding threshold) immediately shift active stops to breakeven and quarantine the symbol for 30 minutes.
   - *Tier 4 (Server-Side EA Dead-Man's Switch)*: The Expert Advisor (`AIAgent_EA.mq5`) on the MT5 terminal continuously inspects `heartbeat.txt`. If the Python process fails to refresh the timestamp within the tolerance window (default 120 seconds), the EA autonomously closes active open positions or freezes order intake.
5. **Graceful Degradation (Fail-Safe Default)**:
   Data feed dropouts, provider quota exhaustion, or broker connection disconnects always resolve to a `NO TRADE` / `WAIT` state rather than speculative guessing.
6. **Concurrency Integrity & Race Condition Prevention**:
   Order dispatch workflows are protected via *PostgreSQL Transactional Advisory Locks*, real-time open position double-verification (`_count_open_positions`), and partial unique database indices to preclude duplicate order dispatch.

---

## 2. End-to-End System Architecture & Master Orchestration

The Monika AI Trading platform orchestrates **18+ concurrent asynchronous background tasks** running inside a unified asyncio event loop (`TradingAgent` in `main.py`):

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                MONIKA AI TRADING AGENT MAIN                                 │
│                                                                                             │
│  ┌──────────────────────┐   ┌──────────────────────┐   ┌─────────────────────────────────┐  │
│  │ GraphCycleScheduler  │   │     NewsWatcher      │   │       ActiveCalendarPoller      │  │
│  │ (8-Hour Cycle + Ssn) │   │ (Breaking News 5-min)│   │ (Sub-Minute Economic Releases)  │  │
│  └──────────┬───────────┘   └──────────┬───────────┘   └────────────────┬────────────────┘  │
│             │                          │                                │                   │
│             │               ┌──────────▼───────────┐                    │                   │
│             │               │ PostReleaseAnalyzer  │                    │                   │
│             │               │ (15m Post-Release)   │                    │                   │
│             │               └──────────┬───────────┘                    │                   │
│             │                          │                                │                   │
│             └──────────────────────────┼────────────────────────────────┘                   │
│                                        │                                                    │
│                             ┌──────────▼──────────┐                                         │
│                             │   TriggerChecker    │ (Condition & Invalidation Eval 2-min)   │
│                             └──────────┬──────────┘                                         │
│                                        │                                                    │
│ ┌──────────────────────┐    ┌──────────▼──────────┐    ┌─────────────────────────────────┐  │
│ │  EdgeStrategyRunner  │───►│   SignalArbitrator  │◄───┤       TimesFMEngine (ML 3.0)    │  │
│ │ (6 Quant Strategies) │    │ (Quant vs AI Arb)   │    │(Probabilistic Quantile Forecast)│  │
│ └──────────────────────┘    └──────────┬──────────┘    └─────────────────────────────────┘  │
│                                        │                                                    │
│                             ┌──────────▼──────────┐                                         │
│                             │       RiskGate      │ (10-Layer Deterministic Risk Filter)    │
│                             └──────────┬──────────┘                                         │
│                                        │                                                    │
│                             ┌──────────▼──────────┐                                         │
│                             │   ExecutionService  │ (Idempotency, Paired-Legs, Sizing)      │
│                             └──────────┬──────────┘                                         │
│                                        │                                                    │
│                 ┌──────────────────────┴──────────────────────┐                             │
│                 ▼                                             ▼                             │
│      ┌─────────────────────┐                       ┌─────────────────────┐                  │
│      │      MT5Client      │                       │  AIAgent_EA Bridge  │                  │
│      │ (Windows Native Lib)│                       │ (Dead-Man's Switch) │                  │
│      └─────────────────────┘                       └─────────────────────┘                  │
│                                                                                             │
│  CONCURRENT MONITORS & GUARDIANS:                                                           │
│  ├── FlashCrashDetector (30s)          ├── FloatingDrawdownMonitor (30s Hysteresis)         │
│  ├── PositionGuardian (News/Weekend)   ├── TrailingStopManager (ATR Trail & Breakeven)      │
│  ├── PositionExitReviewer (AI Review)  ├── PaperTradeMonitor & WhatIfResolver (5m)          │
│  ├── MarketDataScheduler (Auto-Heal)   ├── ScraperLoop & NewsDigestProcessor (1h)           │
│  ├── MT5HealthMonitor (60s Reconnect)  ├── DBHealthCheck (Pool SELECT 1 5m)                 │
│  ├── NotifierOutboxFlusher             ├── TelegramBot (Polling & Interactive Keyboards)    │
│  └── FastAPI Dashboard (REST)          └── Vite/React Frontend Observability Dashboard      │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Balanced Startup Sequence (Startup Health Checks)
1. Structured logging initialization to console and rotating files (`logs/`).
2. Unified configuration loading (`config/settings.yaml`, `MACRO_REALITY.md`, `TRADING_SOUL.md`).
3. Single-instance process lock via `trading_agent.pid` to prevent overlapping instances.
4. Static verification of declared `task_roles` against invocations in the codebase.
5. PostgreSQL connection pool initialization and schema validation across critical tables (35+ tables).
6. AI budget tracking synchronization (MTD cost, daily budget limits).
7. API credentials validation and ping testing across all configured providers (OpenRouter, Gemini, Groq, Ollama).
8. Validation of tool handler registrations (50+ tools) within `ToolExecutor`.
9. MetaTrader 5 connectivity verification and asset symbol discovery (including Brent crude `XBRUSD`).
10. Paper trading validation gate (aborts live mode if historical accumulation requirements are unmet).

### 2.2 Post-Restart Recovery Protocol (`_post_restart_recovery`)
Following an engine restart (system reboot or deployment cycle), the platform executes a deterministic recovery sequence:
1. Restores executed analysis identifiers from the database (`_restore_executed_ids_from_db`).
2. Awaits stable MT5 connectivity (120-second timeout); transitions to `degraded_mode` upon failure.
3. Synchronizes active broker positions from MT5 into the relational `positions` table (3 retry attempts).
4. Enforces weekend closure protection (Friday close check when UTC time exceeds 20:00).
5. Synchronizes market data and executes instant indicator warmup across the instrument universe.
6. Sets the `_recovery_complete` event to notify background schedulers that the platform is operational.
7. Evaluates cycle drift (harmonized catch-up logic): if the last cycle exceeds cadence thresholds or the Fundamental Brief has expired, triggers an immediate catch-up cycle.
8. Verifies news digest freshness (initiates an immediate refresh if older than 4 hours).
9. Emits a recovery completion operational notification to the administrative Telegram channel.

### 2.3 Graceful Shutdown Protocol
Upon receiving SIGINT (Ctrl+C) or SIGTERM signals:
1. Persists an instantaneous snapshot of active positions to `data/last_shutdown_snapshot.json`.
2. Emits an emergency Telegram notification if shutdown occurs with live positions open.
3. Systematically terminates all background schedulers and guardian tasks.
4. Closes the MT5 client connection cleanly (5-second grace period).
5. Closes the PostgreSQL async connection pool.
6. Cancels Telegram bot tasks and releases the PID file lock.

---

## 3. Directory Structure & Module Decomposition

The codebase enforces strict Separation of Concerns (SoC):

```
trading-agent/
├── main.py                               # Top-level orchestrator & bootstrap runtime
├── config/
│   ├── settings.py                       # YAML configuration loader & schema validator
│   ├── settings.yaml                     # Master configuration (1890+ lines)
│   ├── MACRO_REALITY.md                  # Verified macroeconomic baseline (Layer 1 Memory)
│   └── TRADING_SOUL.md                   # Core system philosophy & risk identity (Layer 0 Memory)
├── analysis/                             # Cognitive & quantitative analysis pipeline
│   ├── arbitration/
│   │   └── signal_arbitrator.py          # Quant vs LLM Debate signal reconciliation
│   ├── calculators/                      # Deterministic technical & structural calculators
│   │   ├── confluence_calculator.py      # Confluence scorecard generator
│   │   ├── daily_range_calculator.py     # ADR intraday range context
│   │   ├── economic_surprise.py          # Actual vs forecast deviation calculator
│   │   ├── intraday_level_optimizer.py   # Optimal structural entry points via liquidity
│   │   ├── liquidity_sweep_detector.py   # Asian session liquidity sweep detector
│   │   ├── macro_priced_in_calculator.py # Baseline priced-in rate expectations
│   │   ├── regime_classifier.py          # Market regime classification (trending vs consolidation)
│   │   └── volume_profile.py             # Volume profile Value Area (VAH, VAL, POC) & VWAP
│   ├── debate/                           # Multi-agent dialectical debate system
│   │   ├── bull_analyst.py               # Long thesis advocate (Bull thesis)
│   │   ├── bear_analyst.py               # Short thesis advocate (Bear dissent)
│   │   ├── investment_judge.py           # Impartial debate adjudicator
│   │   ├── macro_bull_analyst.py         # Optimistic macroeconomic specialist
│   │   ├── macro_bear_analyst.py         # Pessimistic macroeconomic specialist
│   │   ├── macro_judge.py                # Macro adjudicator
│   │   └── portfolio_manager.py          # Portfolio decisions & cross-pair risk balance
│   ├── memory/                           # Persistent memory subsystem & empirical learning
│   │   ├── chronicle_writer.py           # Structural macro chronicle logger (Layer 2)
│   │   ├── layered_memory.py             # 4-tier memory manager
│   │   ├── outcome_linker.py             # Links trading decisions to real PnL outcomes
│   │   ├── reflector.py                  # Post-trade AI reflector & lesson extractor
│   │   ├── session_search.py             # Historical precedent search engine in PostgreSQL
│   │   └── lesson_consolidator.py        # Consolidates validated lessons into markdown playbooks
│   ├── prefetch/                         # Token-optimized data bundling & preprocessing
│   │   ├── digest_slice_generator.py     # Rolling 2-hour news snapshot generator
│   │   ├── news_digest.py                # Thematic news compressor & calendar grounding
│   │   ├── stage1_prefetcher.py          # Stage 1 Macro Fundamental data bundler
│   │   └── stage2_prefetcher.py          # Stage 2 Per-Asset data bundler
│   ├── providers/                        # Unified multi-LLM provider fabric
│   │   ├── base_provider.py              # Base interface & anti-oscillation tool guard
│   │   ├── llm_factory.py                # Client factory & 8-tier fallback wrapper
│   │   ├── anthropic_provider.py         # Claude Direct API driver
│   │   ├── gemini_provider.py            # Google Gemini API driver (Thinking & Free tiers)
│   │   ├── groq_provider.py              # Groq API driver (High-speed inference)
│   │   ├── openrouter_provider.py        # OpenRouter API driver (Paid/Free key rotation)
│   │   ├── openai_provider.py            # OpenAI API driver
│   │   └── ollama_provider.py            # Local model driver (Llama 3 / Qwen)
│   ├── schemas/                          # Pydantic data contracts & JSON schemas
│   │   └── pydantic_schemas.py           # FundamentalBriefSchema, SubmitAssetAnalysisSchema, etc.
│   ├── stages/                           # Primary analysis stages
│   │   ├── fundamental_stage.py          # Stage 1: Global Macro Fundamentals
│   │   └── per_asset_stage.py            # Stage 2: Per-Asset Analysis + Multi-Agent Debate
│   ├── strategies/                       # Deterministic quantitative strategies (Non-LLM)
│   │   ├── base_strategy.py              # Base quantitative strategy interface
│   │   ├── gap_fade.py                   # Market open gap fade strategy
│   │   ├── btc_donchian_breakout.py      # BTC Donchian breakout with volume z-score
│   │   ├── tsm_momentum.py               # Multi-lookback Time-Series Momentum
│   │   ├── xau_trend_engine.py           # Gold trend engine (EMA fast/slow + Donchian)
│   │   ├── xti_pairs_readiness.py        # Statistical Arbitrage dual-leg WTI vs Brent
│   │   └── liquidity_sweep_edge.py       # Asian session liquidity sweep + ChoCH
│   ├── tools/                            # System tool execution & registration
│   │   ├── tool_executor.py              # Dispatcher for 50+ tools with schema validation
│   │   ├── tool_registry.py              # Progressive Tool Registry (Dynamic categories)
│   │   ├── tools_definitions.py          # JSON tool declarations for LLM function calling
│   │   ├── composite_tools.py            # Single-turn composite tools for token savings
│   │   └── domain/                       # Domain-specific functional tool handlers
│   └── validators/                       # Guardrails & mathematical snapping
│       ├── core_data_validator.py        # Price data freshness & calendar validation
│       ├── confluence_verifier.py        # Independent confluence score verifier
│       ├── adversarial_check.py          # Confirmation bias & worst-case scenario stress tester
│       └── output_verifier.py            # Deterministic snapping & parameter adjustments
├── database/                             # PostgreSQL persistence & async ORM
│   ├── db.py                             # Asyncpg engine, session pool & advisory locks
│   ├── models.py                         # 35+ SQLAlchemy 2.0 ORM models
│   ├── adapters.py                       # Data adapter converters between scrapers & models
│   ├── safe_ops.py                       # Atomic transaction operations with rollback
│   └── migrations/                       # Alembic migration revisions
├── execution/                            # Broker connectivity & order execution
│   ├── mt5_client.py                     # Asynchronous MetaTrader 5 Python SDK wrapper
│   ├── execution_service.py              # Execution service, idempotency & paired legs
│   └── ea_bridge/
│       ├── AIAgent_EA.mq5                # MQL5 Expert Advisor for broker-side safety
│       └── heartbeat_writer.py           # Heartbeat writer targeting MT5 Common Files directory
├── graph/                                # LangGraph workflow orchestration
│   ├── state.py                          # TypedDict states & recursive reducers
│   ├── workflow.py                       # StateGraph compiler & transition routes
│   └── nodes/                            # Independent graph execution nodes
├── indicators/                           # Technical computing & machine learning
│   ├── technical.py                      # Classical indicators (MA, RSI, MACD, BB)
│   ├── structure.py                      # Market structure (Swings, S/R, Liquidity, FVG, ChoCH)
│   └── timesfm_engine.py                 # Google TimesFM 3.0 PyTorch Quantile Forecast Engine
├── logging_observability/                # Logging, metrics & user interfaces
│   ├── activity_logger.py                # Structured database logger & rotating log files
│   ├── metrics_exporter.py               # In-memory Prometheus metric collector
│   └── dashboard/
│       ├── api.py                        # FastAPI REST backend (15+ endpoints)
│       └── frontend/                     # Web dashboard (React 18, TypeScript, Vite, Tailwind)
├── risk/                                 # Institutional risk management
│   ├── position_sizing.py                # Deterministic lot calculation per instrument
│   ├── risk_gate.py                      # 10-layer risk verification gate
│   └── portfolio_correlation_gate.py     # Dynamic portfolio correlation filter (EWMA)
├── scheduler/                            # Schedulers, pollers & autonomous guardians
│   ├── graph_cycle_scheduler.py          # 8-hour LangGraph analysis cycle scheduler
│   ├── news_watcher.py                   # Lightweight breaking news monitor (5 minutes)
│   ├── active_calendar_poller.py         # Sub-minute economic release poller
│   ├── post_release_analyzer.py          # Post-release news impact analyzer (15-min settlement)
│   ├── trigger_checker.py                # Trade trigger & invalidation monitor (2 minutes)
│   ├── flash_crash_detector.py           # Extreme volatility circuit breaker (30 seconds)
│   ├── position_guardian.py              # High-impact news & weekend risk guardian
│   ├── position_exit_reviewer.py         # Autonomous AI review of active open positions
│   ├── trailing_stop_manager.py          # Dynamic ATR-based trailing stop & breakeven manager
│   ├── edge_strategy_runner.py           # Independent runner for quantitative strategies (60s)
│   ├── market_data_scheduler.py          # Market data synchronization & auto-healing
│   └── digest_slice_scheduler.py         # Rolling 2-hour news digest slice generator
├── scrapers/                             # Headless scrapers & structured RSS feeds
│   ├── base_scraper.py                   # Base scraper with anti-bot protection & retries
│   ├── calendar/                         # ForexFactory, Investing.com, Finnhub
│   ├── macro/                            # CME FedWatch
│   ├── news/                             # Kitco, TradingView, RSS feeds from 5 Central Banks & Portals
│   ├── sentiment/                        # FXSSI, MyFxBook, Binance Long/Short
│   └── social/                           # Social / macro sentiment feeds
├── telegram_bot/                         # Operational Telegram interface
│   ├── bot.py                            # Telegram bot with inline keyboard support
│   ├── chat_agent.py                     # Natural language operational chat agent
│   ├── chat_tool_router.py               # Token-efficient tool router for chat interactions
│   └── command_router.py                 # Deterministic command router (/status, /positions, etc.)
└── utils/                                # 40+ modular technical utilities
    ├── analytics/                        # Win rate, cost tracking & empirical edge evaluation
    ├── calibration/                      # Confluence calibration & drift detection
    ├── llm/                              # Token compression, prompt caching & context compaction
    ├── market/                           # Market session hours, dynamic correlation, USD strength
    └── infra/                            # Notifiers, database backups, Windows event loop policy
```

---

## 4. Data Feed, Ingestion & Preprocessing Layers

Data integrity is the foundational bedrock of the trading system. The architecture prioritizes official programmatic APIs and structured RSS feeds before falling back to browser automation:

### 4.1 Programmatic APIs & Quantitative Feeds
- **Federal Reserve Economic Data (FRED API)**: US sovereign bond yields (2Y, 5Y, 10Y, 30Y, 10Y Real Yield, 10Y Breakeven Inflation) and benchmark policy rates from the Fed, ECB, BOE, and BOJ.
- **CFTC Public Reporting Environment (Socrata API)**: Weekly Disaggregated *Commitment of Traders (COT)* reports (Dealer, Asset Manager, Leveraged Funds) covering XAU, WTI, EUR, GBP, JPY, and AUD.
- **Yahoo Finance API**: Daily closing series for the Cboe Volatility Index (VIX), US Dollar Index (DXY), and Brent Crude Oil (`BRENT` / `BZ=F`).
- **Coinglass / Binance Futures / Bybit API**: Bitcoin perpetual swap funding rates to assess cryptocurrency leverage sentiment.

### 4.2 Central Bank RSS Feeds & Headless Scraping
- **Direct Central Bank RSS Feeds**: Headless, low-overhead RSS feed monitoring for the Bank of Japan (BOJ), Reserve Bank of Australia (RBA), Federal Reserve (Fed), European Central Bank (ECB), and Bank of England (BOE) to capture monetary policy statements instantly.
- **Global Financial News Portals**: Reuters, Financial Times, Bloomberg, WSJ, CNBC, MarketWatch, Dow Jones, FXStreet, ForexLive, Investing.com, CoinDesk.
- **DrissionPage Headless Browser**: Dynamic browser automation with anti-bot challenge bypass for economic calendars (ForexFactory, Investing.com), TradingView news, Kitco Gold, and CME FedWatch.

### 4.3 Active Calendar Poller & Post-Release Event Analyzer
- `ActiveCalendarPoller`: Monitors economic calendars with sub-minute precision. Preceding high-impact macroeconomic releases (CPI, Non-Farm Payrolls, FOMC), this poller engages an aggressive 15-second polling interval to capture actual releases instantly.
- `PostReleaseAnalyzer`: Awaits a 15-minute market settlement window post-release to allow wide broker spreads and whipsaw volatility to normalize. It then computes *economic surprise* metrics (`actual` vs `forecast`) and triggers targeted Stage 2 re-analyses for affected currencies.

### 4.4 Data Bundling, Prefetching & News Digest Compression
To minimize LLM token consumption and eliminate redundant round-trips:
- `NewsDigestProcessor`: Groups raw news items into thematic currency clusters, filters noise, and cross-verifies numerical claims against official economic calendar records.
- `DigestSliceScheduler`: Periodically generates rolling 2-hour currency snapshots (`NewsDigestSlice`) in PostgreSQL, allowing Stage 1 to consume information-dense 12-hour macro summaries without parsing hundreds of raw article feeds.

---

## 5. Quantitative Computing & Machine Learning Engines (Non-LLM)

The platform operates deterministic quantitative engines and deep learning foundation models that execute independently before LLM invocation:

### 5.1 Technical Indicators & Market Structure Engine
Computed directly from MT5 tick and OHLCV candle feeds across multiple timeframes (M15, H1, H4, D1):
- **Classical Indicators**: Moving Averages (EMA 20, SMA 50, SMA 200), RSI (14), Stochastic (14, 3, 3), MACD (12, 26, 9), Bollinger Bands (20, 2), Average Daily Range (ADR 5-day & 20-day).
- **Smart Money Concepts (SMC) & ICT Market Structure**:
  - Fractal Swing High and Swing Low detection.
  - Historical Support & Resistance zone clustering based on price touch density.
  - Liquidity Zone mapping (Buy-side & Sell-side liquidity pools above/below swing pivots).
  - Fair Value Gap (FVG) identification (bullish/bearish) with mitigation tracking (*unfilled*, *partially filled*, *mitigated*).
  - Institutional Order Block (OB) identification and structural transition confirmation (Break of Structure / Change of Character - ChoCH).
  - Volume Profile & VWAP: Computes Value Area High (VAH), Value Area Low (VAL), and Point of Control (POC) over recent 30-bar rolling horizons.

### 5.2 Google TimesFM 3.0 Deep Learning Forecasting Engine
The `TimesFMEngine` leverages Google's **TimesFM 3.0** PyTorch time-series foundation model (CUDA-optimized with automatic CPU fallback):
- **Context Window**: 512 H1 candle bars (~21 trading days).
- **Forecast Horizon**: 24 steps ahead (24-hour forward projection).
- **Exogenous Multivariate Covariates**: DXY (Dollar Index), US10Y (10-Year Treasury Yield), and XTIUSD (WTI Crude Oil).
- **Probabilistic Quantile Output**: Comprehensive quantile matrix ($q_{0.1}, q_{0.2}, \dots, q_{0.9}$) producing median price trajectory paths, dynamic confidence bands, upper/lower dispersion bounds, and probabilistic expectancy metrics.
- **Architectural Integration**: Serves as an anti-exhaustion momentum validator, volatility trailing stop adjuster, and statistical arbitrage correlation verifier.

### 5.3 Quantitative Edge Strategies Portfolio
Executes autonomously within `EdgeStrategyRunner` on a 60-second polling schedule:
1. `DailyReopenGapFade`: Identifies daily opening gaps relative to prior close across FX and equity index instruments, entering mean-reverting fade positions when gaps exceed pip thresholds with TP set at gap closure.
2. `BTCDonchianBreakout`: Bitcoin trend-following system executing on 20-period Donchian Channel breakouts confirmed by volume z-score expansion ($z \ge 1.5$).
3. `TimeSeriesMomentum` (TSM): Measures absolute momentum across 63, 126, and 252 trading-day lookback windows to determine macro multi-month trend direction.
4. `XAUTrendEngine`: Gold (XAUUSD) trend-following engine combining fast EMA (20) and slow EMA (50) crossovers with Donchian channel envelope confirmation.
5. `XTIPairsReadiness` (Statistical Arbitrage WTI vs. Brent): Tracks cointegration spread and $z\text{-score}$ between WTI Crude Oil (`XTIUSD`) and Brent Crude Oil (`XBRUSD`). When the spread deviates beyond $z = \pm 2.0$, it generates synchronized, notional-weighted *dual-leg* paired orders (Buy XTI / Sell XBR or inverse).
6. `LiquiditySweepStructuralShift`: Monitors Asian session liquidity pools (00:00 - 08:00 UTC). When Asian highs/lows are swept during the London open followed by an M15 Change of Character (ChoCH), a structural reversal order is triggered.

### 5.4 Centralized SignalArbitrator
The `SignalArbitrator` reconciles quantitative signals with cognitive LLM proposals:
- **Concordant (Aligned)**: When quantitative models and LLM consensus agree, confidence receives a boost (+0.05) and risk allocation is scaled up to 1.15x.
- **Discordant (Opposing)**: If a quantitative strategy exhibits high confidence ($\ge 0.75$) under strong trend regimes, quantitative signals take precedence with reduced risk scaling (0.70x).
- **VIX Defensive Shield**: When VIX $\ge 35.0$, all trade proposals running counter to quantitative defensive baselines are automatically blocked.

---

## 6. Cognitive AI Pipeline: LangGraph & Multi-Agent Debate

The cognitive decision-making pipeline is orchestrated via a persistent **LangGraph StateGraph** featuring asynchronous PostgreSQL checkpointing:

```
                  ┌──────────────────────┐
                  │      START NODE      │
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │      Data Node       │ (Prefetch Market, News & Macro Bundles)
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │   Fundamental Node   │ (Stage 1: Macro Regime & Global Bias)
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │    Per-Asset Node    │ (Stage 2: Prescreen & Specialist Decomposition)
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │     Debate Node      │ (Bull vs Bear Dialectic → Judge Adjudication)
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │    Risk Gate Node    │ (Deterministic & AI Portfolio Synthesis)
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │   Reflection Node    │ (Cross-Asset Synergy & VIX Shield Check)
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │    Execution Node    │ (MT5 Placement / Paper Trade Recording)
                  └──────────┬───────────┘
                             │
                  ┌──────────▼───────────┐
                  │       END NODE       │
                  └──────────────────────┘
```

### 6.1 Stage 1: Global Fundamental Macro Regime
- **Model Role**: `stage1_fundamental` (Primary: Gemini 3.7 Flash with extended reasoning budget, backed by 8-tier automated failover).
- **Objective**: Evaluates latest economic releases, US Treasury yield curves, FedWatch implied rate trajectories, COT institutional positioning, DXY trend, and VIX volatility.
- **Structured Output (`FundamentalBriefSchema`)**:
  - `macro_narrative`: Comprehensive synthesis of prevailing macroeconomic forces.
  - `currency_bias`: Directional bias per currency (`USD`, `EUR`, `GBP`, `JPY`, `AUD`, etc.) categorized as `bullish`, `bearish`, or `neutral`.
  - `key_upcoming_risks`: High-impact risk events slated for the upcoming 24-hour window.
  - `risk_sentiment`: Broad market regime classification (`risk-on`, `risk-off`, or `mixed`).
  - `confidence`: Analytical confidence rating (0.0 to 1.0).

### 6.2 Stage 2: Fast Prescreening Filter
Prior to launching token-intensive analytical subagents, a lightweight model (`stage2_prescreen`: Gemini Flash Lite / Claude Haiku) screens technical snapshots and macro alignment for each asset. Assets displaying severe consolidation, erratic chop, or lack of directional catalysts are tagged `SKIP`, reducing cycle compute costs by up to 70%.

### 6.3 Stage 2: Three Specialist Domain Agents
Assets passing prescreening undergo independent evaluation by domain specialists:
1. `specialist_technical`: Focuses on price action, liquidity sweeps, SMC/ICT market structure, and momentum indicators.
2. `specialist_sentiment`: Focuses on retail trader positioning (MyFxBook, FXSSI), perpetual funding rates, and non-commercial COT changes.
3. `specialist_macro`: Focuses on sovereign bond yield differentials, commodity/DXY correlations, and scheduled economic data impacts.

### 6.4 Multi-Agent Dialectical Debate System
Following specialist data synthesis, an adversarial debate arena is convened:
- **Bullish Advocate (`debate_bull`)**: Formulates the strongest evidence-backed long thesis (demand mitigation, sell-side liquidity sweeps, macro tailwinds).
- **Bearish Dissenter (`debate_bear`)**: Aggressively exposes structural vulnerabilities, overhead supply zones, bearish divergences, liquidity traps, and invalidation criteria.
- **Investment Judge (`debate_judge`)**: Impartially evaluates competing arguments against empirical data, adjudicates the winner (`bull` / `bear` / `draw`), and sets the calibrated confidence score.

### 6.5 Synthesis Adjudicator & Scenario Tree Engine
- `stage2_adjudicator`: Synthesizes debate transcripts, confluence scores, and specialist insights into a formalized proposal (`SubmitAssetAnalysisSchema`).
- `ScenarioTreeEngine`: Constructs a 3-branch probabilistic market scenario tree (*Bullish continuation*, *Bearish reversal*, *Consolidation/chop*) with associated Expected Values (EV). Trade signals are only ratified when $EV \ge 1.3$.

### 6.6 Guardrails & Deterministic Snapping (`OutputVerifier`)
Proposed JSON structures are validated deterministically by `OutputVerifier`:
- Enforces strict minimum Risk:Reward ratio compliance ($\ge 1.3$).
- Enforces that Stop Loss distance does not exceed instrument ADR safety ceilings.
- **Deterministic Mathematical Snapping**: If the LLM proposes entry, stop loss, or take profit coordinates drifting several pips from verified swing levels or actual FVG bounds, the backend deterministically snaps them to the nearest valid structural price level in the database.

---

## 7. Multi-Provider LLM Fabric, Dynamic Routing & Token Optimization

The platform does not rely on a single AI provider, utilizing a distributed **Multi-Provider Fabric** architecture:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LLM PROVIDER ROUTING FABRIC                        │
│                                                                             │
│  Task Request ──► LLMFactory.get_client_for_task(role)                      │
│                          │                                                  │
│                          ▼                                                  │
│         ┌─────────────────────────────────┐                                 │
│         │     Settings.yaml Task Roles    │ (30+ Defined Roles)             │
│         └────────────────┬────────────────┘                                 │
│                          │                                                  │
│         ┌────────────────▼────────────────┐                                 │
│         │      FallbackClientWrapper      │                                 │
│         │ (Up to 8-Tier Failover Chains)  │                                 │
│         └────────────────┬────────────────┘                                 │
│                          │                                                  │
│    ┌──────────────┬──────┴──────┬──────────────┬──────────────┬────────┐    │
│    ▼              ▼             ▼              ▼              ▼        ▼    │
│ OpenRouter      Gemini        Groq         Anthropic       OpenAI   Ollama  │
│ (Paid/Free)  (Flash/Pro)   (Compound)    (Direct Claude)  (Direct)  (Local) │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.1 Automated Multi-Provider Key Rotation & Failover
- **OpenRouter**: Features automated separation between *Paid Keys* (commercial models: Claude 3.5 Sonnet, GPT-4o, DeepSeek R1) and *Multi-Key Free Tier* rotation for open models (GLM-4, MiniMax, Qwen 2.5).
- **Google Gemini**: Official `google-genai` integration with multi-key rotation, `thinkingBudget` reasoning depth controls, and automatic backoff upon rate limit or quota exhaustion.
- **Groq**: Ultra-low latency inference for high-speed preprocessing, news classification, and entity extraction.
- **Anthropic**: Native Claude Direct API driver with multi-tier prompt caching support.
- **DeepSeek & OpenAI Compatible**: Local REST endpoint integration (Ollama / vLLM / LM Studio).

### 7.2 30+ Task Role Matrix & Thinking Calibration
The `settings.yaml` configuration establishes fine-grained roles with calibrated reasoning parameters:
- **Macro & Fundamental Roles**: `stage1_fundamental`, `stage1_shadow_check`, `stage1_escalation`, `fundamental_verifier`.
- **Per-Asset & Debate Roles**: `stage2_prescreen`, `stage2_per_asset_primary`, `stage2_per_asset_secondary`, `stage2_session_trigger`, `specialist_technical`, `specialist_sentiment`, `specialist_macro`, `debate_bull`, `debate_bear`, `debate_judge`, `stage2_adjudicator`.
- **Portfolio & Risk Management**: `risk_gate_conservative`, `risk_gate_aggressive`, `risk_gate_neutral`, `portfolio_manager_per_trade`, `portfolio_synthesis`, `adversarial_check`.
- **News Processing**: `news_classification`, `news_classification_escalation`, `news_classification_verifier`, `news_digest`, `news_digest_macro_overview`, `news_digest_verifier`.
- **Interaction & Reflection**: `chat_telegram`, `chat_telegram_medium`, `chat_telegram_complex`, `trade_reflection`, `cot_precompute`.

### 7.3 Token Optimization Strategies
1. **Caveman Mode (`caveman_compressor.py`)**: Condenses conversational transcripts and operational tool payloads by stripping conversational fluff, articles, and filler words, slashing token consumption by up to 65% while maintaining full technical fidelity.
2. **4-Tier Prompt Assembly (`PromptAssembler`)**:
   - *Tier 0 (Anchor)*: Permanent static system instructions maintaining identical token sequences to maximize KV-cache reuse.
   - *Tier 1 (Canonical Rules)*: Compressed standard operating procedures and non-negotiable risk boundaries.
   - *Tier 2 (Tool Stubs)*: Compact functional interface declarations.
   - *Tier 3 (Dynamic Context)*: Volatile market data appended strictly at the tail of the prompt payload.
3. **Cache Breakpoint Manager (`cache_breakpoint_manager.py`)**: Guarantees system prompts meet or exceed the $\ge 1,024$ token caching threshold using deterministic padded anchors, ensuring 100% activation of Gemini and Anthropic prompt caching mechanisms and cutting input token costs by 50-80%.
4. **Lossless Semantic Slicing (LSS) & Context Compaction**: Prunes obsolete multi-turn tool execution histories without corrupting JSON structures or discarding critical market extremes.
5. **Progressive Tool Registry (`ProgressiveToolRegistry`)**: LLMs are initialized with core primitives; specialized analytical tools are exposed dynamically on demand.

---

## 8. 4-Tier Memory Hierarchy & Continuous Empirical Learning

The system implements a structured multi-tier memory architecture bridging permanent operating principles and empirical market lessons:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          4-TIER MEMORY HIERARCHY                            │
│                                                                             │
│  Layer 0: Core Operating Soul (TRADING_SOUL.md)                             │
│  ├── Permanent operational identity, capital preservation doctrine          │
│                                                                             │
│  Layer 1: Factual Macro Baseline (MACRO_REALITY.md)                         │
│  ├── Verified 2026 geopolitical & macroeconomic realities (Fed leadership,  │
│  │   Strait of Hormuz / Red Sea shipping, tariff regimes, BoJ rate normalization)│
│                                                                             │
│  Layer 2: Structural Market Chronicle (MarketChronicle ORM Model)           │
│  ├── Chronological repository of structural macro shocks and regime shifts  │
│                                                                             │
│  Layer 3: Episodic Precedents Search (SessionSearchEngine)                  │
│  ├── Semantic and structural precedent matching across historical records   │
│                                                                             │
│  Layer 4: Continuous Empirical Learning (CandidateLesson & Playbook)        │
│  ├── trade_reflection → lesson_consolidator → lessons_learned.md            │
│  └── Self-Adapting GEPA Lite Engine                                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **Layer 0 (Permanent Soul)**: Contains core behavioral axioms defined in `config/TRADING_SOUL.md`, injected into all system prompts to maintain consistent risk discipline.
2. **Layer 1 (Factual Baseline)**: `config/MACRO_REALITY.md` provides verified ground-truth facts for the current 2026 economic environment, preventing temporal hallucination regarding central bank leadership and geopolitical baselines.
3. **Layer 2 (Market Chronicle)**: The `market_chronicles` table logs multi-week macroeconomic trends and structural shifts (geopolitical crises, emergency monetary adjustments).
4. **Layer 3 (Episodic Precedent Retrieval)**: `SessionSearchEngine` executes structural queries against PostgreSQL to surface past market setups sharing technical and macro characteristics with current conditions.
5. **Layer 4 (Candidate Lessons & Playbook Consolidation)**: Every closed trade (real execution and paper what-if records) is audited by `TradeReflector`. Empirical observations are stored as `CandidateLesson` records. Lessons passing out-of-sample validation are consolidated periodically by `lesson_consolidator.py` into `skills/trading/lessons_learned.md`.
6. **GEPA Lite (Prompt Evolution Engine)**: Tests and refines prompt variations autonomously across 14-day evaluation windows based on Sharpe ratio and win rate performance metrics.

---

## 9. Background Scheduling & Autonomous Guardian Ecosystem (26 Components)

The entire platform operates under continuous surveillance by autonomous background guardians and schedulers:

| No | Component Name | Cadence / Trigger | Primary Responsibility & Mission |
|---|---|---|---|
| 1 | `GraphCycleScheduler` | Every 8 Hours (00:00, 08:00, 13:00 UTC) | Executes complete LangGraph cognitive analysis cycles across the entire asset universe. |
| 2 | `SessionTriggerLoop` | Major Session Opens | Detects London open (07:00 UTC) and New York open (12:00 UTC) to trigger momentum analyses. |
| 3 | `DailyReportScheduler` | Daily at 01:00 UTC | Compiles and delivers comprehensive performance, PnL, and exposure reports to Telegram. |
| 4 | `TriggerChecker` | Every 2 Minutes | Evaluates pending `trade_triggers` against live market prices without invoking LLMs. |
| 5 | `NewsWatcher` | Every 5 Minutes | Scans news feeds, applies low-cost filtering, and triggers targeted Stage 2 re-analyses upon shocks. |
| 6 | `ActiveCalendarPoller` | Release Minute Windows | Executes aggressive 15-second polling on economic calendars around high-impact event times. |
| 7 | `PostReleaseAnalyzer` | 15-min Post-Release | Computes economic surprise deviations (`actual` vs `consensus`) once market volatility settles. |
| 8 | `FlashCrashDetector` | Every 30 Seconds | Volatility circuit breaker (ATR mult $\ge 5.0$ / move% $\ge 2.0\%$). Tightens stops to BE and halts pair for 30m. |
| 9 | `FloatingDrawdownMonitor` | Every 30 Seconds | Evaluates equity vs high-water mark; triggers kill switch if drawdown breaches 3% over 2 consecutive checks. |
| 10 | `PositionGuardian` | Every 60 Seconds | Audits high-impact news calendars; broadcasts 30-min warnings and liquidates risky exposures if needed. |
| 11 | `FridayCloseGuardian` | Every 30m (Friday) | Evaluates open exposures ahead of weekend closure (20:00 UTC) to eliminate weekend gap risk. |
| 12 | `TrailingStopManager` | Every 5 Minutes | Dynamically ratchets Stop Loss orders based on ATR thresholds (0.8x Breakeven, 1.2x Trailing). |
| 13 | `PositionExitReviewer` | Every 4 Hours | Prompts AI models to audit stagnating positions or structural reversal developments. |
| 14 | `EdgeStrategyRunner` | Every 60 Seconds | Evaluates and executes 6 deterministic quantitative strategies autonomously. |
| 15 | `MarketDataScheduler` | Every 2 Minutes | Pulls latest OHLCV candle bars from MT5, calculates indicators, and triggers auto-healing warmups. |
| 16 | `MT5HealthMonitor` | Every 60 Seconds | Audits MT5 IPC socket health; raises alerts upon dropouts and re-synchronizes market state on reconnect. |
| 17 | `PaperTradeMonitor` | Every 5 Minutes | Evaluates virtual positions against live price bars, closes paper trades, and updates edge statistics. |
| 18 | `WhatIfResolver` | Every 1 Hour | Resolves rejected trade setups (what-if scenarios) to evaluate RiskGate decision fidelity. |
| 19 | `ScraperLoop` | Every 1 Hour | Executes staggered scraper queues and compiles thematic rolling news digests. |
| 20 | `DigestSliceScheduler` | Every 2 Hours | Generates rolling 2-hour thematic currency slices in PostgreSQL. |
| 21 | `DBHealthCheck` | Every 5 Minutes | Executes `SELECT 1` health queries against PostgreSQL to verify connection pool integrity. |
| 22 | `PositionSyncLoop` | Every 60 Seconds | Reconciles discrepancies between active broker positions in MT5 and database records. |
| 23 | `NotifierOutboxFlusher` | Continuous | Flushes outbound notification queues to Telegram administrators asynchronously. |
| 24 | `HeartbeatManager` | Every 10 Seconds | Writes current timestamps to `heartbeat.txt` in the MT5 Common directory to reset the EA dead-man switch. |
| 25 | `TelegramBot` | Continuous Polling | Processes operator commands, inline confirmation callbacks, and interactive system queries. |
| 26 | `DashboardServer` | Continuous (FastAPI) | Serves REST endpoints and powers the React frontend observability dashboard. |

---

## 10. Position Sizing & Deterministic Risk Gate

The `RiskGate` and `PositionSizer` modules form an uncompromising deterministic defense perimeter around capital:

### 10.1 Position Sizing Formula
Position sizes are computed using strict *fixed-fractional* risk based on stop loss distance relative to account equity:

$$\text{Risk Amount (\USD)} = \min\left(\text{Equity} \times \text{Risk Percent}, \text{Max Risk Amount}\right)$$

$$\text{Lot Size} = \frac{\text{Risk Amount}}{\text{Stop Loss Distance in Price} \times \text{Contract Size} \times \text{Tick Value Ratio}}$$

Calculated lot sizes are rounded to the broker's minimum lot step (e.g., 0.01) and clamped within `max_lot_per_symbol` (1.0 lot) subject to account margin availability.

### 10.2 Intraday Range Strategy (ADR-Based Bands)
To prevent unrealistic price targets within intraday horizons:
- **Take Profit Band**: Restricted to **40% to 90% of the 5-day ADR** of the instrument. TP targets exceeding 100% ADR are rejected due to low single-session probability.
- **Stop Loss Ceiling**: Capped at **40% of the 5-day ADR** to guarantee healthy Risk:Reward ratios and avoid absorbing outsized adverse excursions.
- **Minimum R:R Ratio**: Strictly enforced at **1.3** (Recommended 1.5 to 2.0).

### 10.3 10-Layer Deterministic Validation Gate (`RiskGate`)
Before dispatching an order to the broker, it must pass 10 validation layers:
1. **Kill Switch Status Check**: Verifies trading is not paused manually via Telegram or automatically via drawdown triggers.
2. **Per-Trade Risk Ceiling**: Financial risk cannot exceed configured `risk_percent_per_trade` (default 0.5% - 1.0%).
3. **Daily & Weekly Drawdown Caps**: Current daily drawdown cannot exceed 3.0% and weekly drawdown cannot exceed 6.0%.
4. **Maximum Concurrent Open Positions**: Total open positions across the entire portfolio cannot exceed 5.
5. **Maximum Position per Symbol**: Maximum 1 open position per symbol (exempting paired dual-leg statistical arbitrage).
6. **Portfolio Correlation Exposure Cap**: Evaluates dynamic rolling correlation matrices (EWMA); forbids opening correlated directional positions across more than 3 currency pairs ($r \ge 0.7$).
7. **News Blackout Window**: Blocks new order execution within 15 minutes before and 15 minutes after high-impact economic releases for affected currencies.
8. **VIX Volatility Regime Scaling**:
   - VIX < 20: Normal Risk (1.0x sizing).
   - VIX 20 - 25: Cautionary Regime (0.8x sizing).
   - VIX 25 - 35: Defensive Regime (0.5x sizing, heightened confluence threshold).
   - VIX $\ge 35$: Trading Halted (Zero new trade allocations).
9. **Consecutive Loss Suspension**: If a symbol experiences 3 consecutive Stop Loss hits within a single trading day, it is placed in automated quarantine for 12 hours.
10. **Empirical Confluence Verification**: The LLM's claimed confluence score is independently re-verified by `ConfluenceVerifier`; divergence between LLM claims and deterministic indicators cannot exceed 3 points.

---

## 11. MetaTrader 5 (MT5) Execution & EA Bridge Safety Net

Execution integration combines official native Python APIs with broker-side Expert Advisors:

### 11.1 MT5Client Architecture (Python Native Integration)
- The `MT5Client` module wraps official `MetaTrader5` SDK calls asynchronously via a dedicated background thread executor to avoid blocking the asyncio event loop.
- Supports multi-timeframe bar retrieval (`M15`, `H1`, `H4`, `D1`), live spread inspection, market order execution (`ORDER_TYPE_BUY` / `ORDER_TYPE_SELL`), and trailing stop loss modifications.

### 11.2 Paired-Leg Execution
For statistical arbitrage (`XTIPairsReadiness`), `ExecutionService.execute_paired_analyses()` executes both legs simultaneously (e.g., Buy WTI and Sell Brent) with notional-balanced sizing. If one leg fails broker execution, the active counter-leg is immediately liquidated to eliminate unhedged directional exposure.

### 11.3 AIAgent_EA.mq5 (MQL5 Expert Advisor & Dead-Man's Switch)
The EA attached to terminal charts functions as an autonomous broker-side safety net:
- **Broker-Side Hard SL/TP Enforcement**: Every order dispatched by Python must contain explicit hard SL and TP parameters registered directly on broker servers, guaranteeing capital protection even during total server network outages.
- **File-Based Dead-Man's Switch**: The `HeartbeatManager` in Python writes an updated timestamp to the shared directory (`MT5 Common Files/heartbeat.txt`) every 10 seconds.
- The EA polls this file every few seconds. If `heartbeat.txt` remains un-updated beyond the tolerance window (default 120 seconds, indicating Python process crash, freeze, or host OS failure):
  1. The EA raises immediate audio and log alarms on the MT5 terminal.
  2. The EA autonomously liquidates all active open positions tagged with the system magic number.
  3. The EA purges all residual pending orders to prevent unattended order execution.

---

## 12. Telegram Interface & Mobile Operational Control

The Telegram bot subsystem (`telegram_bot/`) acts as the mobile mission control center and real-time observability interface:

### 12.1 Dual-Path Command Routing
Inbound messages are routed via `CommandRouter`:
- **Deterministic Path (Direct Commands)**: Fixed-format commands (`/status`, `/positions`, `/balance`, `/pnl`, `/pause`, `/resume`, `/kill`, `/help`) resolve directly from memory cache and PostgreSQL in single-digit milliseconds **without invoking LLMs** (zero token overhead, sub-second latency).
- **Conversational Path (Chat Agent)**: Natural language queries ("Why hasn't XAUUSD entered a position?", "What is the post-CPI outlook for gold?") route to `ChatAgent`.

### 12.2 Multi-Tier Chat Agent & Chat Tool Router
To minimize token costs, operator queries are triaged by analytical complexity:
- *Simple*: Answered by lightweight models (`gemini-3.1-flash-lite`).
- *Medium*: Standard technical questions answered by `gemini-3.5-flash-lite`.
- *Complex*: Deep strategy inquiries, macroeconomic evaluations, or audit requests answered by `gemini-3.7-flash` with active reasoning.
- `ChatToolRouter`: Exposes only contextually relevant tool definitions to the conversational model, avoiding bloated schema overhead.

### 12.3 Interactive Confirmation Workflows (Inline Keyboards)
Financially impactful operations (manual position close proposals, risk parameter changes) are never executed autonomously from conversation. The agent formats a `PendingAction` and delivers an interactive Telegram message equipped with inline callback buttons:
- `[Confirm & Execute]`
- `[Cancel]`
Actions are executed only after explicit confirmation callback from an authorized Administrator ID.

### 12.4 Headless Candlestick Chart Engine (`chart_generator.py`)
Features an automated headless charting engine (`matplotlib` dark-theme). Operators can request visual technical charts complete with SMA 20/50/200 overlays, volume histogram, liquidity zones, and entry/SL/TP coordinate lines delivered directly as high-resolution PNG images.

---

## 13. Comprehensive System Tool Catalog (50+ Tools)

Tools are categorized by functional domain and role permissions in `ToolExecutor`:

| Category | Tool Identifier | Permitted Roles | Functional Description |
|---|---|---|---|
| **Macro & Fundamental** | `get_economic_calendar` | Stage 1, Telegram | Retrieves economic calendar releases (actual, forecast, prior). |
| | `get_news_items` | Stage 1, Telegram | Reads filtered financial news streams by currency tag. |
| | `get_treasury_yields` | Stage 1, Specialist | Retrieves US sovereign yields (2Y, 5Y, 10Y, 30Y) from FRED. |
| | `get_interest_rates` | Stage 1, Specialist | Retrieves central bank policy rates (Fed, ECB, BOE, BOJ). |
| | `get_fedwatch_probabilities` | Stage 1, Specialist | FOMC target rate probabilities from CME FedWatch. |
| | `get_cot_report` | Stage 1 & 2, Specialist | CFTC institutional net positioning (Dealer, Asset Mgr, Leveraged). |
| | `get_vix` | Stage 1 & 2, Risk | Cboe Volatility Index (VIX) daily closing series from Yahoo Finance. |
| | `get_bond_yield_spreads` | Stage 1 & 2, Specialist | International 10-year sovereign bond yield spreads (DE, UK, JP, AU). |
| | `get_funding_rate` | Stage 2, Specialist | Bitcoin perpetual contract funding rates from Binance / Bybit. |
| | `submit_fundamental_brief` | Stage 1 | Persists structured macro fundamental brief to PostgreSQL. |
| | `get_fundamental_brief` | Stage 2, Telegram | Retrieves the current active global macro fundamental brief. |
| **Price & Technical** | `get_price_history` | Stage 2, Telegram | Retrieves historical OHLCV candlestick series across timeframes (M15, H1, H4, D1). |
| | `get_technical_indicators` | Stage 2, Specialist | Computes technical indicator values (EMA, RSI, MACD, Stoch, BB, ATR). |
| | `get_swing_points` | Stage 2, Specialist | Identifies confirmed fractal swing high and swing low pivots. |
| | `get_sr_zones` | Stage 2, Specialist | Surfaces active horizontal Support and Resistance density clusters. |
| | `get_liquidity_zones` | Stage 2, Specialist | Surfaces un-swept buy-side and sell-side liquidity pools. |
| | `get_fvg_zones` | Stage 2, Specialist | Retrieves Fair Value Gap boundaries (unfilled / partially filled). |
| | `get_order_blocks` | Stage 2, Specialist | Surfaces institutional Order Block zones. |
| | `get_structure_breaks` | Stage 2, Specialist | Retrieves Break of Structure (BOS) and Change of Character (ChoCH) events. |
| | `get_volume_profile` | Stage 2, Specialist | Retrieves Value Area High (VAH), Value Area Low (VAL), POC, and VWAP levels. |
| | `get_timesfm_forecast` | Stage 2, Specialist | Retrieves 24-hour forward quantile price projections from Google TimesFM 3.0. |
| | `get_multi_timeframe_summary` | Stage 2, Telegram | Generates multi-timeframe trend and momentum alignment summaries across M15-D1. |
| | `get_spread_snapshot` | Stage 2, Risk | Evaluates live broker spread against historical averages. |
| | `get_market_correlations` | Stage 2, Risk | Computes dynamic rolling correlation matrices (EWMA) across instruments. |
| | `submit_asset_analysis` | Stage 2 | Commits per-asset trade decisions and order parameters to PostgreSQL. |
| **Composite Tools** | `execute_market_context` | Stage 2 | Bundles fundamental brief, calendar, news, and VIX in a single turn. |
| | `execute_technical_analysis`| Stage 2 | Bundles OHLCV, indicators, S/R, liquidity, and FVG in a single turn. |
| | `execute_institutional_data`| Stage 2 | Bundles COT reports, funding rates, and yield curves in a single turn. |
| **Execution & Portfolio** | `get_open_positions` | Risk, Telegram | Retrieves active open positions in MT5 and database records. |
| | `get_trade_history` | Risk, Telegram | Retrieves historical closed trades and realized PnL. |
| | `get_account_info` | Risk, Telegram | Inspects broker account parameters (Balance, Equity, Margin, Free Margin, Leverage). |
| | `get_risk_state` | Risk, Telegram | Checks daily drawdown limit status, exposure limits, and pause flags. |
| | `get_active_triggers` | Scheduler, Telegram | Lists active conditional trade triggers awaiting price activation. |
| | `propose_action` | Telegram Chat | Generates manual operational proposals requiring admin button confirmation. |
| **Diagnostics & Memory** | `get_recent_activity` | Telegram | Inspects recent system audit activity logs. |
| | `get_system_health` | Telegram | Checks MT5 connectivity, database pool health, task uptimes, and API latencies. |
| | `get_edge_tracker_status` | Telegram | Checks empirical edge tracking (win rate, profit factor, confidence intervals). |
| | `get_calibration_status` | Telegram | Checks confluence threshold calibration status and model drift flags. |
| | `get_token_usage_and_costs`| Telegram | Summarizes LLM token consumption and month-to-date API costs. |
| | `get_paper_trading_perf` | Telegram | Delivers performance metrics for accumulated paper trading records. |
| | `get_chart` | Telegram | Generates and sends candlestick technical analysis charts. |
| | `get_conversation_history` | Telegram Chat | Retrieves prior operator conversation context. |

---

## 14. PostgreSQL Database Schema (35+ ORM Models)

The persistence tier utilizes PostgreSQL 16+ managed via SQLAlchemy 2.0 Async ORM (`database/models.py`):

### 14.1 Raw Feeds & Macroeconomic Cluster
1. `NewsItem`: Raw scraped news and RSS feed items (`source`, `title`, `summary`, `url`, `published_at`, `currency_tags`, `scraped_at`).
2. `NewsDigest`: Compressed thematic news summaries per analysis batch (`content_json`, `generated_at`).
3. `NewsDigestSlice`: Rolling 2-hour thematic currency slices (`currency`, `slice_data`, `period_start`, `period_end`).
4. `MarketChronicle`: Long-term structural macro events and policy shifts (`category`, `event_headline`, `impact_assessment`, `active_until`).
5. `EconomicCalendar`: Scheduled economic releases (`event_name`, `country`, `currency`, `impact`, `actual`, `forecast`, `previous`, `event_time`).
6. `TreasuryYield`: Daily US Treasury yield curves (`tenor`, `yield_percent`, `date`).
7. `BondYieldData`: International sovereign yields for Germany, UK, Japan, Australia (`country`, `tenor`, `yield_percent`, `date`).
8. `InterestRate`: Benchmark central bank policy rates (`bank`, `rate_percent`, `effective_date`).
9. `FedWatchProbability`: Target rate probability distributions from CME FedWatch (`meeting_date`, `probabilities_json`).
10. `COTReport`: CFTC institutional positioning reports (`market_code`, `dealer_long`, `dealer_short`, `leveraged_long`, `leveraged_short`, `report_date`).
11. `VIXData`: Daily equity volatility index closing records (`date`, `open`, `high`, `low`, `close`).
12. `DXYData`: US Dollar Index daily closing data (`date`, `close`).

### 14.2 Price Series & Market Structure Cluster
13. `PriceOHLCV`: Historical candlestick bars from MT5 (`symbol`, `timeframe`, `timestamp`, `open`, `high`, `low`, `close`, `volume`).
14. `TechnicalIndicator`: Calculated technical indicator records (`symbol`, `timeframe`, `timestamp`, `indicator_name`, `value_json`).
15. `SwingPoint`: Verified swing high and swing low pivots (`symbol`, `timeframe`, `timestamp`, `swing_type`, `price`).
16. `SRZone`: Historical horizontal Support and Resistance clusters (`symbol`, `timeframe`, `price_high`, `price_low`, `strength`, `touch_count`).
17. `LiquidityZone`: Market liquidity pools (`symbol`, `timeframe`, `zone_high`, `zone_low`, `zone_type`, `swept_at`).
18. `FVGZone`: Fair Value Gap zones (`symbol`, `timeframe`, `gap_high`, `gap_low`, `direction`, `status`).
19. `OrderBlock`: Institutional Order Block zones (`symbol`, `timeframe`, `high`, `low`, `direction`, `mitigated_at`).
20. `StructureBreak`: Market structure transition events BOS and ChoCH (`symbol`, `timeframe`, `break_type`, `broken_level`, `timestamp`).
21. `TimesFMForecast`: Quantile price projections from Google TimesFM 3.0 (`symbol`, `timeframe`, `horizon_hours`, `quantile_predictions_json`).

### 14.3 AI Analysis & Dialectical Debate Cluster
22. `FundamentalBrief`: Stage 1 global macro fundamental brief (`macro_narrative`, `currency_bias_json`, `key_risks_json`, `valid_until`).
23. `AssetAnalysis`: Stage 2 per-asset analytical decisions (`symbol`, `decision`, `confidence`, `entry_price`, `sl`, `tp`, `rationale`, `confluence_score`, `debate_bull_thesis`, `debate_bear_dissent`, `debate_verdict`, `pair_group_id`).
24. `TradeTrigger`: Conditional entry triggers awaiting price validation (`symbol`, `condition_type`, `condition_json`, `status`).
25. `MT5Signal`: Execution bridge linking `AssetAnalysis` to broker order instructions (`symbol`, `signal_type`, `order_status`).
26. `DecisionReflection`: Post-trade AI reflections (`analysis_id`, `outcome_pnl`, `lesson_extracted`, `was_decision_sound`).
27. `PrescreenLog`: Asset prescreening filter audit trails (`symbol`, `action_taken`, `rejection_reason`).
28. `NewsClassificationOutcome`: Tracks post-release price impact of classified news items.
29. `CandidateLesson`: Empirical trading lessons undergoing out-of-sample validation (`source_trade_id`, `observation`, `rule_proposal`, `validation_status`).

### 14.4 Execution, Risk & System Cluster
30. `Position`: Active and closed broker positions in MT5 (`ticket`, `symbol`, `direction`, `volume`, `entry_price`, `sl`, `tp`, `pnl`, `status`, `opened_at`, `closed_at`, `close_reason`, `pair_group_id`).
31. `TradeOutcome`: Comprehensive post-close PnL and trade duration metrics (`position_id`, `pnl_net`, `r_multiple`, `holding_hours`, `exit_reason`).
32. `PaperTradeRecord`: Simulated paper trade executions for empirical edge verification (`symbol`, `direction`, `virtual_pnl`, `exit_reason`).
33. `OrderLog`: Complete broker order dispatch log (`action`, `symbol`, `params_json`, `status`, `error_message`).
34. `RiskState`: Daily portfolio risk snapshots (`date`, `daily_pnl`, `current_drawdown`, `trading_paused`, `pause_reason`).
35. `TelegramConversation`: Operator conversational history for persistent chat context (`user_id`, `role`, `message`, `timestamp`).
36. `ActivityLog`: Categorized system audit activity stream (`timestamp`, `category`, `actor`, `description`, `metadata_json`).
37. `TokenUsageLog`: LLM token expenditure tracking per role and provider (`provider`, `model`, `task_role`, `input_tokens`, `output_tokens`, `cost_usd`).
38. `SystemConfig`: Dynamic key-value store for runtime parameters (`key`, `value`).
39. `CyclePerformance`: Execution duration and resource metrics per LangGraph cycle.
40. `ConfluenceFactorOutcome`: Empirical evaluation of individual confluence factor contributions to trade outcomes.

---

## 15. Observability, Prometheus Metrics & Web Dashboard

Operational transparency is maintained through multi-channel observability:

### 15.1 FastAPI REST API (`logging_observability/dashboard/api.py`)
Provides 15+ unified RESTful endpoints:
- `GET /api/status`: System heartbeat, uptime, operating mode, and active task registry.
- `GET /api/positions`: Real and paper open positions.
- `GET /api/pnl`: Historical PnL series and equity curves.
- `GET /api/brief`: Active global macro fundamental brief.
- `GET /api/analyses`: Recent per-asset analysis decisions.
- `GET /api/debates`: Full Bull/Bear debate transcripts and judicial verdicts.
- `GET /api/market-data`: Real-time market snapshots, indicators, and spreads.
- `GET /api/edge-metrics`: Empirical win rate, profit factor, and confidence intervals.
- `GET /api/token-usage`: LLM token expenditure, daily costs, and monthly budget pacing.
- `GET /api/activity`: Real-time system activity audit stream.
- `POST /api/actions/kill`: Web-based emergency kill switch dispatch.
- `POST /api/actions/pause` & `POST /api/actions/resume`: Operational pause and resume controls.

### 15.2 Frontend React 18 / TypeScript (`dashboard/frontend/`)
Built with Vite, TypeScript, and Tailwind CSS:
- **Status Widgets**: `AgentStatusBar`, `MetricCard`, `StatusIndicator`.
- **Analytical Charts**:
  - `EquityChart`: Real vs paper capital growth trajectories.
  - `FactorHeatmap`: Empirical efficacy heatmap across technical confluence factors.
  - `WinRateGauge`: Interactive performance gauge tracking progress toward the 55% live gate.
  - `VixSparkline`: Rolling equity volatility trendlines.
  - `DecisionDistribution`: Action breakdown (Buy, Sell, Wait, Avoid).
- **Control Panels**: `PositionsTable`, `AnalysisGrid`, `ActivityFeed`, `EdgeMetricsPanel`, `SystemPanel`.

### 15.3 Prometheus Metrics & OpenMetrics
The `MetricsCollector` singleton exposes standard Prometheus metrics:
- Counter: `trading_agent_orders_total`, `trading_agent_tool_calls_total`, `trading_agent_api_errors_total`.
- Gauge: `trading_agent_equity_usd`, `trading_agent_balance_usd`, `trading_agent_daily_drawdown_pct`, `trading_agent_open_positions`.
- Histogram: `trading_agent_cycle_duration_seconds`, `trading_agent_llm_latency_seconds`.

---

## 16. Environment Configuration & Runtime Parameters

### 16.1 Environment Variables Template (`.env.example`)
```ini
# Relational Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/trading_agent_db

# AI Provider API Keys
ANTHROPIC_API_KEY=sk-ant-api03-...
GEMINI_API_KEY=AIzaSy...                          # Primary Paid Pro Key
GEMINI_API_KEYS=AIzaSyKey1...,AIzaSyKey2...       # Free Tier Multi-Key Rotation
OPENROUTER_PAID_API_KEY=sk-or-v1-...              # Commercial Paid Key
OPENROUTER_API_KEYS=sk-or-free1...,sk-or-free2... # Community Free Key Rotation
GROQ_API_KEYS=gsk_...                             # Free Tier Key Rotation
OPENAI_API_KEY=sk-proj-...
DEEPSEEK_API_KEY=sk-...

# MetaTrader 5 Broker Configuration
MT5_ACCOUNT=12345678
MT5_PASSWORD=BrokerPasswordSecret
MT5_SERVER=YourBroker-LiveServer
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_COMMON_FILES_PATH=C:\Users\Username\AppData\Roaming\MetaQuotes\Terminal\Common\Files

# Telegram Bot Interface
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_ADMIN_CHAT_ID=987654321

# External Data Feeds
FRED_API_KEY=abcdef0123456789abcdef0123456789
FINNHUB_API_KEY=c12345...

# Observability Dashboard Server
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8000
```

### 16.2 Key Runtime Parameters (`config/settings.yaml`)
- **Asset Universe**: `XAUUSD`, `EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`, `XTIUSD`, `BTCUSD`, `XBRUSD`.
- **Cycle Schedule (UTC)**: 00:00, 08:00, 13:00 + London/NY Session Open Triggers.
- **Risk per Trade**: 0.5% (Max 1.0% after verified empirical edge).
- **Maximum Daily Drawdown**: 3.0% (Triggers kill switch with 2x confirmation hysteresis).
- **Maximum Weekly Drawdown**: 6.0%.
- **Intraday ADR Targets**: Take Profit 40% - 90% ADR; Stop Loss ceiling 40% ADR; Minimum R:R 1.3.
- **Monthly API Budget**: $100.00 (Warning alert at 80%, automated pause if exceeding $5.00 daily limit).
- **Live Transition Gate**: Mandates $\ge 50$ paper trades accumulated with win rate $\ge 55\%$.

---

## 17. Compliance, System Resilience & Disaster Recovery

1. **Scraper Resilience & Graceful Ingestion**:
   - All scrapers inherit from `BaseScraper` with 30-second timeouts, up to 3 retries with exponential backoff, and randomized user agents.
   - Central bank RSS feeds minimize reliance on brittle HTML scraping.
   - Automated Cloudflare detection transitions to DrissionPage `ChromiumPage` with automated temp-profile cleanup to prevent memory exhaustion.
2. **Auto-Healing & Crash Recovery**:
   - `MT5HealthMonitor` detects broken terminal IPC connections, initiates reconnection sequences, and triggers instant market data warmups once restored.
   - `DBHealthCheck` recycles stale database connections in the asyncpg pool without requiring process restarts.
   - Background tasks run inside isolated `_run_with_restart` wrappers featuring exponential backoff, preventing isolated worker failures from crashing the core runtime.
3. **Legal Compliance & Regulatory Boundaries**:
   - The platform is engineered exclusively for proprietary capital and personal trading accounts.
   - Public data ingestion via scraping and RSS is strictly intended for internal analytical consumption and non-commercial execution.
   - Third-party asset management is subject to regulatory authorities and mandates appropriate investment advisory licensing.

---

## 18. Operational Guidelines for AI Assistants & Developers

When modifying or extending this codebase:
1. **Never Compromise Safety Guards**: Never disable `paper_trading.enabled` checks, `RiskGate` validation, `ConfluenceVerifier`, or `HeartbeatManager` for development convenience without explicit operator consent.
2. **Adhere to Defined Pydantic Schemas**: Any new data passed through analytical pipelines must be defined in `analysis/schemas/pydantic_schemas.py` and reflected in `database/models.py`.
3. **Token Efficiency Standards**: Maintain Caveman mode for conversational output and ensure system prompt assemblies preserve padded anchors ($\ge 1,024$ tokens) for maximum caching efficiency.
4. **Maintain Documentation & Indexes**: Any addition or modification of files, classes, or functions must be documented in `INDEX.md` and `STRUKTUR.md`, followed by executing `python scripts/update_index_toc.py`.
5. **Mandatory Test Verification**: All modifications must pass validation via `pytest` before being marked complete.
