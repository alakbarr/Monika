# Changelog

All notable changes to **Monika** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-09-14

### Initial Production Release

#### Added
- **SOTA Agent Harness & Orchestration**:
  - Centralized LLM task routing with support for Anthropic Claude, Google Gemini, Groq, OpenAI ChatGPT, and OpenRouter.
  - Multi-tier prompt system with structured fallback handling and capability matrix detection.
  - `StallGuard` and turn budgeting to prevent infinite execution loops in autonomous reasoning.
  - `ContextCompressor` and prompt compression preserving critical market context while minimizing token overhead.
  - Programmatic Tool Calling (PTC) sandbox with sanitized subprocess environment variables.
  - Error classification and automated failover routing for API rate limits, model hallucinations, and transport timeouts.

- **Multi-Agent Dialectical Debate Pipeline**:
  - Two-stage analysis architecture: Stage 1 Macroeconomic Foundation and Stage 2 Per-Asset Tactical Synthesis.
  - Adversarial Bull and Bear specialist agents engaged in structured dialectic debates.
  - `MarketAwareJudge` implementing Bayesian confidence scoring and evidence weighting.
  - Subagent Blackboard architecture for cross-agent memory sharing and scenario tree generation.

- **Smart Money Concepts (SMC) & Market Structure Indicators**:
  - Automated detection of Break of Structure (BOS) and Change of Character (CHoCH).
  - Fair Value Gap (FVG) and Order Block identification across multi-timeframe candle streams.
  - Liquidity sweep verification and inducement level identification.
  - Integrated Google TimesFM 3.0 foundation model for daily range prediction and volatility envelope projection.

- **MetaTrader 5 (MT5) Execution Engine**:
  - High-performance direct IPC bridge via `MetaTrader5` Python client.
  - Fallback Expert Advisor (EA) bridge (`AIAgent_EA.mq5`) with heartbeat monitoring and dead-man switch auto-liquidation.
  - Advanced order execution supporting market execution, limit orders, stop-loss / take-profit placement, and partial tranche scaling.
  - Real-time `OrderReconciler` and `PositionSynchronizer` with slippage protection and spread gating.

- **Mechanical Risk Gate & Capital Protection**:
  - Strict rule-based `RiskGate` and `EffectGate` enforcing position limits prior to order transmission.
  - Real-time Daily Drawdown circuit breaker monitoring realized and floating equity losses.
  - Flash crash anomaly detection and high-spread volatility filters.
  - Dynamic risk-reward ratio pairing, volatility-adjusted position sizing, and correlation limiter.
  - Forced Paper Trading incubation mode (`paper_trading.enabled`) ensuring trade history criteria before live execution.

- **Full-Stack Observability & Dashboard**:
  - FastAPI backend serving real-time REST endpoints, WebSocket telemetry feeds, and interactive Swagger UI at `/docs`.
  - React 19 + Vite frontend featuring real-time account equity curves, open position monitors, debate transcripts, and system health status.
  - Comprehensive trade performance analytics: win rate, profit factor, Sharpe ratio, and trade autopsies.
  - Prometheus metrics instrumentation and structured asynchronous activity logging.

- **Interactive Telegram Bot**:
  - Real-time two-way bot interface supporting administrative commands (`/status`, `/positions`, `/kill`, `/override_risk`, `/report`).
  - Forum topic dispatching for segmented channel alerts (Macro, Trade Signals, Execution, Risk Alerts).
  - Voice memo processing via Gemini audio transcription for hands-free queries.

- **Macro & Alternative Data Scrapers**:
  - Federal Reserve Economic Data (FRED) API integration for yields, inflation, and liquidity metrics.
  - Finnhub economic calendar parser with automated high-impact event blackout windows.
  - CME FedWatch rate hike probability tracker.
  - Real-time multi-source financial news digest engine and social media sentiment monitors.
