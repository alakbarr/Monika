# Comprehensive Codebase Index: Monika (MT5 Trading Agent)

This document provides an exhaustive structural index of all directories, files, functions, classes, data models, and runtime variables within the Monika quantitative trading platform.

## Table of Contents
*(Note: Line numbers are auto-updated by `scripts/update_index_toc.py`)*

- [Root Directory: `Monika/`](#root-directory-monika) - Line 79
  - [Folder: `.github`](#folder-github) - Line 137
    - [Folder: `.github/ISSUE_TEMPLATE`](#folder-githubissue_template) - Line 142
    - [Folder: `.github/workflows`](#folder-githubworkflows) - Line 150
  - [Folder: `deploy`](#folder-deploy) - Line 155
  - [Folder: `docs`](#folder-docs) - Line 169
  - [Folder: `scripts`](#folder-scripts) - Line 174
  - [Folder: `typings`](#folder-typings) - Line 179
  - [Folder: `src`](#folder-src) - Line 192
    - [Folder: `src/monika`](#folder-srcmonika) - Line 194
    - [Folder: `src/monika/core`](#folder-srcmonikacore) - Line 198
      - [Folder: `src/monika/core/config`](#folder-srcmonikacoreconfig) - Line 210
      - [Folder: `src/monika/core/security`](#folder-srcmonikacoresecurity) - Line 231
      - [Folder: `src/monika/core/telemetry`](#folder-srcmonikacoretelemetry) - Line 255
      - [Folder: `src/monika/core/telemetry/tracing`](#folder-srcmonikacoretelemetrytracing) - Line 270
      - [Folder: `src/monika/core/primitives`](#folder-srcmonikacoreprimitives) - Line 281
      - [Folder: `src/monika/core/analytics`](#folder-srcmonikacoreanalytics) - Line 304
      - [Folder: `src/monika/core/calibration`](#folder-srcmonikacorecalibration) - Line 315
      - [Folder: `src/monika/core/streaming`](#folder-srcmonikacorestreaming) - Line 321
      - [Folder: `src/monika/core/validation`](#folder-srcmonikacorevalidation) - Line 327
    - [Folder: `src/monika/domain`](#folder-srcmonikadomain) - Line 334
    - [Folder: `src/monika/domain/entities`](#folder-srcmonikadomainentities) - Line 338
    - [Folder: `src/monika/domain/risk`](#folder-srcmonikadomainrisk) - Line 348
    - [Folder: `src/monika/domain/execution`](#folder-srcmonikadomainexecution) - Line 442
    - [Folder: `src/monika/domain/indicators`](#folder-srcmonikadomainindicators) - Line 487
    - [Folder: `src/monika/domain/indicators/alpha_zoo`](#folder-srcmonikadomainindicatorsalpha_zoo) - Line 503
    - [Folder: `src/monika/domain/market`](#folder-srcmonikadomainmarket) - Line 545
    - [Folder: `src/monika/application`](#folder-srcmonikaapplication) - Line 555
      - [Folder: `src/monika/application/agent`](#folder-srcmonikaapplicationagent) - Line 559
      - [Folder: `src/monika/application/analysis`](#folder-srcmonikaapplicationanalysis) - Line 601
      - [Folder: `src/monika/application/graph`](#folder-srcmonikaapplicationgraph) - Line 627
    - [Folder: `src/monika/application/services`](#folder-srcmonikaapplicationservices) - Line 651
      - [Folder: `src/monika/application/execution`](#folder-srcmonikaapplicationexecution) - Line 695
      - [Folder: `src/monika/application/agent/harness`](#folder-srcmonikaapplicationagentharness) - Line 713
      - [Folder: `src/monika/application/plugins/engine`](#folder-srcmonikaapplicationpluginsengine) - Line 725
      - [Folder: `src/monika/application/skills`](#folder-srcmonikaapplicationskills) - Line 736
      - [Folder: `src/monika/application/governance`](#folder-srcmonikaapplicationgovernance) - Line 749
      - [Folder: `src/monika/application/scheduler`](#folder-srcmonikaapplicationscheduler) - Line 755
      - [Folder: `src/monika/application/backtest`](#folder-srcmonikaapplicationbacktest) - Line 779
      - [Folder: `src/monika/application/evals`](#folder-srcmonikaapplicationevals) - Line 800
      - [Folder: `src/monika/application/benchmark`](#folder-srcmonikaapplicationbenchmark) - Line 811
      - [Folder: `src/monika/application/plugins`](#folder-srcmonikaapplicationplugins) - Line 833
      - [Folder: `src/monika/application/protocol`](#folder-srcmonikaapplicationprotocol) - Line 847
    - [Folder: `src/monika/infrastructure`](#folder-srcmonikainfrastructure) - Line 866
      - [Folder: `src/monika/infrastructure/brokers`](#folder-srcmonikainfrastructurebrokers) - Line 870
      - [Folder: `src/monika/infrastructure/credentials`](#folder-srcmonikainfrastructurecredentials) - Line 896
      - [Folder: `src/monika/infrastructure/database`](#folder-srcmonikainfrastructuredatabase) - Line 906
      - [Folder: `src/monika/infrastructure/database/domain_models`](#folder-srcmonikainfrastructuredatabasedomain_models) - Line 934
      - [Folder: `src/monika/infrastructure/database/repositories`](#folder-srcmonikainfrastructuredatabaserepositories) - Line 952
      - [Folder: `src/monika/infrastructure/data_ingestion`](#folder-srcmonikainfrastructuredata_ingestion) - Line 966
        - [Folder: `src/monika/infrastructure/data_ingestion/sources`](#folder-srcmonikainfrastructuredata_ingestionsources) - Line 970
        - [Folder: `src/monika/infrastructure/data_ingestion/scrapers`](#folder-srcmonikainfrastructuredata_ingestionscrapers) - Line 989
          - [Folder: `src/monika/infrastructure/data_ingestion/scrapers/calendar`](#folder-srcmonikainfrastructuredata_ingestionscraperscalendar) - Line 1002
          - [Folder: `src/monika/infrastructure/data_ingestion/scrapers/macro`](#folder-srcmonikainfrastructuredata_ingestionscrapersmacro) - Line 1011
      - [Folder: `src/monika/infrastructure/graph/checkpointers`](#folder-srcmonikainfrastructuregraphcheckpointers) - Line 1023
      - [Folder: `src/monika/infrastructure/ml`](#folder-srcmonikainfrastructureml) - Line 1033
      - [Folder: `src/monika/infrastructure/providers`](#folder-srcmonikainfrastructureproviders) - Line 1039
      - [Folder: `src/monika/infrastructure/sandboxes`](#folder-srcmonikainfrastructuresandboxes) - Line 1053
      - [Folder: `src/monika/infrastructure/llm/rate_limiting`](#folder-srcmonikainfrastructurellmrate_limiting) - Line 1072
      - [Folder: `src/monika/infrastructure/mcp`](#folder-srcmonikainfrastructuremcp) - Line 1082
      - [Folder: `src/monika/infrastructure/notifications`](#folder-srcmonikainfrastructurenotifications) - Line 1092
      - [Folder: `src/monika/infrastructure/infra`](#folder-srcmonikainfrastructureinfra) - Line 1097
      - [Folder: `src/monika/infrastructure/llm`](#folder-srcmonikainfrastructurellm) - Line 1108
      - [Folder: `src/monika/infrastructure/storage`](#folder-srcmonikainfrastructurestorage) - Line 1118
    - [Folder: `src/monika/interfaces`](#folder-srcmonikainterfaces) - Line 1123
      - [Folder: `src/monika/interfaces/cli`](#folder-srcmonikainterfacescli) - Line 1127
      - [Folder: `src/monika/interfaces/dashboard`](#folder-srcmonikainterfacesdashboard) - Line 1135
      - [Folder: `src/monika/interfaces/gateway`](#folder-srcmonikainterfacesgateway) - Line 1142
      - [Folder: `src/monika/interfaces/telegram`](#folder-srcmonikainterfacestelegram) - Line 1150
      - [Folder: `src/monika/interfaces/workspace`](#folder-srcmonikainterfacesworkspace) - Line 1161

## Root Directory: `Monika/`

**File:** `.dockerignore`

**File:** `.env.example`

**File:** `.geminiignore`

**File:** `.gitignore`

**File:** `AGENTS.md`
  - **Description**: Universal engineering directives and system invariants for autonomous AI coding agents (Claude, Cursor, Codex, etc.) detailing navigation protocols, surgical engineering standards, large-codebase systemic integration & blast-radius tracing, /grill-me design alignment, doc sync mandates, triple quality gates (pytest/ruff/pyright zero-defect mandate), atomic git commit protocol, GitHub Actions CI surveillance, safety boundaries, and CLI workflows.

**File:** `CHANGELOG.md`

**File:** `CODE_OF_CONDUCT.md`

**File:** `CONTRIBUTING.md`

**File:** `DESIGN.md`

**File:** `docker-compose.yml`

**File:** `Dockerfile`

**File:** `GEMINI.md`
  - **Description**: Engineering directives and system invariants tailored for Google Gemini CLI and Antigravity agents detailing navigation protocols, surgical engineering standards, large-codebase systemic integration & blast-radius tracing, /grill-me design alignment, doc sync mandates, triple quality gates (pytest/ruff/pyright zero-defect mandate), atomic git commit protocol, GitHub Actions CI surveillance, safety boundaries, and CLI workflows.

**File:** `INDEX.md`

**File:** `LICENSE`

**File:** `Makefile`

**File:** `PRD.md`
  - **Description**: Master Project Requirements Document (PRD) defining product vision, target audience, core architectural principles ("AI Proposes, Mechanical Fortress Disposes"), functional requirements (FR-1 through FR-10), non-functional requirements (NFR-1 through NFR-5), database schema, operational workflows, and open collaboration guidelines for Monika domain-specific trading agent harness.

**File:** `pyproject.toml`

**File:** `pyrightconfig.json`

**File:** `pytest.ini`

**File:** `README.md`

**File:** `SECURITY.md`

**File:** `setup.bat`
  - **Description**: Shell / batch execution script.

**File:** `setup.sh`
  - **Description**: !/usr/bin/env bash

**File:** `skills-lock.json`
  - **Description**: Structured JSON data / schema definition.

**File:** `STRUCTURE.md`

### Folder: `.github`

**File:** `pull_request_template.md`
  - **Description**: Pull request verification checklist enforcing RiskGate integrity, paper trading validation, and credential protection.

#### Folder: `.github/ISSUE_TEMPLATE`

**File:** `bug_report.md`
  - **Description**: Structured bug reporting template with credential sanitization guidelines.

**File:** `feature_request.md`
  - **Description**: Feature proposal template incorporating capital safety criteria and RiskGate compatibility.

#### Folder: `.github/workflows`

**File:** `ci.yml`
  - **Description**: GitHub Actions CI pipeline executing Python linting (Ruff), automated test suites (Pytest), and frontend dashboard compilation.

### Folder: `deploy`

**File:** `docker-compose.vps.yml`
  - **Docstring**: Production Docker Compose configuration orchestrating PostgreSQL 16 with pgvector, MT5 Wine service, and Monika Trading Agent container on VPS.

**File:** `Dockerfile.mt5-wine`
  - **Docstring**: Production multi-stage Dockerfile bundling Wine, Xvfb virtual display, MetaTrader 5 terminal runner, and Python 3.11 runtime for headless Linux VPS execution.

**File:** `entrypoint_mt5.sh`
  - **Docstring**: Shell entrypoint script for initializing virtual X11 framebuffer (Xvfb), Wine environment, MT5 terminal bridge, and python runtime inside the container.

**File:** `vps_deployment_guide.md`
  - **Docstring**: Comprehensive VPS architecture, provisioning, deployment, container orchestration, and troubleshooting guide for running Monika 24/7 on Linux VPS.

### Folder: `docs`

  - **Description**: Documentation repository, system guides (`SETUP_GUIDE.md`), gradual migration roadmap (`ROADMAP_SRC_MONIKA.md`), comprehensive UI showcase screenshot assets, and the persistent `docs/ux-audit/` workstation evaluation ledger.
  - **Note**: Collapsed directory containing documentation, screenshots, and UX audit files.

### Folder: `scripts`

  - **Description**: Installation, testing, operational utility scripts (`update_economic_calendar.py`), scraper verification scripts (`scripts/check_scrapers/`), database state healing (`heal_kill_switch_state.py`), token auditing (`audit_token_usage.py`), benchmark evaluation suites (`benchmark_stage1_openrouter.py`, `benchmark_stage2_openrouter.py`, `benchmark_debate_openrouter.py`, `benchmark_news_classification_openrouter.py`), and `ux_audit_baseline_scan.py` automated baseline verification harness.
  - **Note**: Collapsed directory containing utility, benchmarking, and verification scripts.

### Folder: `typings`

  - **Description**: Static type stub definitions (`.pyi`) for C-extensions and external libraries to enable strict Pyright analysis without runtime suppressions.
  - **Subfolders**:
    - `typings/MetaTrader5`: C-extension type stub definitions (`__init__.pyi`).
    - `typings/bottleneck`: Fast NumPy array operations type stub definitions (`__init__.pyi`).
    - `typings/concurrent_log_handler`: Concurrent rotating file handler type stub definitions (`__init__.pyi`).
    - `typings/hmmlearn`: Hidden Markov Model machine learning type stub definitions (`__init__.pyi`, `hmm.pyi`).
    - `typings/ib_insync`: Interactive Brokers client type stub definitions (`__init__.pyi`).
    - `typings/mt5linux`: Linux-Wine bridge type stub definitions (`__init__.pyi`).
    - `typings/uvloop`: Fast asyncio event loop type stub definitions (`__init__.pyi`).
    - `typings/weasyprint`: PDF report generation type stub definitions (`__init__.pyi`).

### Folder: `src`

#### Folder: `src/monika`

**File:** `__init__.py`

#### Folder: `src/monika/core`

**File:** `__init__.py`

**File:** `exceptions.py`
  - **Docstring**: Core exception taxonomy for Monika quantitative trading platform with structured error codes and metadata.
  - **Classes**: `MonikaError`, `ConfigurationError`, `RiskViolationError`, `KillSwitchActiveError`, `ExecutionError`, `BrokerConnectionError`, `DataIngestionError`, `ModelInferenceError`, `AuthenticationError`, `CircuitBreakerOpenError`

**File:** `paths.py`
  - **Docstring**: Canonical application path resolution for Monika Trading Agent. Provides CWD-invariant absolute paths for data, logs, configs, and repository root.
  - **Functions**: `get_default_monika_home`, `get_repo_root`, `get_base_dir`, `get_data_dir`, `get_logs_dir`, `get_config_dir`, `get_profiles_dir`, `get_subagent_logs_dir`, `get_builtin_skills_dir`, `get_skills_dir`, `resolve_data_path`, `resolve_config_path`

##### Folder: `src/monika/core/config`

**File:** `settings.py`
  - **Docstring**: Global application settings loader with schema validation and environment resolution.
  - **Classes**: `Settings`
  - **Functions**: `load_settings`, `load_all_config`, `validate_config`

**File:** `schemas.py`
  - **Docstring**: Strongly typed Pydantic models for configuration validation.
  - **Classes**: `TradingAgentConfig`, `RiskConfig`, `ExecutionConfig`, `PaperTradingConfig`

**File:** `protocols.py`
  - **Docstring**: Decoupled configuration protocols and observer hooks.
  - **Classes**: `CredentialResolver`
  - **Functions**: `register_config_listener`, `notify_config_listeners`

**File:** `atomic_writer.py`
  - **Docstring**: Atomic YAML configuration writer with comment preservation, fsync, env-template protection, and automatic backups.
  - **Classes**: `AtomicConfigWriter`
  - **Functions**: `write`, `update_in_place`, `backup`

##### Folder: `src/monika/core/security`

**File:** `terminal_guard.py`
  - **Docstring**: Deterministic shell command analysis and execution safety guard.
  - **Classes**: `DenialCircuitBreaker`, `CommandSecurityViolationError`
  - **Functions**: `validate_command`, `assert_safe_read_path`, `assert_safe_write_path`

**File:** `credential_vault.py`
  - **Docstring**: Windows Credential Manager and AES-GCM / HMAC encrypted vault.
  - **Classes**: `CredentialVault`, `SensitiveMaskingFilter`
  - **Functions**: `get_secret`, `set_secret`, `delete_secret`, `mask_sensitive`, `create_opaque_handle`, `resolve_opaque_handle`

**File:** `ssrf_guard.py`
  - **Docstring**: Server-Side Request Forgery IP/hostname validation guard.
  - **Functions**: `validate_safe_url`, `is_ip_private_or_reserved`

**File:** `threat_detector.py`
  - **Docstring**: Real-time heuristic and signature-based threat detection engine.
  - **Classes**: `ThreatDetector`

**File:** `threat_scanner.py`
  - **Docstring**: Static and runtime prompt injection and malicious payload scanner.
  - **Classes**: `ThreatScanner`

##### Folder: `src/monika/core/telemetry`

**File:** `activity_logger.py`
  - **Docstring**: Structured activity logging with database fallback and abstract sink support.
  - **Classes**: `ActivityLogger`

**File:** `doctor.py`
  - **Docstring**: Backward-compatible diagnostic telemetry facade (canonical implementation in `monika.interfaces.cli.doctor`).
  - **Classes**: `DiagnosticItem`, `SystemDoctor`

**File:** `sinks.py`
  - **Docstring**: Abstract telemetry persistence sinks.
  - **Classes**: `TelemetrySink`
  - **Functions**: `get_telemetry_sink`, `set_telemetry_sink`

##### Folder: `src/monika/core/telemetry/tracing`

**File:** `tracer.py`
  - **Docstring**: Execution tracer and OpenTelemetry span coordinator.
  - **Classes**: `AgentTracer`, `Span`
  - **Functions**: `get_tracer`

**File:** `exporters.py`
  - **Docstring**: In-memory span ring-buffer exporter with auto-eviction.
  - **Classes**: `InMemorySpanExporter`

##### Folder: `src/monika/core/primitives`

**File:** `clock.py`
  - **Docstring**: Clock abstraction supporting UTC and point-in-time deterministic simulation.
  - **Functions**: `now`, `set_simulated_now`, `frozen_time`, `async_frozen_time`

**File:** `event_bus.py`
  - **Docstring**: Asynchronous priority event bus.
  - **Classes**: `EventBus`, `AppEvent`
  - **Functions**: `get_event_bus`

**File:** `retry.py`
  - **Docstring**: Deterministic async and sync exponential retry decorator.
  - **Functions**: `retryable`

**File:** `turn_marker.py`
  - **Docstring**: Deterministic turn marker tracking for agentic workflows.
  - **Classes**: `TurnMarker`

**File:** `prompt_primitives.py`
  - **Docstring**: Pure core prompt formatting and token estimation primitives.
  - **Functions**: `_flatten_system_prompt`, `estimate_tokens`

##### Folder: `src/monika/core/analytics`
- **Modules**:
  - `cost_tracker.py`: Real-time token consumption and inference expenditure tracker (`CostTracker`).
  - `chart_generator.py`: Candlestick chart generation and technical indicator overlay rendering (`generate_candlestick_chart`, `plot_candlesticks_with_smc`).
  - `paper_tracker.py`: Simulated paper execution portfolio tracker, realized payoff ratio metrics, and decay outcome logger (`PaperTracker`).
  - `trade_autopsy.py`: Post-trade forensic autopsy and degradation attribution engine (`TradeAutopsy`).
  - `edge_tracker.py`: Alpha strategy edge quantification and decaying expectancy tracker (`EdgeTracker`).
  - `specialist_tracker.py`: Domain specialist model performance and win-rate attribution monitor (`SpecialistTracker`).
  - `adversarial_outcome_tracker.py`: Adversarial counter-trade outcome recorder and bias tracking (`AdversarialOutcomeTracker`).
  - `token_auditor.py`: Per-turn token usage auditor and budget alert mechanism (`TokenAuditor`).

##### Folder: `src/monika/core/calibration`
- **Modules**:
  - `confidence_calibrator.py`: Platt scaling and isotonic regression confidence calibrator (`fit_platt_scaling`, `calibrate_probability`).
  - `cot_thresholds.py`: Chain-of-Thought calibration thresholds and regime boundaries (`CoTThresholdCalibrator`).
  - `prescreen_calibrator.py`: Multi-factor trade proposal pre-screening boundary calibrator (`PrescreenCalibrator`).

##### Folder: `src/monika/core/streaming`
- **Modules**:
  - `sanitizer.py`: Pure regex sanitization primitives for emoji and markdown scrubber isolation (`EMOJI_PATTERN`, `ASCII_EMOTICON_PATTERN`, `strip_emojis_and_emoticons`).
  - `stream_scrubber.py`: Stateful stream token scrubber with buffering and sliding-window regex sanitization (`StatefulStreamScrubber`).
  - `streaming_lease.py`: Concurrency lease manager for SSE and WebSocket token streams (`StreamingLeaseManager`).

##### Folder: `src/monika/core/validation`
- **Modules**:
  - `data_validator.py`: Market data freshness, schema, and NaN validation rules (`validate_data_freshness`).
  - `data_temporal_validator.py`: Temporal point-in-time timestamp alignment and lookahead bias validator (`TemporalValidator`).
  - `indicator_sanitizer.py`: Indicator output clamp and numerical sanity filter (`IndicatorSanitizer`).
  - `tool_response_validator.py`: Deterministic schema validation for agent tool execution payloads (`ToolResponseValidator`).

#### Folder: `src/monika/domain`

**File:** `__init__.py`

#### Folder: `src/monika/domain/entities`

- Pure domain entities and value objects decoupled from database ORM models.
- **Modules**:
  - `order_status.py`: Pure domain order status enumeration (`OrderStatus`, `InvalidOrderStateTransitionError`).
  - `order.py`: Pure domain order entity (`OrderEntity`).
  - `position.py`: Pure domain position entity (`PositionEntity`).
  - `trade_trigger.py`: Pure domain trade trigger entity (`TradeTriggerEntity`).
  - `snapshots.py`: Pure domain snapshots (`AccountSnapshot`, `ActivePositionSnapshot`, `SymbolExposure`, `CalendarRiskEvents`).

#### Folder: `src/monika/domain/risk`

**File:** `__init__.py`

**File:** `ports.py`
  - **Docstring**: Pure domain risk ports and protocols decoupling risk logic from database persistence.
  - **Classes**: `RiskDataProviderProtocol`, `InstrumentRegistryProtocol`, `ApprovalTransportProtocol`

**File:** `approval_transport.py`
  - **Docstring**: Cryptographic approval payload transport and canonical serialization primitives.
  - **Classes**: `ApprovalRequestPayload`, `ApprovalDecisionPayload`, `ApprovalTransport`

**File:** `trade_proposal.py`
  - **Docstring**: Canonical TradeProposal Domain Entity & Fortress Admission Validator.
  - **Classes**:
    - `TradeProposal`
    - `FortressAdmissionValidator`
      - *Methods*: `validate_proposal(proposal)`

**File:** `risk_gate.py`
  - **Docstring**: Canonical Mechanical Fortress RiskGate coordinator composing modular check mixins.
  - **Classes**:
    - `FortressRejectionReason`
    - `RiskGate`
      - *Methods*: `evaluate_proposal(proposal, current_positions, equity, daily_pnl)`, `evaluate(proposal, session)`, `is_paused()`, `pause()`, `resume()`

**Directory:** `evaluators/`
  - **Docstring**: Modular check evaluators decomposing RiskGate into cohesive rule domains.
  - **Files**:
    - `base.py`: Mixin base, dynamic model resolver, and trading day cutoff helpers (`_RiskGateMixinBase`, `resolve_model`, `get_trading_day_start`, `get_daily_risk_cutoff`).
    - `execution_checks.py`: Execution, position sizing, spread, duplicate, and loss cooldown checks (`RiskExecutionChecksMixin`).
    - `portfolio_checks.py`: Portfolio heat, drawdowns, multi-asset correlation, and copula tail risk checks (`RiskPortfolioChecksMixin`).
    - `market_checks.py`: Market session, news blackout, rollover, Schmitt regime, and VPIN toxicity checks (`RiskMarketChecksMixin`).
    - `intelligence_checks.py`: TimesFM forecast expectancy, evidence gate, bounded mandate, and edge status checks (`RiskIntelligenceChecksMixin`).

**File:** `position_sizing.py`
  - **Docstring**: Canonical Position Sizing Calculator with strict precision and tick size constraints.
  - **Classes**:
    - `InstrumentSpec`
    - `SizingResult`
    - `PositionSizer`
      - *Methods*: `calculate_lot_size(symbol, equity, stop_loss_pips, risk_pct)`

**File:** `correlation_matrix.py`
  - **Docstring**: Rolling correlation matrix calculation across multi-asset portfolios.
  - **Classes**:
    - `CorrelationMatrix`
      - *Methods*: `compute_matrix(returns_df)`, `get_correlated_pairs(threshold)`

**File:** `portfolio_correlation_gate.py`
  - **Docstring**: Portfolio correlation filtering and USD directional delta limits.
  - **Functions**: `filter_correlated_proposals(proposals, open_positions, matrix)`, `_get_usd_directional_delta(proposal, instrument)`

**File:** `portfolio_optimizer.py`
  - **Docstring**: Mathematical portfolio optimization (mean-variance, risk parity, Kelly).
  - **Classes**:
    - `OptimizationResult`
    - `PortfolioOptimizer`
      - *Methods*: `optimize(expected_returns, cov_matrix, constraints)`

**File:** `crypto_audit_ledger.py`
  - **Docstring**: Cryptographically hashed tamper-evident ledger for trade decisions.
  - **Classes**:
    - `CryptoAuditLedger`
      - *Methods*: `append_event(event_type, payload)`, `verify_chain()`
    - `LedgerTamperedError`

**File:** `approval_hub.py`
  - **Docstring**: Two-man rule and administrative trade approval workflows.
  - **Classes**:
    - `ApprovalRequest`
    - `ApprovalHub`
      - *Methods*: `request_approval(proposal)`, `approve(request_id)`, `reject(request_id)`

**File:** `pending_action.py`
  - **Docstring**: Crash-recovery pending order ledger.
  - **Classes**:
    - `PendingAction`
    - `PendingActionLedger`
      - *Methods*: `record_pending(action)`, `resolve_pending(action_id)`

**File:** `execution_simulator.py`
  - **Docstring**: Pure simulated execution environment for backtesting and paper validation.
  - **Classes**:
    - `ExecutionSimulator`
      - *Methods*: `simulate_fill(order, tick_data)`

**File:** `risk_rule_plugin.py`
  - **Docstring**: Modular pluggable risk rule interface.
  - **Classes**:
    - `RiskRulePlugin`
    - `RiskRulePipeline`
      - *Methods*: `register_rule(rule)`, `execute_all(context)`

#### Folder: `src/monika/domain/execution`

**File:** `__init__.py`

**File:** `broker_plugin.py`
  - **Docstring**: Abstract execution protocol for broker adapters.
  - **Classes**:
    - `BrokerPlugin`
      - *Methods*: `connect()`, `disconnect()`, `place_order(order)`, `cancel_order(ticket)`, `get_positions()`

**File:** `verification_engine.py`
  - **Docstring**: Evidence-first execution verification and telemetry assertions.
  - **Classes**:
    - `EvidenceFirstVerifier`
      - *Methods*: `verify_fill(order, ticket, broker_response)`

**File:** `order_emulator.py`
  - **Docstring**: Order lifecycle emulator for backtesting and paper trading.
  - **Classes**:
    - `OrderEmulator`
      - *Methods*: `process_order(order, tick)`

**File:** `state_machine.py`
  - **Docstring**: Formal state machine for order lifecycle transitions.
  - **Classes**:
    - `OrderStateMachine`
      - *Methods*: `transition(current_state, event)`

**File:** `order_creator.py`
  - **Docstring**: Pure domain factory for constructing verified orders from trade proposals.
  - **Classes**:
    - `OrderCreator`
      - *Methods*: `create_order(proposal, spec)`

**File:** `sizing_calculator.py`
  - **Docstring**: Execution sizing calculator adhering to broker lot step constraints.
  - **Classes**:
    - `SizingCalculator`
      - *Methods*: `clamp_volume(volume, min_lot, max_lot, step)`

**File:** `base.py`
  - **Docstring**: Base interfaces and dataclasses for execution domain.
  - **Classes**:
    - `ExecutionPluginBase`

#### Folder: `src/monika/domain/indicators`

**File:** `__init__.py`

**File:** `factor_primitives.py`
  - **Docstring**: Pure mathematical factor primitives (rolling moments, ranking, decay, safe division).
  - **Functions**: `safe_div(a, b)`, `ts_mean(s, d)`, `ts_std(s, d)`, `ts_min(s, d)`, `ts_max(s, d)`, `ts_rank(s, d)`

**File:** `microstructure.py`
  - **Docstring**: Market microstructure metrics (VPIN, Kyle's Lambda, Roll effective spread, Amihud illiquidity).
  - **Functions**: `calculate_vpin_fractional(df)`, `calculate_roll_effective_spread(df)`, `calculate_kyles_lambda_ols(df)`, `calculate_amihud_illiquidity_mt5(df)`

**File:** `econometrics.py`
  - **Docstring**: Time series econometrics (Ornstein-Uhlenbeck, Engle-Granger cointegration, EVT tail risk).
  - **Functions**: `fit_ornstein_uhlenbeck(series)`, `test_cointegration(s1, s2)`

#### Folder: `src/monika/domain/indicators/alpha_zoo`

**File:** `__init__.py`
  - **Docstring**: Monika Quantitative Alpha Zoo: Factor registry, metadata, and auto-registration.

**File:** `registry.py`
  - **Docstring**: Central factor registry and factory for 900+ quantitative alpha formulas.
  - **Classes**:
    - `FactorRegistry`
      - *Methods*: `register(meta)`, `get(name)`, `list_factors()`, `compute(name, df)`
    - `RegistryError`

**File:** `meta.py`
  - **Docstring**: Alpha formula metadata specifications and categorical taxonomy.
  - **Classes**:
    - `AlphaMeta`
    - `AlphaCategory`
    - `AlphaDirection`

**File:** `vector_factor_engine.py`
  - **Docstring**: High-performance vectorized alpha factor evaluator.
  - **Classes**:
    - `VectorFactorEngine`
      - *Methods*: `evaluate(df, factors, regime)`
    - `VectorFactorResult`
    - `FactorSignal`

**File:** `qlib158.py`
  - **Docstring**: Microsoft Qlib 158 continuous alpha factor formulations for MT5.

**File:** `alpha101.py`
  - **Docstring**: WorldQuant 101 alpha formulations adapted for continuous MT5 data.

**File:** `academic_factors.py`
  - **Docstring**: Academic literature alpha factors (Carhart, Fama-French, Jegadeesh-Titman).

**File:** `microstructure_factors.py`
  - **Docstring**: High-frequency order flow and microstructure alpha formulations.

**File:** `fundamental_factors.py`
  - **Docstring**: Macroeconomic and fundamental indicator alpha formulations.

#### Folder: `src/monika/domain/market`
- **Modules**:
  - `session_info.py`: Trading session definitions and active market session detection (`get_current_market_session`, `MarketSession`).
  - `dynamic_correlation.py`: Dynamic rolling EWMA and Pearson asset correlation calculator (`compute_cross_asset_macro_correlation`, `get_dynamic_correlation`).
  - `currency_utils.py`: Currency pair decomposition, base/quote extraction, and triangulation utilities (`CurrencyUtils`).
  - `swap_estimator.py`: Broker swap and rollover cost estimation engine (`SwapEstimator`).
  - `direction.py`: Directional mapping and signal polarity normalization (`DirectionHelper`).
  - `bias_utils.py`: Market directional bias calculation and agreement metric utilities (`BiasUtils`).
  - `news_impact_keywords.py`: Macroeconomic news impact dictionary and keyword classifier (`NewsImpactClassifier`).

#### Folder: `src/monika/application`

**File:** `__init__.py`

##### Folder: `src/monika/application/agent`

**File:** `__init__.py`
**File:** `agent_loop.py`
  - **Docstring**: Central System Agent Loop for conversational autonomy and ad-hoc single-asset LangGraph analytical pipeline triggers.
  - **Classes**:
    - `SystemAgentLoop`
      - *Methods*: `execute_ad_hoc_analysis(symbol, sender_id, message_id, channel, broadcast_callback, is_paper, extra_context)`
**File:** `chat_agent.py`
  - **Docstring**: Conversational Trading Assistant coordinating LLM reasoning, Chronicle context injection, and dual-signature approval transports.
  - **Classes**:
    - `ChatAgent`
      - *Methods*: `handle_message(message, session, session_id, token_callback)`

**File:** `chat_compaction.py`
  - **Docstring**: Micro-Compaction for Cognitive Chat Sessions preserving user messages verbatim.
  - **Classes**:
    - `ChatMicroCompactor`
      - *Methods*: `compact_history(messages)`

**File:** `chat_tool_router.py`
  - **Docstring**: Progressive tool loading for cognitive chat agents reducing token overhead.
  - **Classes**:
    - `ChatToolRouter`
      - *Methods*: `get_tools_for_query(query, available_tools)`

**File:** `startup_checks.py`
  - **Docstring**: Pre-flight system and environment verification suite.
  - **Classes**:
    - `StartupChecker`
      - *Methods*: `run_all_checks()`, `check_database()`, `check_mt5()`
**File:** `task_registry.py`
  - **Docstring**: Autonomous task registration and lifecycle supervision registry.
  - **Classes**:
    - `TaskRegistry`
      - *Methods*: `register_task(task_def)`, `start_all()`, `stop_all()`
**File:** `turn_tool_round.py`
  - **Docstring**: LLM multi-turn tool calling orchestration, parameter deduplication, and execution verdict synthesis.
  - **Classes**:
    - `TurnToolRound`
      - *Methods*: `normalize_and_partition(raw_tool_calls)`, `execute_tool_round(raw_tool_calls, tool_executor_fn)`

##### Folder: `src/monika/application/analysis`

- Core framework for multi-agent analytical orchestration, execution harness, prefetch pipelines, MCP integration, stages, subagents, and deterministic trade gating.
- **Subpackages**:
  - `arbitration/`: Trade signal arbitration and conflict resolution engine (`SignalArbitrator`).
  - `calculators/`: Domain quantitative algorithms and statistical estimators (`AdaptivePolicyEngine`, `CointegrationCalculator`, `DailyRangeCalculator`, `FactorICCalculator`, `GARCHVolatilityCalculator`, `HierarchicalRiskParity`, `HMMRegimeClassifier`, `InvariantCalculator`, `SeasonalityCalculator`, `TimesFMResidualValidator`, `UniversalMacroAnalyzer`).
  - `debate/`: Adversarial dialectic multi-agent consensus protocols, dialectic convergence, and cross-examination judges (`DialecticDebateEngine`, `DebateOrchestrator`, `DebateJudge`, `AdversarialConsensus`).
  - `grounding/`: Factual citation and provenance tagging (`DeclaredFiguresTracker`, `ProvenanceTagger`, `SurgicalRedactor`).
  - `harness/`: Autonomous agent execution harness, token budgeting, error classification, and stop gates (`AgentHarness`, `TradeStopGates`).
  - `journal/`: Behavioral diagnostics and trade reflection attribution (`AttributionEngine`, `JournalParser`).
  - `mcp/`: Model Context Protocol client/server infrastructure and tool servers (`MCPClient`, `MCPServer`, `ExcelServer`, `SqliteServer`).
  - `memory/`: Recursive episodic memory, outcome linking, crystallized trade reflection, and skill crystallizers (`OutcomeLinker`, `TradeReflector`, `SkillCrystallizer`, `PlaybookLedger`, `EpisodicMemory`).
  - `prefetch/`: Market data, macro indicators, and sentiment prefetching pipelines (`Stage1Prefetcher`, `Stage2Prefetcher`, `PrefetchPipeline`, `NewsDigest`).
  - `research/`: Macroeconomic regime playbooks and playbook runners (`MacroPlaybookRunner`).
  - `schemas/`: Pydantic data validation and payload schemas for analytical outputs.
  - `stages/`: Multi-stage analytical pipeline execution (`FundamentalStage`, `PerAssetStage`, `ContextBuilder`, `PerAssetRunner`).
  - `strategies/`: Quantitative alpha signal generation engines, institutional SMC/FVG models, statistical arbitrage pairs, and auto-synthesized dynamic strategies (`StrategyRegistry`, `EdgeStrategy`, `EdgeSignal`, `SMCFVGStrategy`, `BBVolumeProfileStrategy`, `XTIPairsReadiness`, `SynthesizedStrategy`).
  - `subagent/`: Isolated subagent spawner, lifecycle manager, and blackboard communication (`SubagentBlackboard`, `SubagentSpawner`).
  - `tools/`: Dynamic tool registry, multi-tier execution environments (in-process, persistent kernel, Docker), domain tools (market data, macro, trade intel, SMC, quant, news, sentiment, code execution, terminal), and tool security dispatchers (`ToolRegistry`, `UnifiedToolRegistry`, `ToolExecutor`, `BaseToolHandler`, `Tier1InProcessEnvironment`, `Tier2KernelEnvironment`, `Tier3DockerEnvironment`).
  - `validators/`: Market data sanity, confluence verification, and precommit risk gates (`PrecommitGate`, `ConfluenceVerifier`, `CoreDataValidator`).
- **Core Modules**:
  - `event_broadcaster.py`: Real-time WebSocket streaming of analysis steps and trade decisions.
  - `pipeline_plugin.py` & `macro_pipeline_plugin.py`: Extensible stage plugin lifecycle hooks.
  - `prompt_sections.py`: Dynamic context assembler for multi-agent prompt construction.
  - `scenario_tree.py`: Scenario expansion and risk probability tree evaluation.

##### Folder: `src/monika/application/graph`

**File:** `__init__.py`
**File:** `workflow.py`
  - **Docstring**: Primary LangGraph StateGraph compiler and conditional workflow orchestrator for Monika multi-agent deliberation.
  - **Functions**: `build_trading_graph(settings, checkpointer)`
**File:** `state.py`
  - **Docstring**: LangGraph TypedDict cognitive state definitions and tombstoned deep merger primitives.
  - **Classes**: `TradingState`, `AgentState`
  - **Functions**: `merge_dicts(a, b)`, `merge_lists(a, b)`
**File:** `reactive_graph.py`
  - **Docstring**: Event-driven reactive execution graph engine with adaptive pipeline routing.
  - **Classes**:
    - `ReactiveGraphEngine`
      - *Methods*: `run_step(event, state)`
**File:** `team_compiler.py`
  - **Docstring**: Multi-agent team topology compiler binding specialized agent nodes into executable LangGraph subgraphs.
  - **Functions**: `compile_multi_agent_team(agent_configs, settings)`
**File:** `grounding.py`
  - **Docstring**: Deterministic factual market data grounding and OHLCV markdown context builder.
  - **Classes**:
    - `GroundingContextBuilder`
      - *Methods*: `build_market_context(symbol, df, tf)`

#### Folder: `src/monika/application/services`

**File:** `__init__.py`

**File:** `trading_service.py`
  - **Docstring**: Canonical Trading & Order Execution Application Service. Enforces pre-trade confirmation token lifecycle, mechanical fortress risk validation, and paper mode isolation.
  - **Classes**:
    - `OrderPreviewResult`
    - `TradeExecutionResult`
    - `TradingService`
      - *Methods*: `generate_preview_token(symbol, action, volume, expires_at)`, `verify_preview_token(token, symbol, action, volume, expires_at)`, `preview_manual_order(session, symbol, action, volume, entry_price, stop_loss, take_profit, is_paper)`, `submit_order(session, symbol, action, volume, entry_price, stop_loss, take_profit, is_paper, preview_token, token_expires_at, actor, broker_adapter)`, `close_position(session, ticket, reason, actor, broker_adapter)`, `emergency_kill(session, reason, actor)`

**File:** `portfolio_service.py`
  - **Docstring**: Canonical Portfolio & Position Application Service. Consolidates position queries, performance metrics, and order history across UI layers.
  - **Classes**:
    - `PortfolioService`
      - *Methods*: `get_open_positions(session, symbol, is_paper)`, `get_closed_positions(session, limit, symbol, is_paper)`, `get_portfolio_metrics(session, is_paper)`, `get_active_orders(session, symbol, limit)`, `get_portfolio_exposure(session, is_paper)`

**File:** `market_intel_service.py`
  - **Docstring**: Canonical Market Intelligence & Alpha Application Service. Bridges OHLCV data to VectorFactorEngine alpha evaluation.
  - **Classes**:
    - `AlphaEvaluationResult`
      - *Methods*: `to_prompt_context()`
    - `MarketIntelService`
      - *Methods*: `evaluate_alpha_factors(symbol, df, regime, top_k)`, `get_economic_calendar_events(session, currencies, impact_levels, limit)`

**File:** `general_harness_service.py`
  - **Docstring**: Canonical General Agent Harness Application Service. Exposes partitioned toolsets and tool schemas for multi-purpose agent invocation.
  - **Classes**:
    - `GeneralHarnessService`
      - *Methods*: `get_toolset_names(toolset)`, `get_toolset_schema(toolset, format)`, `execute_tool(tool_name, params, context)`

**File:** `market_data_service.py`
  - **Docstring**: Canonical Market Data Application Service providing uniform symbol quotes, ticks, and candle access with MT5, DB, and Yahoo Finance cascade.
  - **Classes**:
    - `MarketDataService`
      - *Methods*: `get_latest_quote(symbol, container)`, `get_bars(symbol, timeframe, count, container)`

**File:** `system_status_service.py`
  - **Docstring**: Canonical System Status Application Service aggregating component health, broker connectivity, DB latency, and runtime telemetry.
  - **Classes**:
    - `SystemStatusService`
      - *Methods*: `get_status(session, broker)`

##### Folder: `src/monika/application/execution`

- Order execution orchestration, broker registry, effect gating, health supervision, and multi-account coordination.
- **Modules**:
  - `execution_service.py`: High-level execution coordinator linking trade proposals to broker execution (`ExecutionService`).
  - `broker_registry.py`: Dynamic registry of active broker adapters and execution routing (`BrokerRegistry`).
  - `effect_gate.py`: Real-world effect verification, dry-run safety gates, and live execution confirmation (`EffectGate`).
  - `health_check.py`: Continuous broker connection, latency, and margin health monitoring (`BrokerHealthChecker`).
  - `service/order_executor.py`: Low-level atomic order dispatcher and status tracker (`OrderExecutor`).
  - `service/order_lifecycle_service.py`: Orchestrates pure domain state transitions, DB session flush, event store emit, and event bus publishing (`OrderLifecycleService`).
  - `service/position_synchronizer.py`: Real-time position reconciliation between local database and broker state (`PositionSynchronizer`).
  - `service/reconciliation.py`: Periodic trade and fill reconciliation ledger (`ExecutionReconciliation`).
  - `service/risk_evaluator.py`: Pre-execution risk sanity check, realized payoff Kelly scaling, and sizing gatekeeper (`RiskEvaluatorMixin`).
  - `service/self_healing_executor.py`: Automated retry, failover, and order recovery engine (`SelfHealingExecutor`).
  - `service/trade_confirm.py`: Dual-token trade confirmation and user approval verification (`TradeConfirmationManager`).
  - `service/emergency_manager.py`: Emergency liquidation and position halt coordinator (`EmergencyExecutionManager`).
  - `service/multi_account_adapter.py`: Multi-broker, multi-account routing and allocation adapter (`MultiAccountAdapter`).

##### Folder: `src/monika/application/agent/harness`

- Autonomous agent turn loop harness, context compressor, state guards, structured output extraction, and error classifiers.
- **Modules**:
  - `agent_harness.py`: Core multi-turn execution harness (`AgentHarness`, `calculate_turn_cost_usd`).
  - `harness_state.py`: Execution state tracking and checkpoint boundaries (`HarnessState`).
  - `context_compressor.py`: Turn context window compression and trimming (`ContextCompressor`).
  - `error_classifier.py`: Structured error categorization and retry policies (`classify_harness_error`).
  - `stall_guard.py` & `repetition_guard.py`: Infinite loop and repetitive action guards (`StallGuard`, `RepetitionGuard`).
  - `structured_output.py`: Schema extraction and validation from model outputs (`extract_structured_output`).
  - `trade_stop_gates.py`: Invariant safety and trade stop execution barriers (`TradeStopGates`).

##### Folder: `src/monika/application/plugins/engine`

- Microkernel plugin execution engine, contract definitions, lifecycle supervision, and functional runner adapters.
- **Modules**:
  - `contract.py`: Plugin specifications, state enums, and runner protocol contracts (`TradingPlugin`, `PluginMetadata`, `PluginState`).
  - `engine.py`: Dynamic plugin lifecycle and dependency engine (`PluginEngine`, `get_plugin_engine`).
  - `context.py`: Sandboxed execution context provided to loaded plugins (`PluginContext`).
  - `lifecycle.py`: Controlled draining, hot-reload, and replacement coordinator (`ReplacementCoordinator`).
  - `installer.py`: Dynamic package installation and catalog status manager (`get_community_catalog`).
  - `adapters/functional_adapter.py`: Functional adapter bridging callables and tools into microkernel plugins (`FunctionalPluginBridge`).

##### Folder: `src/monika/application/skills`

- Autonomous agent capability modules, dynamic skill loader, curation pipeline, continuous learning, and runtime hub.
- **Modules**:
  - `loader.py`: Skill manifest discovery, validation, and metadata loading (`SkillLoader`, `SkillMetadata`).
  - `skill_manager.py`: Dynamic skill lifecycle and execution manager (`SkillManager`).
  - `skills_hub.py`: Central skill registry and inter-agent skill sharing hub (`SkillsHub`).
  - `skills_guard.py`: Skill security guard and execution permission verifier (`SkillsGuard`).
  - `unified_runtime.py`: Unified skill runtime environment for agent workflows (`UnifiedSkillRuntime`).
  - `continuous_learning.py`: Automated post-trade skill refinement and optimization tracker (`ContinuousLearningEngine`).
  - `curator.py`: Skill synthesis, curation, and quality pruning (`SkillCurator`).
  - `usage_tracker.py`: Skill invocation metrics and token efficiency analytics (`SkillUsageTracker`).

##### Folder: `src/monika/application/governance`

- Run manifest generation, cryptographic runtime fingerprinting, and post-trade reproducibility audit engine.
- **Modules**:
  - `run_manifest.py`: Cryptographic SHA-256 fingerprinting of directives, dependency versions, git commits, and runtime environments (`RunManifest`, `RunManifestGenerator`).

##### Folder: `src/monika/application/scheduler`

- Universal cron orchestration, market session cycle schedulers, NLP cron expression parsing, and autonomous background monitors.
- **Modules**:
  - `unified_cron_engine.py`: Unified Cron Engine executing at-most-once scheduled tasks, monitor hash suppression, and multi-channel delivery (`UnifiedCronEngine`, `CronJobRecord`).
  - `cycle_scheduler.py`: Market session and scheduled pipeline runner coordinating analytical tasks (`CycleScheduler`).
  - `graph_cycle_scheduler.py`: LangGraph analytical cycle runner triggering periodic asset analyses (`GraphCycleScheduler`).
  - `cron_nlp_parser.py`: Natural language cron parser converting trading session expressions to cron schedules (`parse_natural_schedule`).
  - `trailing_stop_manager.py`: Dynamic trailing stop, volatility adjustments, and breakeven protection manager (`TrailingStopManager`).
  - `trigger_checker.py`: Real-time price trigger evaluation, condition matching, and order lifecycle execution (`TriggerChecker`).
  - `active_calendar_poller.py`: Real-time economic calendar poller for high-impact news window detection (`ActiveCalendarPoller`).
  - `alpha_discovery_scheduler.py`: Automated walk-forward alpha discovery, parameter search, and strategy candidate evaluation (`AlphaDiscoveryScheduler`).
  - `edge_strategy_runner.py`: Continuous edge strategy evaluator and signal generator (`EdgeStrategyRunner`).
  - `flash_crash_detector.py`: Real-time anomalous market movement and flash crash detector (`FlashCrashDetector`).
  - `macro_data_scheduler.py`: Periodic macroeconomic data ingestion and indicator synchronization scheduler (`MacroDataScheduler`).
  - `market_data_scheduler.py`: Multi-timeframe bar ingestion and price data scheduler (`MarketDataScheduler`).
  - `news_watcher.py`: Continuous news and sentiment ingestion scheduler (`NewsWatcher`).
  - `order_reconciler.py`: Broker order execution reconciler and terminal position tracker (`OrderReconciler`).
  - `playbook_curator.py`: Automated strategy playbook maintenance and performance curation (`PlaybookCurator`).
  - `position_guardian.py` & `position_supervisor.py`: Position risk supervision and emergency protection monitors (`PositionGuardian`, `PositionSupervisor`).
  - `strategy_synthesis_scheduler.py`: Automated LLM-driven quantitative strategy synthesis and code generation scheduler (`StrategySynthesisScheduler`).
  - `task_plugin.py`: Standardized modular task plugin interface for background scheduler extensions (`TaskPlugin`, `LegacySchedulerWrapper`).
  - `wall_clock.py`: Wall clock scheduling helper and ISO time parser (`parse_time_list`, `is_time_within_window`).

##### Folder: `src/monika/application/backtest`

- Institutional walk-forward engine, point-in-time backtesting, statistical validation, and multi-asset replay simulation.
- **Modules**:
  - `walk_forward_engine.py`: Anchored and rolling walk-forward optimization with Purged K-Fold validation (`WalkForwardEngine`, `WalkForwardResult`).
  - `point_in_time_engine.py`: Research-to-live parity replay engine with zero-lookahead next_bar.open execution and simulated broker adapter (`PointInTimeBacktestEngine`).
  - `outcome_evaluator.py`: Quantitative trade outcome evaluator, dynamic friction modeling, and asset friction profiles (`OutcomeEvaluator`, `ASSET_FRICTION_PROFILE`).
  - `monte_carlo_engine.py`: Institutional Monte Carlo stress tester, scenario shock engine, and probability of ruin simulator (`MonteCarloStressTester`).
  - `alpha_validation.py`: Rigorous alpha hypothesis validation against statistical tests, cost stresses, and split-half tests (`validate_alpha`, `AlphaValidation`).
  - `isolated_strategy_harness.py`: Strictly isolated, zero-lookahead historical bar-by-bar evaluation harness for EdgeStrategy subclasses (`IsolatedStrategyBacktestHarness`, `ZeroLookaheadSliceSession`).
  - `statistical_tests.py`: Financial econometrics battery including Deflated Sharpe Ratio (DSR), Probabilistic Sharpe Ratio (PSR), and sample moments (`deflated_sharpe_ratio`, `probabilistic_sharpe_ratio`).
  - `matrix_alignment.py`: High-performance multi-asset synchronous matrix alignment and resampling (`MatrixAligner`, `AlignedMarketMatrices`).
  - `offline_signal_engine.py`: Offline vector signal computation with lookahead bias prevention (`OfflineSignalEngine`).
  - `batch_scenario_runner.py`: Parallelized batch backtesting across multiple symbols and market regimes (`BatchScenarioRunner`).
  - `benchmark_tracker.py`: Real-time benchmark index performance tracking and relative alpha measurement (`BenchmarkTracker`).
  - `decision_memory.py`: Learning loop memory logger for historical decisions and backtest reflections (`DecisionMemoryManager`).
  - `report_generator.py`: Comprehensive tear-sheet and performance metrics report generator (`generate_backtest_report`).
  - `run_card.py`: Immutable run card manifest generator capturing backtest metadata and reproducibility data (`RunCardGenerator`, `RunCard`).
  - `time_machine.py`: Deterministic temporal state rewind and replay utility (`TimeMachine`).
  - `engines/`: Asset-specific backtest execution engines (`CryptoBacktestEngine`, `EquityBacktestEngine`, `ForexBacktestEngine`, `FuturesBacktestEngine`).

##### Folder: `src/monika/application/evals`

- LLM offline evaluations, behavioral oracles, and hostile market probing.
- **Modules**:
  - `eval_runner.py`: Offline A/B evaluation runner and prompt variant regression testing (`ABEvalRunner`).
  - `hostile_market_probe.py`: Adversarial scenario generator testing agent resilience against stress, flash crashes, and extreme slippage (`HostileMarketProbe`).
  - `simulation_clock.py`: Deterministic virtual clock for asynchronous time machine simulations (`SimulationClock`).
  - `eval_metrics.py`: Standardized offline evaluation metrics, semantic scoring, and agreement calculators (`calculate_eval_metrics`).
  - `runner.py`: Automated scenario evaluation suite and oracle runner (`run_evals`).
  - `oracles/`: Specialized deterministic validation oracles (`ToolSafetyOracle`, `RiskComplianceOracle`, `TradeDisciplineOracle`, `MacroRegimeOracle`, `SMCGeometryOracle`).

##### Folder: `src/monika/application/benchmark`

- LLM benchmarking framework, role-based evaluation harness, ELO arena, GEPA prompt evolution, and judge consensus ensemble.
- **Modules**:
  - `runner.py`: End-to-end benchmark execution engine (`BenchmarkRunner`, `BenchmarkCase`).
  - `alpha_arena.py`: Head-to-head ELO tournament arena for alpha strategies and model comparisons (`AlphaArena`).
  - `judge.py`: Multi-persona consensus LLM judge ensemble (`ConsensusJudge`, `JudgeEnsemble`).
  - `invoker.py`: Resilient LLM client invoker with token telemetry and drift tracking (`LLMInvoker`).
  - `task_specs.py`: Standardized benchmark task specifications across 53 trading agent roles (`TASK_SPECS`).
  - `prompt_evolution.py`: Genetic Evolutionary Prompt Adaptation (GEPA) engine for trading prompts (`GEPAPromptEvolver`).
  - `system_one_scorer.py`: System-1 intuitive latency and calibration scoring engine (`SystemOneScorer`).
  - `paired_evaluator.py`: Statistical paired model evaluation and bootstrap significance testing (`PairedEvaluator`).
  - `token_drift_tracker.py`: Semantic drift and token consumption variance monitor (`TokenDriftTracker`).
  - `trade_trajectory_logger.py`: High-fidelity multi-turn agent decision trajectory recorder (`TradeTrajectoryLogger`).
  - `model_registry.py`: Canonical trading LLM model metadata, tier classification, and capability registry (`MODEL_REGISTRY`).
  - `deterministic.py`: Deterministic mock providers and reproducible replay harnesses (`DeterministicMockProvider`).
  - `fixture_loader.py`: Golden dataset and historical market scenario fixture loader (`FixtureLoader`).
  - `db_models.py` & `db_access.py`: Benchmark run result persistence models and repository access (`BenchmarkResult`).
  - `pricing.py`: Provider token cost calculation and margin accounting (`calculate_cost`).
  - `report.py`: Leaderboard summary and comparative markdown report generation (`generate_benchmark_report`).
  - `config.py`: Benchmark framework configuration and hyperparameter settings (`BenchmarkConfig`).

##### Folder: `src/monika/application/plugins`

- Modular plugin framework, dynamic lifecycle management, and built-in plugin implementations.
- **Modules**:
  - `kernel.py`: Universal trading plugin kernel and lifecycle coordinator (`PluginKernel`).
  - `loader.py`: Safe dynamic plugin discovery, validation, and loading mechanism (`PluginLoader`).
  - `manifest.py`: Plugin metadata and dependency manifest verification (`PluginManifest`).
  - `brokers/`: Built-in execution broker plugins (`MT5LocalBrokerPlugin`, `PaperTradingBrokerPlugin`).
  - `analysis_pipelines/`: Built-in macro-to-asset and scalping analysis pipelines (`MacroToAssetPipeline`, `TechnicalScalpingPipeline`).
  - `alerts/`: Notification and operational alert plugins (`DiscordAlertPlugin`).
  - `indicators/`: Custom quantitative indicator plugins (`CustomIndicatorPlugin`).
  - `scrapers/`: Modular external web and market scraper plugins (`ExampleScraperPlugin`).
  - `manager/`: Dynamic plugin management, hook lifecycle dispatch, and tool registration (`PluginManager`, `ExtensionLoader`).

##### Folder: `src/monika/application/protocol`

- Cross-agent communication protocols, SSVP consensus, context coherence, and anti-contamination guards.
- **Modules**:
  - `brief_contamination_guard.py`: Brief isolation and contamination prevention filter (`BriefContaminationGuard`).
  - `ssvp_coordinator.py`: Structured Specialist Verification Protocol coordinator (`SSVPCoordinator`).
  - `context_coherence.py`: Multi-turn context coherence and divergence metric calculator (`compute_brief_price_divergence`).
  - `cross_agent_sync.py`: Asynchronous state synchronization across concurrent agent instances (`CrossAgentSync`).
  - `enhanced_cds.py`: Enhanced Contextual Decision Support protocol (`EnhancedCDSProtocol`).
  - `coherence_flag_tracker.py`: Semantic coherence flag tracking and alert monitor (`CoherenceFlagTracker`).

##### Entrypoints & Daemon

- Master application bootstrap, daemon orchestrator, and CLI runner.
- **Modules**:
  - `bootstrap.py`: Master asynchronous system runtime bootstrapper, network monkeypatches, and environment preparation (`bootstrap_system`).
  - `main.py`: Main operational trading agent daemon and multi-service lifecycle orchestrator (`TradingAgentDaemon`).
  - `run_benchmark.py`: Standalone CLI entrypoint for running benchmark suites and tournament evals (`main`).

#### Folder: `src/monika/infrastructure`

**File:** `__init__.py`

##### Folder: `src/monika/infrastructure/brokers`

**File:** `broker_adapter.py`
  - **Docstring**: Unified Broker Adapter Interface & Implementations.
  - **Classes**: `BrokerAdapter` (ABC), `SimulatedBrokerAdapter`, `OrderResult`, `PositionInfo`, `AccountInfo`

**File:** `mt5_client.py`
  - **Docstring**: Production MT5 Client with auto-reconnection and robust order execution.
  - **Classes**: `MT5Client`

**File:** `ibkr_adapter.py`
  - **Docstring**: Interactive Brokers (IBKR) execution adapter with graceful fallback.
  - **Classes**: `IBKRAdapter`

**File:** `paper_tracker.py`
  - **Docstring**: Deterministic Paper Trading Position and State Tracker.
  - **Classes**: `PaperTracker`

**File:** `approval_transport.py`
  - **Docstring**: Dual-Signature Cryptographic Approval Transport.
  - **Classes**: `ApprovalTransport`, `ApprovalRequestPayload`, `ApprovalDecisionPayload`

**File:** `audit_logger.py`
  - **Docstring**: Append-only tamper-evident execution audit logging.
  - **Classes**: `ExecutionAuditLogger`

##### Folder: `src/monika/infrastructure/credentials`

**File:** `credential_pool.py`
  - **Docstring**: LLM API Credential Pooling, rate limiting, and failure backoff.
  - **Classes**: `CredentialPool`, `CredentialKey`

**File:** `error_taxonomy.py`
  - **Docstring**: Standardized Trading and LLM Provider Error Taxonomy.
  - **Classes**: `TradingErrorCode`, `FailoverReason`, `ProviderErrorDetails`

##### Folder: `src/monika/infrastructure/database`

**File:** `db.py`
  - **Docstring**: Canonical async database engine, sessionmaker, and Alembic initialization lifecycle.
  - **Classes**: `AsyncSessionLocal`
  - **Functions**: `get_engine`, `get_session`, `get_write_session`, `get_sessionmaker`, `init_db`, `get_canonical_db_path`

**File:** `models.py`
  - **Docstring**: Canonical SQLAlchemy ORM declarative models including numeric financial fields (NUMERIC) and operational tables.
  - **Classes**: `Base`, `Trade`, `Order`, `Position`, `PriceOHLCV`, `AssetAnalysis`, `PaperTradeRecord`, `EquityDrawdownSnapshot`, `RiskState`, `CronJob`, `OutboxDelivery`, `DeliveryRecord`, `SessionToolRecord`, `RepairLedger`, `ScheduledJob`, `JobDelivery`

**File:** `engine.py`
  - **Docstring**: SQLAlchemy async and sync database engines and session factories.
  - **Classes**: `DatabaseManager`
  - **Functions**: `get_async_engine`, `get_session_factory`, `init_db`

**File:** `session_db_wal.py`
  - **Docstring**: High-performance SQLite WAL session database with bounded read pool and lock guards.
  - **Classes**: `SessionDbWal`, `SessionDbReadPool`, `FileLockGuard`

**File:** `session_db.py`
  - **Docstring**: SQLite WAL session database manager with automatic checkpointing.
  - **Classes**: `SessionDatabase`

**File:** `sqlite_concurrency.py`
  - **Docstring**: Concurrency primitives and BEGIN IMMEDIATE transactions for SQLite.
  - **Functions**: `safe_commit`, `safe_db_op`

##### Folder: `src/monika/infrastructure/database/domain_models`

**File:** `base.py`
  - **Docstring**: SQLAlchemy Declarative Base and common model mixins.
  - **Classes**: `Base`

**File:** `positions.py`
  - **Docstring**: Position tracking ORM models.
  - **Classes**: `Position`

**File:** `trade_proposals.py`
  - **Docstring**: Trade proposal audit ORM models.
  - **Classes**: `TradeProposal`

**File:** `activity_logs.py`
  - **Docstring**: Activity and audit log ORM models.
  - **Classes**: `ActivityLog`

##### Folder: `src/monika/infrastructure/database/repositories`

**File:** `risk_repository.py`
  - **Docstring**: Pure SQLAlchemy risk data provider fulfilling RiskDataProviderProtocol.
  - **Classes**: `SqlAlchemyRiskRepository`

**File:** `position_repository.py`
  - **Docstring**: Position CRUD repository.
  - **Classes**: `PositionRepository`

**File:** `trade_proposal_repository.py`
  - **Docstring**: Trade proposal repository.
  - **Classes**: `TradeProposalRepository`

##### Folder: `src/monika/infrastructure/data_ingestion`

**File:** `__init__.py`

###### Folder: `src/monika/infrastructure/data_ingestion/sources`

**File:** `__init__.py`
**File:** `base_fetcher.py`
  - **Docstring**: Base data fetcher interface with retry and database persistence primitives.
  - **Classes**: `BaseFetcher`
**File:** `dxy_yfinance.py`
  - **Docstring**: US Dollar Index (DXY) settlement series fetcher via resilient 3-tier pipeline.
  - **Classes**: `DXYFetcher`
**File:** `vix_yfinance.py`
  - **Docstring**: CBOE Volatility Index (VIX) fetcher via 4-tier resilient pipeline.
  - **Classes**: `VIXFetcher`
**File:** `cftc_cot.py`
  - **Docstring**: CFTC Commitments of Traders (COT) report fetcher and parser.
  - **Classes**: `CFTCCotFetcher`
**File:** `treasury_yields.py`
  - **Docstring**: US Treasury Constant Maturity Yields data fetcher via FRED API.
  - **Classes**: `TreasuryYieldsFetcher`

###### Folder: `src/monika/infrastructure/data_ingestion/scrapers`

**File:** `__init__.py`
**File:** `base_scraper.py`
  - **Docstring**: Headless browser automation base scraper powered by DrissionPage.
  - **Classes**: `BaseScraper`
**File:** `scraper_factory.py`
  - **Docstring**: Factory for instantiating web and macro scrapers.
  - **Classes**: `ScraperFactory`
**File:** `playwright_scraper.py`
  - **Docstring**: Async Playwright fallback scraper for dynamic web pages.
  - **Classes**: `PlaywrightScraper`

####### Folder: `src/monika/infrastructure/data_ingestion/scrapers/calendar`

**File:** `calendar_forexfactory.py`
  - **Docstring**: High-speed economic calendar scraper via FairEconomy JSON feed with local caching.
  - **Classes**: `ForexFactoryCalendarScraper`
**File:** `calendar_investing.py`
  - **Docstring**: Investing.com economic calendar scraper with anti-bot bypass and failover.
  - **Classes**: `InvestingCalendarScraper`

####### Folder: `src/monika/infrastructure/data_ingestion/scrapers/macro`

**File:** `central_bank_doc_scraper.py`
  - **Docstring**: Multi-central bank statement and minutes scraper (Fed, ECB, BoJ) with sentiment polarity scoring.
  - **Classes**: `CentralBankDocScraper`
**File:** `bank_indonesia.py`
  - **Docstring**: Bank Indonesia monetary policy and macro indicator scraper.
  - **Classes**: `BankIndonesiaFetcher`
**File:** `sovereign_yield_spreads.py`
  - **Docstring**: Global sovereign bond yield spreads scraper and calculator.
  - **Classes**: `SovereignYieldSpreadsScraper`

##### Folder: `src/monika/infrastructure/graph/checkpointers`

**File:** `__init__.py`
**File:** `sqlite_checkpointer.py`
  - **Docstring**: Hardened local SQLite checkpoint saver with WAL mode and high-concurrency pragmas.
  - **Classes**: `SqliteCheckpointSaver`
**File:** `dual_checkpointer.py`
  - **Docstring**: Dual-write LangGraph checkpointer orchestrating Primary (PostgreSQL) and Secondary (SQLite) persistence.
  - **Classes**: `DualCheckpointSaver`

##### Folder: `src/monika/infrastructure/ml`

**File:** `timesfm_engine.py`
  - **Docstring**: TimesFM 2.5 Zero-Shot Foundation Model inference engine.
  - **Classes**: `TimesFMEngine`

##### Folder: `src/monika/infrastructure/providers`

**File:** `provider_registry.py`
  - **Docstring**: Central registry mapping provider keys to provider implementations.
  - **Classes**: `ProviderRegistry`

**File:** `universal_provider.py`
  - **Docstring**: Unified LLM provider backend wrapper with failover and thinking scrubbers.
  - **Classes**: `UniversalProvider`

**File:** `llm_factory.py`
  - **Docstring**: Factory for creating configured LLM provider instances.
  - **Classes**: `LLMFactory`

##### Folder: `src/monika/infrastructure/sandboxes`

**File:** `base.py`
  - **Docstring**: Sandbox backend interface.
  - **Classes**: `SandboxBackend` (ABC)

**File:** `docker_backend.py`
  - **Docstring**: Isolated Docker execution container sandbox.
  - **Classes**: `DockerSandbox`

**File:** `local_backend.py`
  - **Docstring**: Local sub-process execution sandbox with resource constraints.
  - **Classes**: `LocalSandbox`

**File:** `pty_bridge.py`
  - **Docstring**: Canonical interactive PTY session manager and async pseudo-terminal bridge.
  - **Classes**: `PtySession`, `PtyBridgeManager`
  - **Functions**: `get_pty_bridge_manager`

##### Folder: `src/monika/infrastructure/llm/rate_limiting`
- **Modules**:
  - `gemini_rate_limiter.py`: Google Gemini API rate limiter and token bucket controller (`GeminiRateLimiter`).
  - `claude_rate_limiter.py`: Anthropic Claude API rate limiter and token quota coordinator (`ClaudeRateLimiter`).
  - `groq_rate_limiter.py`: Groq Cloud inference rate limiter (`GroqRateLimiter`).
  - `openrouter_rate_limiter.py`: OpenRouter multi-model rate limiter (`OpenRouterRateLimiter`).
  - `credential_pool.py`: API key rotation, cooldown, and health tracking pool (`CredentialPool`).
  - `credit_balance_tracker.py`: Real-time API balance and credit usage tracker (`CreditBalanceTracker`).
  - `http_retry.py`: Exponential backoff HTTP request executor (`fetch_with_retry`).

##### Folder: `src/monika/infrastructure/mcp`
- **Modules**:
  - `client.py`: Model Context Protocol client manager with auto-discovery and tool bridging (`McpClientManager`).
  - `server.py`: Monika native MCP server exposing tools over stdio/HTTP (`MonikaMcpServer`).
  - `protocol.py`: JSON-RPC 2.0 protocol definitions and serializer (`JsonRpcRequest`, `JsonRpcResponse`).
  - `dispatcher.py`: Event and notification dispatcher for MCP servers.
  - `mcp_schema_cache.py`: On-disk caching of MCP tool schemas for instant startup (`McpSchemaCache`).
  - `mcp_death_supervisor.py`: Process supervisor ensuring orphaned MCP subprocesses terminate (`McpDeathSupervisor`).
  - `servers/`: Pre-packaged native MCP servers (`excel_server`, `fetch_server`, `filesystem_server`, `google_sheets_server`, `sqlite_server`).

##### Folder: `src/monika/infrastructure/notifications`
- **Modules**:
  - `notifier.py`: Unified notification router dispatching to configured channels (`Notifier`).
  - `discord_notifier.py`: Discord webhook notification dispatcher with rate-limiting (`DiscordNotifier`).

##### Folder: `src/monika/infrastructure/infra`
- **Modules**:
  - Backward-compatibility facades preserving historical imports for canonical components:
    `container.py` -> `monika.core.container`,
    `platform_compat.py` -> `monika.core.platform`,
    `env_file_manager.py` -> `monika.core.config.env_file_manager`,
    `log_redactor.py` -> `monika.core.security.log_redactor`,
    `db_backup.py` -> `monika.infrastructure.database.backup`,
    `discord_notifier.py` / `notifier.py` -> `monika.infrastructure.notifications`,
    `worktree_manager.py` -> `monika.infrastructure.sandboxes.worktree_manager`.

##### Folder: `src/monika/infrastructure/llm`
- **Modules**:
  - `caveman_compressor.py`: Deterministic token-saving prompt and tool output compressor (`compress_tool_payload`).
  - `llmlingua_compressor.py`: Selective token and sentence pruning compressor (`LLMLinguaCompressor`).
  - `context_compressor.py`: Context window trimming and multi-turn summary generator (`ContextCompressor`).
  - `embedding.py`: Google Gemini dense vector embedding generation service (`generate_gemini_embedding`).
  - `semantic_cache.py`: High-performance cosine similarity semantic response cache (`SemanticCache`).
  - `model_capabilities.py`: Context window, reasoning tokens, and structured output capability registry (`ModelCapabilities`).
  - `prompt_tiering.py` & `prompt_tiers.py`: Dynamic tiered prompt assembly and token budget allocator (`PromptTierManager`).

##### Folder: `src/monika/infrastructure/storage`
- **Modules**:
  - `journal_helper.py`: Obsidian Dataview & spreadsheet trading journal formatting and persistence helper (`format_dataview_journal`, `format_spreadsheet_row`, `record_trade_to_workspace`).
  - `spill_store.py`: Large tool output and state payload spillover storage with content-addressable hashes (`SpillStore`).

#### Folder: `src/monika/interfaces`

**File:** `__init__.py`

##### Folder: `src/monika/interfaces/cli`
- **Modules**:
  - `main.py`: Canonical entrypoint (`monika` CLI) dispatching daemon, doctor, chat, tui, and admin subcommands.
  - `tui.py`: Terminal User Interface built with Textual for live monitoring and manual trading operations.
  - `doctor.py`: Offline/online environment health check diagnostics.
  - `chat/`: Interactive conversational trading assistant (`prompt.py`, `renderer.py`, `session.py`, `completer.py`).
  - `subcommands/`: Modular CLI handlers (`daemon.py`, `trading.py`, `simulation.py`, `mcp.py`, `upgrade.py`, `runcard.py`).

##### Folder: `src/monika/interfaces/dashboard`
- **Modules**:
  - `api.py`: FastAPI application server orchestrating WebSocket telemetry, REST APIs, strict CORS origin controls (`localhost:5173`, `127.0.0.1:5173`), and modern SPA frontend static file resolution.
  - `rbac.py`: Role-Based Access Control enforcing role boundaries (ADMIN, TRADER, VIEWER).
  - `pty_bridge.py`: WebSocket pseudo-terminal bridge for web console execution.
  - `routes/`: Modular API endpoints (`trading.py` synchronized batch close contracts, `config.py`, `system.py`, `intelligence.py`, `backtest.py`, `benchmark.py`, `tokens.py`, `websocket.py`).

##### Folder: `src/monika/interfaces/gateway`
- **Modules**:
  - `api_server.py`: OpenAI-compatible API server (`/v1/chat/completions`) with origin validation and RBAC-protected PTY terminal websocket.
  - `acp_server.py`: Agent Communication Protocol server.
  - `channel_router.py`: Omnichannel message multiplexing and dispatching across external protocols.
  - `webhook_ingress.py`: Cryptographically signed HMAC-SHA256 webhook ingress with replay window protection.
  - `platforms/`: Adapter integrations (`telegram_adapter.py`, `discord_adapter.py`, `slack_adapter.py`, `webhook_adapter.py`).

##### Folder: `src/monika/interfaces/telegram`
- **Modules**:
  - `base.py`: Type-checking base mixin declaring static properties and cross-mixin signatures (`_TelegramBotMixinBase`).
  - `bot.py`: Coordinator Telegram bot controller composing formatters, command handlers, and media/callback mixins with token-bucket outbound queue, RetryAfter backoff, offline disk buffer, and unbypassable authorization guard (`TelegramBot`, `TelegramController`).
  - `formatters/`: Modular message builders and text chunkers (`TelegramFormatterMixin`, `text_builders.py`).
  - `handlers/`: Domain command handlers and media/callback dispatchers (`TelegramTradingCommandsMixin`, `TelegramMarketCommandsMixin`, `TelegramSystemCommandsMixin`, `TelegramAdminCommandsMixin`, `TelegramCallbackHandlerMixin`, `TelegramMediaHandlerMixin`).
  - `command_router.py`: Command routing and RBAC authorization guard for Telegram.
  - `routers/`: Modular domain sub-routers (`trading_router.py`, `risk_router.py`, `market_router.py`, `quant_router.py`, `admin_router.py`).
  - `voice_handler.py`: Multimodal voice note processing, transcription, and command confirmation.
  - `message_formatter.py`: HTML message templates, slips, and financial cards.

##### Folder: `src/monika/interfaces/workspace`
- **Modules**:
  - `journal_helper.py`: Dataview markdown formatters, Obsidian trade log templates, and workspace synchronizer (`format_dataview_journal`).

