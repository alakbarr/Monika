# Comprehensive Codebase Index: Monika (MT5 Trading Agent)

This document provides an exhaustive structural index of all directories, files, functions, classes, data models, and runtime variables within the Monika quantitative trading platform.

## Table of Contents
*(Note: Line numbers are auto-updated by `scripts/update_index_toc.py`)*

- [Root Directory: `/trading-agent`](#root-directory-trading-agent) - Line 127
  - [Folder: `.github`](#folder-github) - Line 153
    - [Folder: `.github/workflows`](#folder-githubworkflows) - Line 155
    - [Folder: `.github/ISSUE_TEMPLATE`](#folder-githubissue_template) - Line 159
  - [Folder: `deploy`](#folder-deploy) - Line 168
  - [Folder: `docs`](#folder-docs) - Line 182
    - [Folder: `docs/images`](#folder-docsimages) - Line 184
  - [Folder: `scripts`](#folder-scripts) - Line 206
  - [Folder: `trading-agent`](#folder-trading-agent) - Line 243
    - [Folder: `trading-agent/systemd`](#folder-trading-agentsystemd) - Line 289
    - [Folder: `trading-agent/cli`](#folder-trading-agentcli) - Line 293
      - [Folder: `trading-agent/cli/overlays`](#folder-trading-agentclioverlays) - Line 424
    - [Folder: `trading-agent/benchmark`](#folder-trading-agentbenchmark) - Line 433
      - [Folder: `trading-agent/benchmark/results`](#folder-trading-agentbenchmarkresults) - Line 482
    - [Folder: `trading-agent/evals`](#folder-trading-agentevals) - Line 497
      - [Folder: `trading-agent/evals/oracles`](#folder-trading-agentevalsoracles) - Line 516
      - [Folder: `trading-agent/evals/fixtures`](#folder-trading-agentevalsfixtures) - Line 527
    - [Folder: `trading-agent/agent`](#folder-trading-agentagent) - Line 534
      - [Folder: `trading-agent/agent/monitors`](#folder-trading-agentagentmonitors) - Line 558
    - [Folder: `trading-agent/analysis`](#folder-trading-agentanalysis) - Line 573
      - [Folder: `trading-agent/analysis/harness`](#folder-trading-agentanalysisharness) - Line 594
      - [Folder: `trading-agent/analysis/grounding`](#folder-trading-agentanalysisgrounding) - Line 648
      - [Folder: `trading-agent/analysis/subagent`](#folder-trading-agentanalysissubagent) - Line 655
      - [Folder: `trading-agent/analysis/arbitration`](#folder-trading-agentanalysisarbitration) - Line 667
      - [Folder: `trading-agent/analysis/stages`](#folder-trading-agentanalysisstages) - Line 675
        - [Folder: `trading-agent/analysis/stages/per_asset`](#folder-trading-agentanalysisstagesper_asset) - Line 687
      - [Folder: `trading-agent/analysis/validators`](#folder-trading-agentanalysisvalidators) - Line 710
      - [Folder: `trading-agent/analysis/calculators`](#folder-trading-agentanalysiscalculators) - Line 743
      - [Folder: `trading-agent/analysis/tools`](#folder-trading-agentanalysistools) - Line 776
        - [Folder: `trading-agent/analysis/tools/quant_sandbox`](#folder-trading-agentanalysistoolsquant_sandbox) - Line 834
        - [Folder: `trading-agent/analysis/tools/kernel`](#folder-trading-agentanalysistoolskernel) - Line 841
        - [Folder: `trading-agent/analysis/tools/domain`](#folder-trading-agentanalysistoolsdomain) - Line 860
        - [Folder: `trading-agent/analysis/tools/handlers`](#folder-trading-agentanalysistoolshandlers) - Line 882
      - [Folder: `trading-agent/analysis/schemas`](#folder-trading-agentanalysisschemas) - Line 927
      - [Folder: `trading-agent/analysis/stages`](#folder-trading-agentanalysisstages-1) - Line 933
      - [Folder: `trading-agent/analysis/strategies`](#folder-trading-agentanalysisstrategies) - Line 943
        - [Folder: `trading-agent/analysis/strategies/synthesized`](#folder-trading-agentanalysisstrategiessynthesized) - Line 970
      - [Folder: `trading-agent/analysis/prefetch`](#folder-trading-agentanalysisprefetch) - Line 995
      - [Folder: `trading-agent/analysis/debate`](#folder-trading-agentanalysisdebate) - Line 1016
      - [Folder: `trading-agent/analysis/validators`](#folder-trading-agentanalysisvalidators-1) - Line 1065
      - [Folder: `trading-agent/analysis/providers`](#folder-trading-agentanalysisproviders) - Line 1081
      - [Folder: `trading-agent/analysis/memory`](#folder-trading-agentanalysismemory) - Line 1165
      - [Folder: `trading-agent/analysis/mcp`](#folder-trading-agentanalysismcp) - Line 1273
        - [Folder: `trading-agent/analysis/mcp/servers`](#folder-trading-agentanalysismcpservers) - Line 1288
    - [Folder: `trading-agent/backtest`](#folder-trading-agentbacktest) - Line 1300
    - [Folder: `trading-agent/graph`](#folder-trading-agentgraph) - Line 1418
      - [Folder: `trading-agent/graph/nodes`](#folder-trading-agentgraphnodes) - Line 1427
    - [Folder: `trading-agent/config`](#folder-trading-agentconfig) - Line 1454
    - [Folder: `trading-agent/data_sources`](#folder-trading-agentdata_sources) - Line 1517
    - [Folder: `trading-agent/database`](#folder-trading-agentdatabase) - Line 1666
      - [Folder: `trading-agent/database/domain_models`](#folder-trading-agentdatabasedomain_models) - Line 1917
      - [Folder: `trading-agent/database/migrations`](#folder-trading-agentdatabasemigrations) - Line 1942
        - [Folder: `trading-agent/database/migrations/archive`](#folder-trading-agentdatabasemigrationsarchive) - Line 1951
        - [Folder: `trading-agent/database/migrations/versions`](#folder-trading-agentdatabasemigrationsversions) - Line 1954
    - [Folder: `trading-agent/evals`](#folder-trading-agentevals-1) - Line 1960
      - [Folder: `trading-agent/evals/oracles`](#folder-trading-agentevalsoracles-1) - Line 1975
      - [Folder: `trading-agent/evals/fixtures`](#folder-trading-agentevalsfixtures-1) - Line 1983
    - [Folder: `trading-agent/execution`](#folder-trading-agentexecution) - Line 1992
      - [Folder: `trading-agent/execution/backends`](#folder-trading-agentexecutionbackends) - Line 2193
      - [Folder: `trading-agent/execution/service`](#folder-trading-agentexecutionservice) - Line 2203
      - [Folder: `trading-agent/execution/ea_bridge`](#folder-trading-agentexecutionea_bridge) - Line 2292
    - [Folder: `trading-agent/graph`](#folder-trading-agentgraph-1) - Line 2316
      - [Folder: `trading-agent/graph/checkpointers`](#folder-trading-agentgraphcheckpointers) - Line 2347
      - [Folder: `trading-agent/graph/nodes`](#folder-trading-agentgraphnodes-1) - Line 2359
        - [Folder: `trading-agent/graph/nodes/debate`](#folder-trading-agentgraphnodesdebate) - Line 2371
    - [Folder: `trading-agent/indicators`](#folder-trading-agentindicators) - Line 2452
    - [Folder: `trading-agent/logging_observability`](#folder-trading-agentlogging_observability) - Line 2525
      - [Folder: `trading-agent/logging_observability/reporting`](#folder-trading-agentlogging_observabilityreporting) - Line 2594
      - [Folder: `trading-agent/logging_observability/tracing`](#folder-trading-agentlogging_observabilitytracing) - Line 2607
      - [Folder: `trading-agent/logging_observability/dashboard`](#folder-trading-agentlogging_observabilitydashboard) - Line 2623
        - [Folder: `trading-agent/logging_observability/dashboard/routes`](#folder-trading-agentlogging_observabilitydashboardroutes) - Line 2700
        - [Folder: `trading-agent/logging_observability/dashboard/frontend`](#folder-trading-agentlogging_observabilitydashboardfrontend) - Line 2733
          - [Folder: `trading-agent/logging_observability/dashboard/frontend/src`](#folder-trading-agentlogging_observabilitydashboardfrontendsrc) - Line 2741
            - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/charts`](#folder-trading-agentlogging_observabilitydashboardfrontendsrccomponentscharts) - Line 2748
            - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/layout`](#folder-trading-agentlogging_observabilitydashboardfrontendsrccomponentslayout) - Line 2755
            - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/panels`](#folder-trading-agentlogging_observabilitydashboardfrontendsrccomponentspanels) - Line 2763
              - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/panels/config`](#folder-trading-agentlogging_observabilitydashboardfrontendsrccomponentspanelsconfig) - Line 2785
              - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/panels/graph`](#folder-trading-agentlogging_observabilitydashboardfrontendsrccomponentspanelsgraph) - Line 2789
              - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/panels/tokens`](#folder-trading-agentlogging_observabilitydashboardfrontendsrccomponentspanelstokens) - Line 2796
            - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/ui`](#folder-trading-agentlogging_observabilitydashboardfrontendsrccomponentsui) - Line 2800
            - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/hooks`](#folder-trading-agentlogging_observabilitydashboardfrontendsrchooks) - Line 2828
            - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/lib`](#folder-trading-agentlogging_observabilitydashboardfrontendsrclib) - Line 2834
            - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/store`](#folder-trading-agentlogging_observabilitydashboardfrontendsrcstore) - Line 2839
            - [Folder: `trading-agent/logging_observability/dashboard/frontend/src/types`](#folder-trading-agentlogging_observabilitydashboardfrontendsrctypes) - Line 2842
    - [Folder: `trading-agent/plugins`](#folder-trading-agentplugins) - Line 2845
      - [Folder: `trading-agent/plugins/alerts/discord_alert`](#folder-trading-agentpluginsalertsdiscord_alert) - Line 2860
      - [Folder: `trading-agent/plugins/indicators/custom_indicator`](#folder-trading-agentpluginsindicatorscustom_indicator) - Line 2865
      - [Folder: `trading-agent/plugins/scrapers/example_scraper`](#folder-trading-agentpluginsscrapersexample_scraper) - Line 2870
    - [Folder: `trading-agent/provider`](#folder-trading-agentprovider) - Line 2875
    - [Folder: `trading-agent/risk`](#folder-trading-agentrisk) - Line 2890
      - [Folder: `trading-agent/risk/invariants`](#folder-trading-agentriskinvariants) - Line 2984
    - [Folder: `trading-agent/security`](#folder-trading-agentsecurity) - Line 3003
    - [Folder: `trading-agent/scheduler`](#folder-trading-agentscheduler) - Line 3013
    - [Folder: `trading-agent/scrapers`](#folder-trading-agentscrapers) - Line 3317
      - [Folder: `trading-agent/scrapers/calendar`](#folder-trading-agentscraperscalendar) - Line 3349
      - [Folder: `trading-agent/scrapers/macro`](#folder-trading-agentscrapersmacro) - Line 3385
      - [Folder: `trading-agent/scrapers/news`](#folder-trading-agentscrapersnews) - Line 3397
      - [Folder: `trading-agent/scrapers/sentiment`](#folder-trading-agentscraperssentiment) - Line 3523
      - [Folder: `trading-agent/scrapers/social`](#folder-trading-agentscraperssocial) - Line 3550
    - [Folder: `trading-agent/skills`](#folder-trading-agentskills) - Line 3568
      - [Folder: `trading-agent/skills/crystallized`](#folder-trading-agentskillscrystallized) - Line 3611
      - [Folder: `trading-agent/skills/trading`](#folder-trading-agentskillstrading) - Line 3616
    - [Folder: `trading-agent/telegram_bot`](#folder-trading-agenttelegram_bot) - Line 3662
    - [Folder: `trading-agent/utils`](#folder-trading-agentutils) - Line 4091
      - [Folder: `trading-agent/utils/analytics`](#folder-trading-agentutilsanalytics) - Line 4121
      - [Folder: `trading-agent/utils/calibration`](#folder-trading-agentutilscalibration) - Line 4154
      - [Folder: `trading-agent/utils/protocol`](#folder-trading-agentutilsprotocol) - Line 4160
      - [Folder: `trading-agent/utils/api`](#folder-trading-agentutilsapi) - Line 4175
      - [Folder: `trading-agent/utils/validation`](#folder-trading-agentutilsvalidation) - Line 4202
      - [Folder: `trading-agent/utils/llm`](#folder-trading-agentutilsllm) - Line 4211
      - [Folder: `trading-agent/utils/market`](#folder-trading-agentutilsmarket) - Line 4290
      - [Folder: `trading-agent/utils/plugins`](#folder-trading-agentutilsplugins) - Line 4319
      - [Folder: `trading-agent/utils/infra`](#folder-trading-agentutilsinfra) - Line 4329
      - [Folder: `trading-agent/utils/scheduling`](#folder-trading-agentutilsscheduling) - Line 4358
      - [Folder: `trading-agent/utils/streaming`](#folder-trading-agentutilsstreaming) - Line 4368
      - [Folder: `trading-agent/utils/security`](#folder-trading-agentutilssecurity) - Line 4377
      - [Folder: `trading-agent/utils/typesafe`](#folder-trading-agentutilstypesafe) - Line 4390
      - [Folder: `trading-agent/utils/storage`](#folder-trading-agentutilsstorage) - Line 4415

## Root Directory: `/trading-agent`

**File:** `.dockerignore`
**File:** `.env.example`
**File:** `.gitignore`
**File:** `AGENTS.md`
**File:** `CHANGELOG.md`
**File:** `CODE_OF_CONDUCT.md`
**File:** `CONTRIBUTING.md`
**File:** `contoh_pertanyaan.md`
**File:** `DESIGN.md`
**File:** `Dockerfile`
**File:** `docker-compose.yml`
**File:** `GEMINI.md`
**File:** `INDEX.md`
**File:** `LICENSE`
**File:** `Makefile`
**File:** `prompt_benchmark.md`
  - **Description**: Architectural benchmarking specifications and multi-agent upgrade directives for Monika quantitative trading agent.
**File:** `pyproject.toml`
**File:** `pyrightconfig.json`
**File:** `pytest.ini`
**File:** `README.md`
**File:** `SECURITY.md`
**File:** `STRUKTUR.md`

### Folder: `.github`

#### Folder: `.github/workflows`
**File:** `ci.yml`
  - **Description**: GitHub Actions CI pipeline executing Python linting (Ruff), automated test suites (Pytest), and frontend dashboard compilation.

#### Folder: `.github/ISSUE_TEMPLATE`
**File:** `bug_report.md`
  - **Description**: Structured bug reporting template with credential sanitization guidelines.
**File:** `feature_request.md`
  - **Description**: Feature proposal template incorporating capital safety criteria and RiskGate compatibility.

**File:** `pull_request_template.md`
  - **Description**: Pull request verification checklist enforcing RiskGate integrity, paper trading validation, and credential protection.

### Folder: `deploy`

**File:** `Dockerfile.mt5-wine`
  - **Docstring**: Production multi-stage Dockerfile bundling Wine, Xvfb virtual display, MetaTrader 5 terminal runner, and Python 3.11 runtime for headless Linux VPS execution.

**File:** `docker-compose.vps.yml`
  - **Docstring**: Production Docker Compose configuration orchestrating PostgreSQL 16 with pgvector, MT5 Wine service, and Monika Trading Agent container on VPS.

**File:** `entrypoint_mt5.sh`
  - **Docstring**: Shell entrypoint script for initializing virtual X11 framebuffer (Xvfb), Wine environment, MT5 terminal bridge, and python runtime inside the container.

**File:** `vps_deployment_guide.md`
  - **Docstring**: Comprehensive VPS architecture, provisioning, deployment, container orchestration, and troubleshooting guide for running Monika 24/7 on Linux VPS.

### Folder: `docs`

#### Folder: `docs/images`
**File:** `01_trading_desk_overview.png`
  - **Description**: High-resolution showcase screenshot of the main Trading Desk Overview with real-time portfolio telemetry, equity curve, and open positions.
**File:** `02_trading_desk_signals.png`
  - **Description**: Showcase screenshot of the Signals & Triggers Matrix highlighting latency benchmarks and active conditional triggers.
**File:** `03_trading_desk_market.png`
  - **Description**: Showcase screenshot of Live Market Data featuring real MT5 tick feeds, VIX volatility gauge, and macroeconomic event calendar.
**File:** `04_market_intelligence_pipeline_dag.png`
  - **Description**: Showcase screenshot of the LangGraph 7-node autonomous decision pipeline DAG visualizer.
**File:** `05_market_intelligence_macro_brief.png`
  - **Description**: Showcase screenshot of the AI-synthesized Macroeconomic Intelligence Brief.
**File:** `06_ledger_risk_limits.png`
  - **Description**: Showcase screenshot of the Hard Risk Limits & Circuit Breakers panel with analog VU meters.
**File:** `07_ledger_llm_token_audit.png`
  - **Description**: Showcase screenshot of the LLM Token Audit & Cost Economics panel with prompt caching telemetry.
**File:** `08_telegraph_desk_console_chat.png`
  - **Description**: Showcase screenshot of the Phosphor CRT Telegraph Desk Console with human-in-the-loop trade authorization.
**File:** `09_system_configuration.png`
  - **Description**: Showcase screenshot of the Dynamic System Configuration and YAML editor panel.
**File:** `10_terminal_ui_tui.png`
  - **Description**: Showcase screenshot of the Textual Terminal UI (TUI) running in headless terminal environment.

### Folder: `scripts`

**File:** `generate_model_quadrant.py`
  - **Docstring**: Script to generate standalone interactive HTML quadrant visualization for LLM models.
  - **Functions**:
    - `clean_num(val: str, default: float = 0.0) -> float`
    - `parse_csv(filepath: str)`
    - `compute_stats(models)`
    - `generate_html(models, stats, output_path: str)`
    - `main()`
**File:** `generate_showcase_screenshots.py`
  - **Docstring**: Ephemeral FastAPI mock server and headless Chrome automation script for capturing high-resolution dashboard screenshots.
  - **Functions**:
    - `find_chrome_path() -> str`
    - `run_mock_server(port: int = 8899)`
    - `capture_screenshots(port: int = 8899)`
    - `main()`
**File:** `update_index_toc.py`
**File:** `download_timesfm_weights.py`
  - **Docstring**: Script to download Google TimesFM 3.0 model weights using HF_TOKEN.
**File:** `deep_dependency_audit.py`
  - **Docstring**: Exhaustive dependency scanner checking AST imports, dynamic imports, and try-except blocks across codebase.
**File:** `fix_venv_entrypoints.py`
  - **Docstring**: Utility script to repair and regenerate virtualenv console_scripts launcher stubs on Windows to current Python path.
**File:** `reset_paper_trades.py`
  - **Docstring**: CLI utility to safely reset paper trading history, clear loss streaks to 0, unlock suspensions, and auto-backup JSON.
  - **Functions**:
    - `main()`
**File:** `install.ps1`
  - **Docstring**: Windows one-click installer automating isolated virtual environment setup, core dependencies, and setup doctor inspection.
**File:** `install.sh`
  - **Docstring**: Linux VPS one-click installer automating system dependencies, isolated virtual environment setup, core requirements, and setup doctor inspection.
**File:** `run_tests.bat`
  - **Docstring**: Isolated Windows test runner script. Sanitizes runtime environment, strips live credentials, enforces mock trading flags, and executes pytest test suite.
**File:** `run_tests.sh`
  - **Docstring**: Isolated Linux/macOS test runner script. Sanitizes runtime environment, strips live credentials, enforces mock trading flags, and executes pytest test suite.

### Folder: `trading-agent`

**File:** `bootstrap.py`
  - **Docstring**: Cross-platform pre-flight bootstrap and network hardening module. Performs early environment stabilization, stream UTF-8 encoding configuration, console flashing suppression on Windows, and RFC 8305 Happy Eyeballs socket racing to prevent IPv6 routing latency hangs on external API calls.
  - **Functions**:
    - `bootstrap_runtime()`
    - `race_dual_stack_socket(host, port, timeout_ms=250)`

**File:** `main.py`
  - **Global Variables**: logger, BANNER, PERMANENT_ERRORS, LONG_RETRY_ERRORS, CORE_TRADING_TASKS, CLEAN_SHUTDOWN_FLAG
  - **Functions**:
    - `mark_clean_shutdown()`
      - *Docstring*: Write clean shutdown flag file to signal run scripts not to auto-restart.
    - `run_startup_checks()`
      - *Docstring*: Run all startup health checks.
    - `_run_with_restart()`
    - `release_single_instance_lock()`
      - *Docstring*: Explicitly release single instance PID lock file.
    - `main()`
      - *Docstring*: Synchronous entry point.
  - **Classes**:
    - `TradingAgent`
      - *Docstring*: Top-level orchestrator that owns and coordinates all subsystems.
      - *Methods*:
        - `__init__(self)`
        - `_init_components(self)`
        - `_register_signals(self)`
        - `request_fallback_consent(self)`
        - `_post_restart_recovery(self)`
        - `_run_mt5_health_monitor(self)`
        - `_run_risk_parameter_reloader(self)`
        - `stop(self)`

**File:** `spesifikasi_final_ai_trading_agent.md`
  - **Description**: Master technical architecture blueprint and system specification (SSOT). Details the production architecture: multi-provider LLM fabric with 8-tier fallback, LangGraph StateGraph, multi-agent dialectical debate, quantitative edge strategies, Google TimesFM 3.0 deep learning, 4-tier memory, 18+ concurrent schedulers/guardians, 10-layer deterministic risk gate, MT5 EA dead-man switch, 50+ tool catalog, 35+ PostgreSQL models, and observability stack.
**File:** `start_agent.bat`
  - **Description**: Primary Windows startup script. Initializes MT5 terminal from `MT5_PATH` (preserving spaced directory paths), launches Vite Dashboard Frontend (localhost:5173), executes Alembic database migrations via `python -m alembic upgrade head`, and boots the agent inside a resilient auto-restart loop (`python -m cli.main run`). Supports execution flags: `start_agent.bat` (paper mode, default) or `start_agent.bat live`.
**File:** `start_agent.sh`
  - **Description**: Linux/macOS startup script. Launches MT5 via Wine if available (preserving spaced directory paths), boots the Dashboard Frontend, executes Alembic migrations via `python -m alembic upgrade head`, and manages the agent auto-restart loop (`python -m cli.main run`). Supports flags `bash start_agent.sh` (paper) or `bash start_agent.sh live`.
**File:** `stop_agent.bat`
  - **Description**: Windows shutdown script. Terminates active Python agent processes, Vite frontend dev server (port 5173), and MetaTrader 5 terminal (`terminal64.exe`).
**File:** `run_benchmark.py`

**File:** `docker-compose.linux.yml`
  - **Description**: Production Docker Compose configuration for Linux/Ubuntu VPS deployment (PostgreSQL asyncpg + isolated Monika MT5 Trading Agent runtime).

#### Folder: `trading-agent/systemd`
**File:** `tradeagent.service`
  - **Description**: Production systemd service unit file configuring Monika MT5 Trading Agent as a background daemon on Linux/Ubuntu VPS hosts.

#### Folder: `trading-agent/cli`
**File:** `__init__.py`

**File:** `main.py`
  - **Global Variables**: logger, DEFAULT_API_URL, TradingAgent, acquire_single_instance_lock, run_startup_checks
  - **Functions**:
    - `parse_args(args_list=None)`
      - *Docstring*: Parse CLI arguments for trading mode, subcommands (run, status, pause, resume, kill, positions, unsuspend, tui, chat, config, sessions, logs, doctor, setup, profile, mcp-serve), and optional config.
    - `_acli_run(args)`
      - *Docstring*: Asynchronous CLI execution pipeline.
    - `_cmd_status(args)`
      - *Docstring*: Show system status, flags, and open positions.
    - `_cmd_pause(args)`
      - *Docstring*: Pause system trading proposals.
    - `_cmd_resume(args)`
      - *Docstring*: Resume system trading proposals.
    - `_cmd_kill(args)`
      - *Docstring*: Trigger emergency kill switch.
    - `_cmd_positions(args)`
      - *Docstring*: List active open positions (real & paper).
    - `_cmd_unsuspend(args)`
      - *Docstring*: Unsuspend symbols blocked by streak losses.
    - `_cmd_tui(args)`
      - *Docstring*: Launch rich Textual terminal dashboard.
    - `_cmd_chat(args)`
      - *Docstring*: Launch interactive REPL chat with agent.
    - `_cmd_config_show(args)`
      - *Docstring*: Show system configuration or section.
    - `_cmd_config_set(args)`
      - *Docstring*: Update configuration parameter via API or local settings.yaml with validation.
    - `_cmd_config(args)`
      - *Docstring*: Handle config subcommand routing.
    - `_cmd_sessions(args)`
      - *Docstring*: List conversation sessions with metadata.
    - `_cmd_logs(args)`
      - *Docstring*: Stream or tail live activity logs.
    - `_cmd_doctor(args)`
      - *Docstring*: Run deep diagnostic health checks across environment, credentials, MT5, and database.
    - `_cmd_profile(args)`
      - *Docstring*: Manage isolated trading profiles (list, use, create).
    - `_cmd_setup(args)`
      - *Docstring*: Interactive terminal configuration setup wizard.
    - `_cmd_backtest(args)`
      - *Docstring*: Run historical backtest or walk-forward analysis from command line.
    - `_dispatch_cli(args)`
      - *Docstring*: Consolidated async CLI subcommand dispatcher with single event loop lifecycle.
    - `run()`
      - *Docstring*: Synchronous CLI entrypoint.

**File:** `doctor.py`
  - **Classes**:
    - `DiagnosticResult`: Dataclass holding individual diagnostic check outcome (name, passed, message, severity, fix_applied).
    - `SystemDoctor`: Comprehensive system diagnostics engine checking filesystem, YAML validity, credentials, MT5 terminals, and PostgreSQL database.
      - *Methods*: `check_filesystem()`, `check_configuration()`, `check_credentials()`, `check_mt5_environment()`, `check_database()`, `run_all(fix=False)`

**File:** `profile_manager.py`
  - **Classes**:
    - `ProfileManager`: Isolated multi-environment profile manager creating, switching, deleting, exporting, importing, and listing environment profiles under profiles/<name>/.
      - *Methods*: `list_profiles()`, `get_active_profile()`, `switch_profile(name)`, `create_profile(name, clone_from=None)`, `delete_profile(name)`, `export_profile(name, zip_path)`, `import_profile(zip_path, new_name=None)`, `get_env_path_for_active()`, `get_data_dir_for_active()`, `get_settings_path_for_active()`

**File:** `onboarding_trader.py`
  - **Classes**:
    - `TraderProfile`: Dataclass holding trader persona, experience level, risk tolerance, preferred assets, and operating mandates.
    - `TraderOnboarding`: Interactive terminal onboarding wizard syncing trader profile into Layer 0 TRADING_SOUL.md memory.
      - *Methods*: `run_interactive()`, `save_profile()`, `load_profile()`, `sync_to_soul()`

**File:** `setup_wizard.py`
  - **Classes**:
    - `SetupWizard`: Guided interactive CLI setup wizard configuring MT5 accounts, PostgreSQL connections, and LLM API providers with automated verification and modular section execution.
      - *Methods*: `run_interactive()`, `run_wizard(section='all', quick=False)`, `prompt_mt5()`, `prompt_database()`, `prompt_llm()`, `save_configuration()`

**File:** `analysis_tree.py`
  - **Classes**:
    - `AnalysisCycleTree(Widget)`: Textual widget rendering LangGraph pipeline DAG nodes with icons, durations, tokens, braille sparklines, and collapsed historical cycle runs.
      - *Methods*: `compose()`, `update_from_events()`, `update_node()`, `add_completed_cycle()`

**File:** `busy_input.py`
  - **Classes**:
    - `InputDelivery(str, Enum)`: Input delivery modes (one_at_a_time, batch, immediate).
    - `BusyInputBuffer`: Dual-queue buffer distinguishing high-priority steering from follow-up inputs.
      - *Methods*: `submit()`, `has_pending_steer()`, `get_next_steer()`, `get_next_follow_up()`, `dequeue()`, `clear()`, `pending_count()`

**File:** `platform_compat.py`
  - **Functions**:
    - `apply_platform_fixes()`: Hardens standard streams (UTF-8 encoding) and enables Windows VT virtual terminal processing.
    - `detect_color_depth()`: Detects terminal color depth (truecolor, 256, 16, dumb).
    - `supports_unicode()`: Checks Unicode / UTF-8 rendering capability in active console.
    - `get_platform_diagnostics()`: Returns platform compatibility diagnostic dict.

**File:** `sparklines.py`
  - **Functions**:
    - `braille_sparkline(values, min_val=None, max_val=None, width=None)`: Pure Python unicode braille sparkline generator for mini inline terminal trends.
    - `bar_gauge(value, max_val=100.0, width=10, warn_ratio=0.75, crit_ratio=0.90)`: Compact ASCII/Unicode progress bar gauge with warning/critical threshold coloring.

**File:** `theme.py`
  - **Classes**:
    - `ThemePack`: Dataclass defining semantic color tokens for CLI & TUI skins (retro_vintage, modern_dark, high_contrast, daylight).
  - **Global Variables**: `THEME_PACKS`, `PHOSPHOR_AMBER`, `BRASS`, `BULL_PROFIT`, `BEAR_LOSS`, `MUTED`, `DIM`, `PAPER`, `CHARCOAL`, `SURFACE`, `BORDER`, `MONIKA_THEME`, `LEDGER_BOX`
  - **Functions**:
    - `get_theme_pack(name)`: Retrieve ThemePack preset by name.
    - `list_theme_packs()`: List all available theme pack names.
    - `get_console(theme_name)`: Return a Rich Console preconfigured with specified theme.
    - `stamp_ok(text="OK")`: Return formatted green ledger OK stamp.
    - `stamp_err(text="FAILED")`: Return formatted wax red error stamp.
    - `stamp_warn(text="WARNING")`: Return formatted brass warning stamp.
    - `stamp_info(text="INFO")`: Return formatted brass info stamp.
    - `stamp_exec(text="EXECUTE")`: Return formatted amber execution stamp.
    - `build_tui_css(theme_name)`: Generate Textual CSS stylesheet for TUI dashboard using theme semantic tokens.
    - `build_chat_css(theme_name)`: Generate Textual CSS stylesheet for chat screen.

**File:** `tui.py`
  - **Global Variables**: logger, DEFAULT_API_URL, COMMAND_SUGGESTIONS
  - **Classes**:
    - `LiveTickerBanner(Static)`: Top live ticker banner with braille price/VIX sparklines and dynamic trend arrows (•, ▲, ▼).
    - `StatusBar(Static)`: Status footer showing context gauge, cache hit rate, tokens, cost, uptime, and WS status.
    - `TradingDashboard(App)`: Multi-tab rich terminal dashboard (Overview, Analysis Tree, Performance, Signals, Risk, Chat) with theme switching, toast notifications, and live event subscriptions.
      - *Methods*: `action_focus_input()`, `action_blur_input()`, `action_next_tab()`, `action_prev_tab()`, `action_switch_tab()`, `action_tab_overview()`, `action_tab_tree()`, `action_tab_perf()`, `action_tab_signals()`, `action_tab_risk()`, `action_tab_chat()`, `on_tabbed_content_tab_activated()`, `set_theme()`, `_send_inline_chat()`, `_fetch_overview_data()`, `_fetch_data_from_db()`, `_update_ui_state()`
  - **Functions**:
    - `run_tui(api_url, api_key, refresh_interval, theme)`: Entrypoint function to run the Textual TUI dashboard.

**File:** `tui_chat.py`
  - **Global Variables**: logger, DEFAULT_API_URL, CHAT_SCREEN_CSS
  - **Classes**:
    - `ChatScreen(Screen)`: Full-screen interactive chat REPL within Textual TUI.
      - *Methods*: `_is_ws_healthy()`, `_close_ws()`, `_connect_ws()`, `_ensure_ws()`, `action_interrupt()`, `action_clear_transcript()`, `on_input_submitted()`, `_handle_approval_decision()`, `_run_ws_turn()`, `_run_local_turn()`
  - **Functions**:
    - `is_ws_alive(ws)`: Check if ClientWebSocketResponse and underlying transport are active and open.
    - `_get_prompt_session()`: Safely initialize prompt_toolkit PromptSession with fallback for Windows non-console.
    - `run_cli_chat(api_url, api_key, session_id, offline, model)`: Interactive standalone REPL chat with Monika (MT5 Trading Agent).
    - `_submit_cli_decision(ws, local_agent, action_id, decision, console)`: Submit approval decision in CLI REPL.

##### Folder: `trading-agent/cli/overlays`
**File:** `__init__.py`

**File:** `approval_modal.py`
  - **Docstring**: Interactive Modal Dialog for Human-in-the-Loop (HITL) trade action approvals.
  - **Classes**:
    - `ApprovalModalScreen(ModalScreen[Optional[str]])`: Modal screen prompting operator to review and approve/deny proposed trade actions with risk preview and keyboard shortcuts ([1] Allow Once, [2] Allow Session 4h, [3/Esc] Deny).
      - *Methods*: `compose()`, `on_button_pressed(event)`, `action_allow_once()`, `action_allow_session()`, `action_deny()`

#### Folder: `trading-agent/benchmark`
**File:** `__init__.py`
**File:** `alpha_arena.py`
  - **Docstring**: Head-to-Head Tournament Engine for LLM Models & Strategies using Elo ratings.
  - **Classes**: `ArenaCompetitor`, `ArenaMatchResult`, `AlphaArenaTournament`
    - *Methods*: `register_competitor()`, `record_match()`, `get_leaderboard()`
  - **Functions**: `update_elo()`
**File:** `db_access.py`
  - **Classes**: `BenchmarkToolExecutor`
  - **Functions**: `_capturing_submit_asset_analysis`, `_capturing_submit_fundamental_brief`, `_capturing_propose_action`, `guarded_tool_executor`, `pick_asset_analysis`, `latest_brief`, `latest_digest`, `recent_news`, `resolved_reflection`, `latest_user_message`, `entry_context`
**File:** `db_models.py`
  - **Classes**: `BenchmarkRun`, `BenchmarkResult`
**File:** `deterministic.py`
  - **Functions**: `score_trade_payload`, `verify_invariant_compliance`
**File:** `invoker.py`
  - **Classes**: `InvokeResult`
  - **Functions**: `_attach_usage_capture`, `make_client`, `invoke_text`, `invoke_json`, `invoke_agent`, `invoke_chat`, `invoke_custom`
**File:** `judge.py`
  - **Variables**: `JUDGE_PERSONAS`
  - **Functions**: `_score`, `judge_output`, `judge_output_ensemble`
**File:** `model_registry.py`
  - **Variables**: `CANDIDATE_MODELS`
  - **Functions**: `make_role_config`
**File:** `paired_evaluator.py`
  - **Docstring**: A/B Paired Strategy Evaluation Runner computing Win Rate Lift, Profit Factor Delta, Expectancy Delta, and Token Cost Delta across identical historical scenario matrices.
  - **Classes**: `StrategyMetrics`, `PairedComparisonReport`, `PairedStrategyEvaluator`
    - *Methods*: `_compute_metrics()`, `evaluate_pairwise()`
**File:** `pricing.py`
  - **Classes**: `Price`
  - **Variables**: `PRICING`, `OPENROUTER_PRICING_MAP`, `_FREE`
  - **Functions**: `get_price`, `cost_usd`
**File:** `prompt_evolution.py`
  - **Classes**: `GEPALiteEvolver`
**File:** `report.py`
  - **Functions**: `build_report`
**File:** `runner.py`
  - **Functions**: `ensure_tables`, `_err_row`, `_build_case_once`, `run_one_model_for_case`, `run_benchmark`
**File:** `task_specs.py`
  - **Classes**: `BenchmarkCase`, `TaskSpec`
  - **Functions**: `_sym`, `_stage1_system_prompt`, `_case_stage1_fundamental`, `_case_stage1_escalation`, `_case_stage1_shadow_check`, `_case_fundamental_verifier`, `_stage2_system_prompt`, `_build_stage2_case`, `_case_stage2_primary`, `_case_stage2_secondary`, `_case_stage2_session_trigger`, `_case_stage2_prescreen`, `_build_specialist_case`, `_case_specialist_technical`, `_case_specialist_sentiment`, `_case_specialist_macro`, `_case_debate_bull`, `_case_debate_bear`, `_case_debate_judge`, `_case_stage2_adjudicator`, `_build_strict_risk_context`, `_case_risk_gate`, `_case_risk_gate_conservative`, `_case_risk_gate_aggressive`, `_case_risk_gate_neutral`, `_case_portfolio_manager_per_trade`, `_case_portfolio_synthesis`, `_case_adversarial_check`, `_case_news_classification`, `_case_news_classification_escalation`, `_case_news_classification_verifier`, `_case_news_digest`, `_case_news_digest_macro_overview`, `_case_news_digest_verifier`, `_case_cot_precompute`, `_build_chat_case`, `_case_chat_telegram`, `_case_chat_telegram_medium`, `_case_chat_telegram_complex`, `_case_trade_reflection`, `_case_harness_hallucination_detect`, `_case_harness_context_efficiency`, `_case_harness_self_correction`
  - **Variables**: `TASKS`
**File:** `token_drift_tracker.py`
  - **Classes**: `PromptSnapshot`, `DriftReport`, `TokenDriftTracker`
    - *Methods*: `set_baseline()`, `record_run()`, `get_summary()`
**File:** `trade_trajectory_logger.py`
  - **Functions**: `file_lock(f)` (Cross-platform advisory file locking via msvcrt / fcntl)
  - **Classes**: `TradeTrajectoryLogger`
    - *Methods*: `log_trajectory()`, `update_trajectory_outcome()`, `load_recent_trajectories()`

##### Folder: `trading-agent/benchmark/results`
**File:** `model_all.csv`
**File:** `model_cheap_efficient.csv`
**File:** `model_cheap_smart.csv`
**File:** `model_high_intelligence.csv`
**File:** `model_quadrant_analysis.html`
  - **Description**: Standalone interactive quadrant visualization evaluating LLM performance vs task cost (Score vs Cost per Task).
  - **Key Capabilities**:
    - Dynamic 2D ECharts scatter plot (linear and logarithmic scaling) with automatic quadrant thresholds.
    - Two-way interactive binding between scatter plot coordinates and tabular data ledger.
    - Executive KPI summary cards (sweet spot count, percentage, peak score, lowest cost, active thresholds).
    - Precision screener controls (score/cost sliders, fine-tuning steppers, presets for Median/Mean/Elite/Budget/Balanced).
    - ARIA-accessible multi-toggle provider and reasoning depth filters.
    - Tabular ledger with instantaneous search, quadrant filtering, keyboard-accessible sorting, and CSV/PNG export.

#### Folder: `trading-agent/evals`
**File:** `__init__.py`
**File:** `eval_metrics.py`
  - **Docstring**: Core evaluation metrics and A/B comparison engine computing accuracy, grounding pass rates, R:R capture, and Brier calibration scores.
  - **Classes**: `DecisionEvaluation`, `AggregateMetrics`, `ABReport`
  - **Functions**: `compute_brier_score()`, `aggregate_eval_metrics()`, `compare_ab_evaluations()`
**File:** `eval_runner.py`
  - **Docstring**: Automated A/B Evaluation Harness and experiment runner benchmarking prompt and model variants against golden fixtures.
  - **Classes**: `ABEvalRunner`
    - *Methods*: `load_fixtures()`, `evaluate_single_decision()`, `run_ab_benchmark()`
**File:** `runner.py`
  - **Docstring**: Automated Offline Evaluation Runner & Mechanical Scoring Engine.
  - **Classes**: `OfflineEvalRunner`
    - *Methods*: `load_all_fixtures()`, `evaluate_decision()`, `run_suite()`
  - **Functions**: `get_default_golden_candidates()`
**File:** `simulation_clock.py`
  - **Classes**: `SimulationClock`, `MarketStep`, `MarketStepSimulator`
    - *Methods*: `now()`, `advance()`, `advance_to()`, `sleep()`, `load_steps()`, `step()`, `simulate_order_fill()`

##### Folder: `trading-agent/evals/oracles`
**File:** `__init__.py`
**File:** `smc_geometry_oracle.py`
  - **Functions**: `evaluate_smc_geometry()`
**File:** `risk_compliance_oracle.py`
  - **Functions**: `evaluate_risk_compliance()`
**File:** `trade_discipline_oracle.py`
  - **Functions**: `evaluate_trade_discipline()`
**File:** `macro_regime_oracle.py`
  - **Functions**: `evaluate_macro_regime()`

##### Folder: `trading-agent/evals/fixtures`
**File:** `smc_bull_displacement.json`
**File:** `smc_bear_sweep.json`
**File:** `smc_choppy_trap.json`
**File:** `risk_trap_spread_spike.json`
**File:** `risk_trap_daily_dd.json`

#### Folder: `trading-agent/agent`
**File:** `__init__.py`
**File:** `agent_loop.py`
  - **Docstring**: SystemAgentLoop orchestrator for autonomous ad-hoc single-asset pipeline runs and multi-intent actions.
  - **Classes**: `SystemAgentLoop`, `AdHocSchedulerProxy`
    - *Methods*: `normalize_symbol()`, `execute_ad_hoc_analysis()`, `_build_executive_summary()`, `_refresh_data_sources()`
    - *AdHocSchedulerProxy Methods/Attrs*: `_should_skip_full_cycle()`, `_get_symbol_paper_stats()`, `_log()`, `_stage1_consecutive_failures`, `_max_stage1_failures_before_alert`
**File:** `startup_checks.py`
  - **Docstring**: Pre-flight system validation checks extracted from main.py.
  - **Classes**: `StartupChecker`
    - *Methods*: `run_all_checks()`, `_check_task_roles()`, `_check_critical_constants()`, `_check_specialist_prompts()`, `_check_preflight_baselines()`, `_check_paper_trading_gate()`, `_check_db_schema()`, `_check_api_keys()`, `_check_external_services()`, `_check_mt5_connection()`, `_check_tool_handlers()`, `_check_model_roles()`
  - **Functions**: `run_startup_checks()`
**File:** `task_registry.py`
  - **Docstring**: Background task registration, restart logic, and lifecycle supervisor.
  - **Classes**: `TaskDefinition`, `TaskRegistry`
    - *Methods*: `register()`, `get_all()`, `get_core()`, `is_registered()`
  - **Functions**: `_run_with_restart()`, `get_emergency_exit_code()`, `set_emergency_exit_code()`, `mark_clean_shutdown()`
  - **Variables**: `CORE_TRADING_TASKS`
**File:** `turn_lease_manager.py`
  - **Docstring**: Symbol Turn Lease & Event Coalescence Manager preventing concurrent analysis collisions and coalescing reactive market triggers.
  - **Classes**: `SymbolLease`, `SymbolTurnLeaseManager`
    - *Methods*: `acquire_lease()`, `release_lease()`, `coalesce_event()`, `is_symbol_leased()`, `get_lease_holder()`, `get_instance()`
  - **Functions**: `get_symbol_lease_manager()`

##### Folder: `trading-agent/agent/monitors`
**File:** `__init__.py`
**File:** `db_health.py`
  - **Functions**: `run_db_health_check()`
**File:** `drawdown_monitor.py`
  - **Functions**: `run_floating_drawdown_monitor()`
**File:** `paper_trade_monitor.py`
  - **Functions**: `run_paper_trade_monitor()`
**File:** `scraper_loop.py`
  - **Functions**: `run_scraper_loop()`
**File:** `startup_watchdog.py`
  - **Classes**: `StartupWatchdog`
  - **Variables**: `global_startup_watchdog`
  - **Functions**: `arm_startup_watchdog()`, `verify_broker_ping()`, `verify_data_feed_freshness()`, `run_cold_start_preflight()`

#### Folder: `trading-agent/analysis`
**File:** `event_broadcaster.py`
  - **Functions**:
    - `emit_analysis_event(event_type, payload)`: Broadcast LangGraph analysis node and cycle events (start, completion, tokens, elapsed time) to WebSocket subscribers and system event bus.

**File:** `scenario_tree.py`
  - **Classes**: `ScenarioNode`, `ScenarioTree`, `ScenarioTreeEngine`
    - *Methods*: `build_tree()`, `compute_empirical_probabilities()`, `to_jsonl()`
**File:** `subagent_blackboard.py`
  - **Classes**: `SubagentBlackboard`
    - *Methods*: `__init__()`, `set_slot()`, `get_slot()`, `export_distilled_context()`
**File:** `subagent_spawner.py`
  - **Docstring**: Dynamic Subagent Spawner Pool (Autonomous Distributed Architecture) for ad-hoc child subagents with isolated context sandboxes, specialized toolsets, and execution timeouts.
  - **Classes**:
    - `SubagentSpec`
    - `SubagentResult`
    - `SubagentWorker`
      - *Methods*: `__init__()`, `_get_client()`, `run()`
    - `DynamicSubagentPool`
      - *Methods*: `__init__()`, `spawn_worker()`, `run_parallel()`, `decompose_research_query()`

##### Folder: `trading-agent/analysis/harness`
**File:** `__init__.py`
**File:** `agent_harness.py`
  - **Docstring**: Unified Multi-Turn ReAct Agent Harness with turn management, context compaction, state preservation truncation, anti-oscillation, quota enforcement, and ToolExecutor routing.
  - **Classes**: `AgentHarness`
    - *Methods*: `_is_transient_error()`, `_is_billing_error()`, `_normalize_response_content()`, `compute_tool_signature()`, `_preserve_state_summary()`, `_apply_truncation_guardrail()`, `_persist_assistant_turn()`, `_enforce_role_alternation()`, `_check_truncation()`, `_fail_truncated_tool_calls()`, `get_mandatory_tool_for_stage()`, `_log_tool_call()`, `enqueue_steering()`, `run_agent()`, `run_agent_from_messages()`
**File:** `context_compressor.py`
  - **Docstring**: Multi-Phase Hierarchical Context Compressor (PR-06 / Standardized) implementing deterministic tool pruning, protected boundary splitting with warm-prefix preservation, 8-section structured trading summarization (<compacted-summary>), robust tool-pair snapping, and token assembly.
  - **Variables**: `TRADING_SUMMARY_SECTIONS`, `TOOL_PRUNE_MARKER`
  - **Classes**: `ContextCompressor`
    - *Methods*: `compress()`, `prune_oversized_tool_results()`, `prune_deterministic_tools()`, `split_boundaries()`, `_snap_boundary()`, `_feasibility_skip()`, `_extract_existing_summary()`, `_extract_structured_trading_sections()`, `_extract_deterministic_facts()`, `summarize_middle()`
  - **Functions**: `safe_unicode_slice()`, `safe_unicode_tail()`, `prune_tool_result_content()`, `prune_oversized_tool_results()`, `offload_historical_charts()`
**File:** `error_classifier.py`
  - **Docstring**: Structured error classification and recovery strategy assignment with Unicode surrogate cleansing and multimodal fallback.
  - **Functions**: `sanitize_unicode_surrogates()`, `fallback_multimodal_to_text()`
  - **Classes**: `ErrorCategory`, `RecoveryAction`, `ClassifiedError`, `ErrorClassifier`
    - *Methods*: `classify()`, `classify_response()`
**File:** `harness_state.py`
  - **Docstring**: Typed state machine and phase models for agent harness loop.
  - **Classes**: `PhaseAction`, `PhaseVerdict`, `SteeringMessage`, `HarnessState`
    - *Methods*: `record_tokens()`, `record_error()`, `reset_errors()`, `can_retry_error()`, `is_turn_limit_reached()`, `enqueue_steering()`, `drain_steering()`, `drain_follow_up()`
**File:** `message_repair.py`
  - **Docstring**: 4-pass role alternation sanitizer ensuring provider compliance by enforcing role alternation, coalescing consecutive user messages, injecting missing user turns, and purging orphaned tool calls.
  - **Functions**: `repair_message_history(messages)`
**File:** `structured_output.py`
  - **Docstring**: Structured output generation with graceful fallback to free text.
  - **Functions**: `invoke_structured_or_freetext()`
**File:** `repetition_guard.py`
  - **Docstring**: Degenerate Repetition Loop Guard detecting repeating sentence or paragraph fragments in model assistant streams.
  - **Functions**: `detect_text_repetition(text, min_phrase_len=60, min_repeats=3, dominance_ratio=0.50)`
**File:** `stall_guard.py`
  - **Docstring**: State-Aware Stall Guard (H-8) monitoring consecutive read-only tool loops, duplicate response hashing, and enforcing forced termination for synthesis.
  - **Classes**: `StallGuard`
    - *Methods*: `is_read_only()`, `record_call()`, `check_stall()`, `reset()`
  - **Variables**: `READ_ONLY_TOOLS`, `STATE_ADVANCING_TOOLS`
**File:** `symbol_segment_planner.py`
  - **Docstring**: Intelligent tool batch partitioner separating mutating calls across independent asset symbols into parallel batches and sequencing dependent/same-symbol calls.
  - **Classes**: `ToolSegment`, `SymbolSegmentPlanner`
    - *Methods*: `extract_symbol(call)`, `partition_tool_calls(calls)`
**File:** `tool_batch_planner.py`
  - **Classes**: `ToolBatchPlanner`
    - *Methods*: `plan_batch()`, `partition_independent()`
**File:** `tool_repair.py`
  - **Classes**: `ToolRepairEngine`
    - *Methods*: `attempt_repair()`, `validate_schema()`
**File:** `trade_stop_gates.py`
  - **Docstring**: Institutional Trade Stop Gate blocking unverified directional decisions and injecting synthetic verification nudges when required risk evidence is absent.
  - **Classes**: `TradeGateVerdict`, `TradeStopGate`
    - *Methods*: `evaluate(response_text, ledger, stage, symbol)`
**File:** `verification_evidence_ledger.py`
  - **Docstring**: In-memory verification evidence ledger recording empirical proof from deterministic risk and sizing tools.
  - **Classes**: `VerificationEvidence`, `VerificationEvidenceLedger`
    - *Methods*: `record_evidence(tool_name, tool_input, tool_output)`, `has_verified_trade_prerequisites(symbol)`, `get_unverified_reasons(symbol)`, `reset()`

##### Folder: `trading-agent/analysis/grounding`
**File:** `__init__.py`
**File:** `provenance_tagger.py`
  - **Docstring**: Tracks numeric provenance of tool outputs and cross-verifies figures cited by LLM agents. Extended in PR-07 for multi-dimensional grounding (lot_size, spread, margin, equity).
  - **Classes**: `ObservedFact`, `ProvenanceLedger`
    - *Methods*: `register_from_tool_output()`, `register_fact()`, `verify_citation()`, `verify_text_citations()`, `verify_lot_size()`, `verify_spread()`, `verify_margin()`, `verify_equity()`, `verify_trade_parameters()`

##### Folder: `trading-agent/analysis/subagent`
**File:** `__init__.py`
**File:** `adhoc_manager.py`
  - **Docstring**: Non-blocking on-demand market anomaly investigation subagent manager bounded by concurrency semaphore (limit=3).
  - **Classes**: `AdHocInvestigationVerdict`, `AdHocSubagentManager`
    - *Methods*: `get_latest_verdict()`, `investigate_async()`, `run_investigation()`
  - **Functions**: `get_adhoc_manager()`
**File:** `isolated_harness.py`
  - **Docstring**: IsolatedSubagentRunner executing subagent tasks in fully isolated harness loops with clean context windows and bounded turn budgets.
  - **Classes**: `SubagentRunResult`, `IsolatedSubagentRunner`
    - *Methods*: `run_isolated()`

##### Folder: `trading-agent/analysis/arbitration`
**File:** `__init__.py`
**File:** `signal_arbitrator.py`
  - **Docstring**: Centralized SignalArbitrator to reconcile Quantitative vs LLM Debate signals based on conviction, regime, VIX protection, recency-decay Brier calibration, and streak penalties.
  - **Classes**: `ArbitrationResult`, `SignalArbitrator`
    - *Methods*: `arbitrate()`, `_do_arbitrate()`, `_get_empirical_concordant_multiplier()`
  - **Functions**: `compute_empirical_arbitrator_weights()`

##### Folder: `trading-agent/analysis/stages`
**File:** `fundamental_stage.py`
  - **Classes**: `FundamentalStage`
**File:** `per_asset_stage.py`
  - **Docstring**: Backward-compatible facade for PerAssetStage inheriting from PerAssetRunner.
  - **Classes**: `PerAssetStage`
  - **Functions**: `_flatten_system_prompt`, `_get_symbol_sl_streak`
**File:** `preflight_gate.py`
  - **Classes**: `PreFlightTurnGate`
    - *Methods*: `check_high_impact_news()`, `evaluate_preconditions()`
  - **Variables**: `EMPIRICAL_ACTIVE_MEDIANS`, `ACTIVE_SPREAD_HARD_CEILINGS`, `SYMBOL_CURRENCIES`

###### Folder: `trading-agent/analysis/stages/per_asset`
**File:** `__init__.py`
**File:** `context_builder.py`
  - **Classes**: `ContextBuilderMixin`
  - **Functions**: `_render_specialist_prompt`, `_flatten_system_prompt`
  - **Variables**: `SYMBOL_TO_COT`, `SYSTEM_PROMPT_TEMPLATE`, `SYSTEM_PROMPT_STATIC`, `SPECIALIST_PROMPTS`
**File:** `runner.py`
  - **Classes**: `PerAssetRunner`
    - *Methods*: `run_one()`, `run_all()`, `_fetch_stage2_bundle()`, `_execute_stage2_prescreen()`, `_recover_missing_analysis()`
**File:** `specialist_council.py`
  - **Docstring**: Institutional 5-Specialist Council for Per-Asset Trade Decisions (Macro, Technical, News/Sentiment, Risk Arbitrator, Execution Strategist).
  - **Classes**: `SpecialistRole`, `TradeAction`, `SpecialistVote`, `CouncilVerdict`, `SpecialistCouncil`
    - *Methods*: `evaluate()`, `_evaluate_macro()`, `_evaluate_technical()`, `_evaluate_news_sentiment()`, `_evaluate_risk_arbitrator()`, `_evaluate_execution_strategist()`

**File:** `specialist_pipeline.py`
  - **Classes**: `SpecialistPipelineMixin`
    - *Methods*: `_execute_specialist_debate_pipeline()`
  - **Variables**: `_SPECIALIST_KEY_MAP`
**File:** `verifiers.py`
  - **Classes**: `VerifiersMixin`
    - *Methods*: `_check_brief_freshness_and_quality()`, `_compute_ssvp_coherence()`
  - **Functions**: `_get_symbol_sl_streak`

##### Folder: `trading-agent/analysis/validators`
**File:** `adjudication_verifier.py`
  - **Functions**: `verify_adjudication`
  - **Variables**: `ADJUDICATION_VERIFY_SCHEMA`
**File:** `adversarial_check.py`
  - **Functions**: `run_adversarial_check`, `_safe_parse`
**File:** `confluence_verifier.py`
  - **Functions**: `verify_confluence`
**File:** `core_data_validator.py`
  - **Classes**: `CoreDataValidator`
**File:** `cross_timeframe_gate.py`
  - **Docstring**: Cross-Timeframe Confirmation Gate enforcing H4+H1 directional alignment before allowing M15 trade entry.
  - **Classes**: `CrossTimeframeConfirmationGate`
    - *Methods*: `verify_htf_alignment()`, `_extract_timeframe_bias()`
**File:** `float_coercion.py`
  - **Docstring**: Defensive float coercion utilities stripping currency signs, percentages, and commas from LLM outputs.
  - **Functions**: `coerce_optional_float()`, `coerce_float()`
**File:** `fundamental_verifier.py`
  - **Functions**: `verify_fundamental_brief`
**File:** `in_harness_grounding.py`
  - **Classes**: `InHarnessGroundingValidator`
    - *Methods*: `extract_numbers_from_text()`, `verify_grounding()`, `verify_scratchpad_consistency()`, `verify_lot_size()`, `verify_spread()`, `verify_margin()`, `verify_equity()`, `verify_trade_parameters()`
**File:** `market_snapshot.py`
  - **Docstring**: VerifiedMarketSnapshot grounding container providing immutable point-in-time bid/ask/spread/OHLC reference data.
  - **Classes**: `VerifiedMarketSnapshot`
  - **Functions**: `create_market_snapshot`, `_compute_fallback_indicators`, `format_as_markdown`, `validate_plan_against_snapshot`
**File:** `output_verifier.py`
  - **Classes**: `OutputVerifier`
    - *Methods*: `verify_and_correct()`, `_apply_deterministic_math_snapping()` (enhanced with structural anchor snapping), `_run_all_checks()` (tightened Check 5 to 0.5x ATR), `_extract_atr()`, `_near_any_level()`, `_find_nearest()`
**File:** `precommit_gate.py`
  - **Classes**: `TradePreCommitGate`
    - *Methods*: `verify_precommit()` (integrates VerifiedMarketSnapshot structural & drift validation)

##### Folder: `trading-agent/analysis/calculators`
**File:** `adaptive_policy.py`
  - **Classes**: `AdaptiveRiskPolicy`
**File:** `confluence_calculator.py`
  - **Functions**: `calculate_confluence`
**File:** `daily_range_calculator.py`
  - **Functions**: `compute_daily_range_context`
**File:** `economic_surprise.py`
  - **Functions**: `compute_surprise_scores`
**File:** `intraday_level_optimizer.py`
  - **Functions**: `compute_optimal_levels(session, symbol, direction, entry_price, settings, existing_sl=None, existing_tp=None)`
    - *Docstring*: Computes optimal intraday target levels based on H4/D1 zones, ADR, TimesFM cone, and validates R:R >= min_rr pairing (with synthetic TP fallback if structural TP is insufficient).
**File:** `invariant_calculator.py`
  - **Classes**: `DeterministicTradeInvariants`
  - **Functions**: `calculate_deterministic_trade_invariants`, `snap_sl_to_structural_anchor`
**File:** `liquidity_sweep_detector.py`
  - **Functions**: `detect_liquidity_sweep`
**File:** `macro_bias_filter.py`
  - **Functions**: `evaluate_macro_alignment`
**File:** `macro_priced_in_calculator.py`
  - **Functions**: `calculate_macro_priced_in_baseline`
**File:** `regime_classifier.py`
  - **Functions**: `classify_market_regime`, `compute_bollinger_donchian_chop`
**File:** `volume_profile.py`
  - **Functions**: `compute_volume_profile`, `compute_anchored_vwap`
**File:** `stage1_priced_in.py`
  - **Functions**: `calculate_stage1_priced_in_baseline`
**File:** `unified_threshold_calculator.py`
  - **Functions**: `compute_unified_confluence_threshold`
**File:** `timesfm_alpha.py`
  - **Classes**: `TimesFMAlphaCalculator`
    - *Methods*: `calculate_skew_from_quantiles()`, `get_sizing_multiplier()`, `format_for_prompt()`

##### Folder: `trading-agent/analysis/tools`
**File:** `base_handler.py`
  - **Classes**: `ToolHandler`, `DisaggregatedToolResult`
    - *Methods*: `can_handle()`, `execute()`
    - *Attributes*: `protected`
  - **Functions**: `tool_handler`
**File:** `loop_guard.py`
  - **Docstring**: Tool execution loop guard with key-sorted hashing and escalation thresholds.
  - **Classes**: `ToolLoopGuard`
    - *Methods*: `check()`, `reset()`
  - **Functions**: `canonical_tool_hash()`, `_sort_recursive()`
**File:** `composite_tools.py`
  - **Functions**: `execute_market_context`, `execute_technical_analysis`, `execute_price_data`, `execute_institutional_data`
**File:** `executor.py`
  - **Classes**: `ToolExecutor`
    - *Methods*: `execute()`, `has_tool()`, `get_handler()`, `list_tools()`, `_tool_propose_action()`, `_tool_get_price_history()`, `_tool_delegate_specialist_analysis()`
**File:** `registry.py`
  - **Docstring**: Self-registering tool registry with availability gating and bounded output.
  - **Classes**: `ToolDefinition`, `ToolRegistry`, `ToolHandlerRecord`
    - *Methods*: `is_available()`, `get_instance()`, `reset_instance()`, `register()`, `get()`, `list_tools()`, `get_schemas()`, `execute()`
  - **Functions**: `default_tool_registry()`
  - **Global Variables**: `GLOBAL_TOOL_REGISTRY`
**File:** `tool_catalog.py`
  - **Docstring**: Hybrid tool discovery catalog combining pinned essential core tools with dynamic BM25 search.
  - **Classes**: `HybridToolCatalog`
    - *Methods*: `search_tools()`, `get_tool_definition()`, `format_catalog_prompt()`

**File:** `tool_executor.py`
  - **Classes**: `ToolExecutor`
    - *Methods*: `_normalize_tool_name()`, `get_tool_schema()`, `execute()`, `_resolve_symbol()`, `_validate_manual_order_structural()`, `_tool_submit_asset_analysis()`, `_validate_key_data_points()`, `_tool_get_funding_rate()`, `_tool_get_fedwatch_probabilities()`, `_tool_get_paper_trading_performance()`, `_tool_get_trade_history()`, `_tool_get_active_triggers()`, `_tool_get_system_health()`, `_tool_get_edge_tracker_status()`, `_tool_get_calibration_status()`, `_tool_get_token_usage_and_costs()`, `_tool_get_trade_details()`, `_tool_get_market_correlations()`, `_tool_get_bond_yield_spreads()`, `_tool_get_multi_timeframe_summary()`, `_tool_get_chart()`, `_tool_get_spread_snapshot()`, `_tool_get_verified_market_snapshot()`, `_tool_execute_analysis_code()`, `_tool_update_scratchpad()`, `_tool_read_scratchpad()`, `_tool_transition_analysis_phase()`, `_tool_get_timesfm_forecast()`, `_tool_web_search()`, `_tool_save_market_intelligence()`, `_tool_list_active_intelligence()`, `_tool_archive_market_intelligence()`
    - *Variables*: `TOOL_ALIASES`
**File:** `tool_guardrails.py`
  - **Docstring**: Unified Tool Guardrails Controller (Anti-Oscillation, Monotonic Risk, Read-Before-Act, Sizing, Turn Cap, Denial Circuit Breaker).
  - **Classes**: `GuardrailVerdict`, `ToolCallSignature`, `AntiOscillationGuard`, `MonotonicRiskGuard`, `ReadBeforeActGuard`, `MandatorySizingGuard`, `CategoryTurnCapGuard`, `DenialCircuitBreakerGuard`, `ToolGuardrailController`
    - *Methods*: `evaluate()`, `validate_tool_call()`, `record_tool_call()`, `record_denial()`, `record_success()`, `is_denial_breaker_tripped()`, `reset_turn()`, `reset_all()`
  - **Variables**: `DATABASE_IMMUTABLE_TABLES`, `DATA_READ_TOOLS`, `TERMINAL_ACTION_TOOLS`, `TOOL_CATEGORIES`
**File:** `tool_registry.py`
  - **Classes**: `ProgressiveToolRegistry`, `ToolRegistry`
    - *Methods*: `get_prescreen_schemas()`, `get_schemas_for_asset()`, `get_core_schemas()`, `load_category()`, `get_stub_summary()`, `search_tools()`, `describe_tool()`, `compact_schema()`, `get_compact_core_schemas()`
  - **Global Variables*: `LOAD_TOOL_CATEGORY_TOOL`, `SEARCH_TOOLS_TOOL`, `DESCRIBE_TOOL_TOOL`, `CALCULATE_POSITION_SIZE_TOOL`, `default_registry`
**File:** `tool_result_storage.py`
  - **Docstring**: Disk-backed persistent storage for oversized tool execution payloads (>16KB) preventing LLM context window inflation.
  - **Classes**: `ToolResultStorage`
    - *Methods*: `store()`, `retrieve()`, `cleanup()`
**File:** `tool_spill.py`
  - **Docstring**: Disk-backed persistent tool output spillover storage for large payloads preserving 40/60 head-tail tokens.
  - **Classes**: `ToolSpillStorage`
    - *Methods*: `maybe_spill()`, `cleanup_old_spills()`
  - **Functions**: `truncate_head_tail(text, max_chars, head_pct)`, `safe_unicode_slice(text, max_chars)`
**File:** `tools_definitions.py`
  - **Functions**: `minify_tool_definitions`, `make_strict_tool_definitions`
  - **Global Variables*: `STAGE1_TOOLS`, `STAGE2_TOOLS`, `STAGE2_ESSENTIAL_TOOLS`, `STAGE2_FROZEN_TOOLS` (includes `GET_EIA_OIL_INVENTORY`), `STAGE2_TOOLS_V2`, `STAGE2_PRESCREEN_TOOLS`, `TELEGRAM_TOOLS`, `ALL_TOOLS`, `DELEGATE_SPECIALIST_ANALYSIS`, `UPDATE_SCRATCHPAD`, `READ_SCRATCHPAD`, `TRANSITION_PHASE`, `CALCULATE_POSITION_SIZE`, `GET_CENTRAL_BANK_EXPECTATIONS`, `GET_BOND_YIELD_SPREADS`, `GET_MULTI_TIMEFRAME_SUMMARY`, `GET_CHART`, `GET_SPREAD_SNAPSHOT`, `GET_PAPER_TRADING_PERFORMANCE`, `GET_TRADE_HISTORY`, `GET_ACTIVE_TRIGGERS`, `GET_SYSTEM_HEALTH`, `GET_EDGE_TRACKER_STATUS`, `GET_CALIBRATION_STATUS`, `GET_TOKEN_USAGE_AND_COSTS`, `GET_TRADE_DETAILS`, `GET_MARKET_CORRELATIONS`, `GET_OPEN_POSITIONS`, `GET_ACCOUNT_INFO`, `PROPOSE_ACTION`, `GET_EIA_OIL_INVENTORY`, `GET_TIMESFM_FORECAST`, `WEB_SEARCH`, `SAVE_MARKET_INTELLIGENCE`, `LIST_ACTIVE_INTELLIGENCE`, `ARCHIVE_MARKET_INTELLIGENCE`, `GET_VERIFIED_MARKET_SNAPSHOT`, `GET_MARKET_QUOTE`, `EXECUTE_ANALYSIS_CODE`, `INSPECT_DATABASE_SCHEMA`, `READ_DATABASE_RECORDS`, `SEARCH_HISTORICAL_MEMORIES`
**File:** `unified_registry.py`
  - **Docstring**: Single Source of Truth Unified Type-Safe Tool Registry with declarative Pydantic v2 schemas and multi-provider export.
  - **Classes**: `ToolEntry`, `UnifiedToolRegistry`
    - *Methods*: `register()`, `get_tool()`, `list_tools()`, `get_anthropic_tools()`, `get_openai_tools()`, `dispatch()`
  - **Global Variables**: `unified_tool_registry`

###### Folder: `trading-agent/analysis/tools/quant_sandbox`
**File:** `__init__.py`
**File:** `rpc_server.py`
  - **Docstring**: Local Loopback Quant Sandbox RPC Server & Client for zero-context MT5 ticks/bars calculations.
  - **Classes**: `QuantSandboxRpcServer`, `QuantSandboxClient`
    - *Methods*: `handle_request()`, `start()`, `stop()`, `compute_stats()`, `compute_correlation()`, `execute_code()`

###### Folder: `trading-agent/analysis/tools/kernel`
**File:** `__init__.py`
**File:** `env_sanitizer.py`
  - **Docstring**: Subprocess environment sanitizer purging broker passwords, database connections, and API keys from child processes.
  - **Functions**: `get_sanitized_environment()`, `sanitize_environment`
**File:** `output_spiller.py`
  - **Docstring**: Output character bounding and disk spiller preserving 40/60 head-tail tokens.
  - **Functions**: `truncate_and_spill_output()`
**File:** `persistent_kernel.py`
  - **Docstring**: Isolated Python execution session with subprocess sandboxing.
  - **Classes**: `PersistentCodeKernel`
    - *Methods*: `__init__(session_id="default", sandbox_mode=True)`, `execute(code_str, timeout_seconds=30.0)`, `reset()`
**File:** `sandbox_runner.py`
  - **Docstring**: Sandboxed Subprocess Code Execution Runner with AST validation and sanitized environment.
  - **Variables**: `DEFAULT_TIMEOUT_SECONDS`, `MAX_OUTPUT_CHARS`, `FORBIDDEN_MODULES`, `FORBIDDEN_CALLS`, `logger`
  - **Classes**: `SandboxedKernel`
    - *Methods*: `__init__(session_id="sandbox", timeout_seconds=30.0, max_output_chars=50000)`, `execute(code_str, timeout_seconds=None, custom_env=None)`
  - **Functions**: `validate_code_ast(code)`

###### Folder: `trading-agent/analysis/tools/domain`
**File:** `__init__.py`
**File:** `execution_handlers.py`
  - **Classes**: `ExecutionToolHandlers`
    - *Methods*: `__init__(settings=None, mt5_client=None)`, `calculate_position_size()`, `get_spread_snapshot()`
**File:** `macro_handlers.py`
  - **Classes**: `MacroToolHandlers`
    - *Methods*: `get_market_session()`, `get_bond_yield_spreads()`, `get_vix()`, `get_dxy()`, `get_funding_rate()`, `get_fedwatch_probabilities()`, `get_central_bank_expectations()`, `get_treasury_yields()`, `get_interest_rates()`, `get_precomputed_cot_signals()`, `get_surprise_summary()`
**File:** `position_handlers.py`
  - **Classes**: `PositionToolHandlers`
**File:** `sentiment_handlers.py`
  - **Classes**: `SentimentToolHandlers`
    - *Methods*: `get_news_items()`, `get_fear_greed()`, `get_retail_sentiment()`, `get_funding_rate()`, `get_news_digest()`
**File:** `spill_reader_tool.py`
  - **Docstring**: Domain tool handler allowing the AI agent to read back spilled context or observations from PostgreSQL context_spill_blobs or disk spill cache on demand.
  - **Classes**: `RetrieveSpilledContextInput`, `RetrieveSpilledContextHandler`
    - *Methods*: `execute()`
  - **Functions**: `handle_retrieve_spilled_context()`, `unified_retrieve_spilled_context()`
**File:** `technical_handlers.py`
  - **Classes**: `TechnicalToolHandlers`
    - *Methods*: `get_market_quote()`, `get_price_history()`, `get_technical_indicators()`, `get_atr()`, `get_smc_zones()`, `get_structure_breaks()`, `get_fibonacci_levels()`, `get_daily_range_context()`, `get_optimal_intraday_levels()`

###### Folder: `trading-agent/analysis/tools/handlers`
**File:** `__init__.py`
**File:** `analysis_submit.py`
**File:** `category_loader.py`
  - **Classes**: `LoadToolCategoryHandler`, `GetMarketContextHandler`, `GetInstitutionalDataHandler`, `SearchToolsHandler`, `DescribeToolHandler`
  - **Functions**: `handle_load_tool_category`, `handle_get_market_context`, `handle_get_institutional_data`, `handle_search_tools`, `handle_describe_tool`
**File:** `db_tools.py`
  - **Docstring**: Database inspection and query tool handlers for authorized Admin operator.
  - **Classes**: `InspectDatabaseSchemaHandler`, `ReadDatabaseRecordsHandler`
  - **Functions**: `get_table_model_map()`, `_serialize_row()`, `handle_inspect_database_schema()`, `handle_read_database_records()`
**File:** `intelligence.py`
**File:** `macro_data.py`
  - **Classes**: `GetCentralBankExpectationsHandler`, `GetBondYieldSpreadsHandler`, `GetFedWatchProbabilitiesHandler`, `GetFundingRateHandler`, `GetEiaOilInventoryHandler`, `GetTreasuryYieldsHandler`, `GetInterestRatesHandler`, `GetCotReportHandler`, `GetVixHandler`, `GetDxyHandler`, `GetFearGreedIndexHandler`, `GetEconomicCalendarHandler`, `GetEconomicSurpriseHandler`, `GetPrecomputedCotSignalsHandler`, `GetSurpriseSummaryHandler`
**File:** `macro_tools.py`
  - **Functions**: `_safe_execute`, `handle_get_calendar`, `handle_get_fedwatch`, `handle_get_central_bank_expectations`, `handle_get_bond_yield_spreads`, `handle_get_interest_rates`, `handle_get_treasury_yields`, `handle_get_macro_context`, `handle_get_eia_oil_inventory`, `handle_get_precomputed_cot_signals`, `handle_get_surprise_summary`
**File:** `market_data.py`
  - **Classes**: `GetMarketQuoteHandler`, `GetPriceDataHandler`, `GetTechnicalAnalysisHandler`, `GetChartHandler`, `GetMultiTimeframeSummaryHandler`, `GetSpreadSnapshotHandler`, `GetPriceHistoryHandler`, `GetTechnicalIndicatorsHandler`
**File:** `market_data_tools.py`
  - **Functions**: `handle_get_market_quote`, `handle_get_price_history`, `handle_get_technical_indicators`, `handle_get_atr`, `handle_get_swing_points`, `handle_get_structure_breaks`, `handle_get_fibonacci_levels`, `handle_get_intraday_levels`, `handle_get_sr_zones` (R5: standalone S/R zones)
**File:** `news_tools.py`
  - **Functions**: `handle_get_news_items`, `handle_get_news_digest`, `handle_get_digest_slices`, `handle_web_search`, `handle_read_url`, `handle_search_academic`, `_wrap_untrusted_digest`
**File:** `phase_transition.py`
**File:** `position_mgmt.py`
**File:** `ptc_handler.py`
  - **Docstring**: PTCHandler executing analysis code in isolated Python subprocess with TCP JSON-RPC bridge for safe programmatic tool calling.
  - **Classes**: `PTCHandler`
    - *Methods*: `execute()`, `_build_sandboxed_script()`, `_start_tool_rpc_server()`
**File:** `scratchpad.py`
**File:** `sentiment_data.py`
**File:** `sentiment_tools.py`
  - **Functions**: `handle_get_sentiment_summary`, `handle_get_social_sentiment`, `handle_get_retail_sentiment`
**File:** `skills_tools.py`
  - **Classes**: `SkillsListHandler`, `SkillViewHandler`
  - **Functions**: `handle_skills_list()`, `handle_skill_view()`, `_extract_summary()`
**File:** `smc_tools.py`
  - **Functions**: `handle_get_order_blocks`, `handle_get_liquidity_sweeps`, `handle_get_fair_value_gaps`
**File:** `system_info.py`
**File:** `timesfm.py`
**File:** `trade_intel.py`
  - **Classes**: `GetTradeHistoryHandler`, `GetTradeDetailsHandler`, `GetActiveTriggersHandler`, `GetPaperTradingPerformanceHandler`, `GetAssetAnalysisHandler` (R5), `GetRecentActivityHandler` (R5), `GetConversationHistoryHandler` (R5)
  - **Functions**: `handle_get_asset_analysis` (R5: latest AssetAnalysis per symbol), `handle_get_recent_activity` (R5: ActivityLog tail), `handle_get_conversation_history`
**File:** `trading_tools.py`
  - **Functions**: `handle_calculate_position_size`, `handle_propose_order`, `handle_simulate_execution`
**File:** `verified_snapshot.py`

##### Folder: `trading-agent/analysis/schemas`
**File:** `pydantic_schemas.py`
  - **Classes**: `FundamentalBriefSchema`, `SentimentAnalysisSchema`, `SubmitAssetAnalysisSchema`, `SpecialistAdjudication`, `EntryCondition`, `ReevaluationTrigger`, `PricedInOverrideJustification`, `ChecklistVerification`, `KeyDataPointsUsed`, `UpcomingRiskEvent`, `PricedInAssessment`
  - **Functions**: `coerce_str()`, `coerce_string_list()`, `coerce_float()`, `coerce_int()`, `make_openai_strict_schema()`
**File:** `schemas.py`

##### Folder: `trading-agent/analysis/stages`
**File:** `fundamental_stage.py`
  - **Classes**: `FundamentalStage`
**File:** `per_asset_stage.py`
  - **Docstring**: Backward-compatible facade for PerAssetStage inheriting from PerAssetRunner (see `stages/per_asset/runner.py`).
  - **Classes**: `PerAssetStage`
    - *Methods*: `run_one()`, `run_all()`, `_check_brief_freshness_and_quality()`, `_compute_ssvp_coherence()`, `_fetch_stage2_bundle()`, `_compose_stage2_system_prompt()`, `_build_stage2_context_blocks()`, `_execute_specialist_debate_pipeline()`, `_recover_missing_analysis()`
  - **Functions**: `_render_specialist_prompt`, `_flatten_system_prompt`, `_get_symbol_sl_streak`
  - **Variables**: `SYSTEM_PROMPT_TEMPLATE`, `SYSTEM_PROMPT_STATIC`, `SPECIALIST_PROMPTS`

##### Folder: `trading-agent/analysis/strategies`
**File:** `base_strategy.py`
  - **Classes**: `CandleDict` (Dual item/attribute access dict wrapper for OHLCV candles), `EdgeSignal` (Added `exit_style: str = 'intraday_adr'` and `paired_leg: Optional['EdgeSignal']`), `EdgeStrategy` (Methods: `is_enabled()`, `get_historical_candles()`, `evaluate()`)
**File:** `registry.py`
  - **Classes**: `StrategyRegistry`
    - *Methods*: `register(strategy)`, `get_strategy(strategy_id)`, `list_strategies()`, `evaluate_all(symbol, tf, market_data)`, `hot_reload(strategy_id, parameters)`, `load_dynamic_parameters(session)`, `get_strategy_counts()`, `log_summary()`
    - *Variables*: `_registry`, `_dynamic_params`, `_blacklisted_ids`, `_last_load_time`, `_load_interval`
**File:** `gap_fade.py`
  - **Classes**: `DailyReopenGapFade`
**File:** `btc_donchian_breakout.py`
  - **Classes**: `BTCDonchianBreakout`
**File:** `tsm_momentum.py`
  - **Classes**: `TimeSeriesMomentum`
**File:** `xau_trend_engine.py`
  - **Classes**: `XAUTrendEngine`
**File:** `xti_pairs_readiness.py`
  - **Classes**: `XTIPairsReadiness` (Generates dual-leg Stat-Arb signals with dynamic SL/TP using DB Brent data)
**File:** `liquidity_sweep_edge.py`
  - **Classes**: `LiquiditySweepStructuralShift` (Calculates invalidation Stop Loss from sweep_price extreme wick)
**File:** `pretrade_gate.py`
  - **Functions**: `evaluate_pretrade_gate(session, symbol: str, settings: dict, strategy_type: str) -> tuple[bool, str]`
**File:** `decay_monitor.py`
  - **Docstring**: Automated strategy degradation detection & state machine (ACTIVE -> MONITORING -> DECAYED -> DISABLED).
  - **Classes**: `DecayState`, `StrategyHealth`, `StrategyDecayMonitor`
    - *Methods*: `get_health()`, `is_tradeable()`, `record_trade_outcome()`, `evaluate()`
  - **Functions**: `get_strategy_decay_monitor()`

###### Folder: `trading-agent/analysis/strategies/synthesized`
**File:** `alpha_eurusd_6d622a.py`
  - **Classes**: `SynthesizedStrategy_alpha_eurusd_6d622a`
    - *Methods*: `evaluate()`

**File:** `alpha_usdjpy_13a603.py`
  - **Classes**: `SynthesizedStrategy_alpha_usdjpy_13a603`
    - *Methods*: `evaluate()`

**File:** `alpha_xauusd_94ad53.py`
  - **Classes**: `SynthesizedStrategy_alpha_xauusd_94ad53`
    - *Methods*: `evaluate()`

**File:** `alpha_xauusd_b01980.py`
  - **Classes**: `SynthesizedStrategy_alpha_xauusd_b01980`
    - *Methods*: `evaluate()`

**File:** `alpha_xbrusd_e55dbf.py`
  - **Classes**: `SynthesizedStrategy_alpha_xbrusd_e55dbf`
    - *Methods*: `evaluate()`

**File:** `alpha_xtiusd_f30ff5.py`
  - **Classes**: `SynthesizedStrategy_alpha_xtiusd_f30ff5`
    - *Methods*: `evaluate()`

##### Folder: `trading-agent/analysis/prefetch`
**File:** `digest_slice_generator.py`
  - **Classes**: `DigestSliceGenerator` (Methods: `generate_slice`, `assemble_12h_digest`, `_compute_coverage_gaps`)
  - **Variables**: `TARGET_CURRENCIES`, `IMPACT_WEIGHT`
**File:** `macro_preprocessor.py`
  - **Classes**: `MacroPreprocessor`, `GeminiPreprocessor` (alias)
  - **Variables**: `MARKET_CODE_TO_SYMBOL`, `SYMBOL_USD_DIRECTION`, `_PREPROCESSOR_CACHE`, `_GEMINI_CACHE`
  - **Functions**: `_check_cache`, `_set_cache`, `clear_cache`
**File:** `news_digest.py`
  - **Classes**: `NewsDigestProcessor` (Methods: `invalidate_macro_context_cache`, `_build_5day_macro_context`, `_build_currency_signals_summary`, `create_news_digest`, `_check_digest_internal_consistency`, `_reconcile_digest_contradictions`)
  - **Variables**: `MANDATORY_BREAKING_CHECKLIST`, `NON_BREAKING_TITLE_PATTERN`, `NEWS_CLASSIFICATION_SCHEMA`, `SENTIMENT_TAXONOMY`, `_STRUCTURAL_NUMBERS`, `_NUMERIC_TOKEN_PATTERN`
  - **Functions**: `_format_news_item_for_prompt`, `_extract_numeric_claims`, `_normalize_num_variants`, `_normalize_contradictions`, `_flag_ungrounded_numbers`, `_deduplicate_items_by_title`, `_compute_coverage_gaps`, `_get_daily_breaking_budget`, `_persist_daily_breaking_budget`, `_resolve_item_index`, `_is_zero_based_series`, `_keyword_fallback_classify`, `generate_deterministic_macro_summary`, `generate_deterministic_currency_summary`
**File:** `sentiment_aggregator.py`
  - **Classes**: `SentimentAggregator`
**File:** `stage1_prefetcher.py`
  - **Classes**: `Stage1DataBundler` (Methods: `prefetch_all_data`, `_compress_json`)
  - **Variables**: `PREFETCH_KEY_TO_TOOL`
**File:** `stage2_prefetcher.py`
  - **Classes**: `Stage2DataBundler` (Methods: `fetch_bundle`, `_compress_history`, `_format_technical_readable`, `_compress_json`, `_check_age_warnings`)
  - **Variables**: `_PRICE_PRECISION`, `STANDARD_FETCH_TASKS`, `SYMBOL_FETCH_TASKS`

##### Folder: `trading-agent/analysis/debate`

**File:** `__init__.py`

**File:** `macro_bull_analyst.py`
  - **Functions**: `run_bull_analyst()`

**File:** `macro_bear_analyst.py`
  - **Functions**: `run_bear_analyst()`

**File:** `macro_judge.py`
  - **Functions**: `run_macro_judge()`

**File:** `macro_debate_validator.py`
  - **Functions**: `normalize_winner()`, `validate_macro_judge_output()`

**File:** `adjustment_validator.py`
  - **Functions**: `validate_and_apply_judge_adjustments()`

**File:** `bear_analyst.py`
  - **Functions**: `generate_bear_dissent()`

**File:** `bull_analyst.py`
  - **Functions**: `generate_bull_advocacy()`, `generate_bull_rebuttal()`

**File:** `conservative_risk_llm.py`
  - **Functions**: `analyze_risk_conservative_llm()`

**File:** `aggressive_risk_llm.py`
  - **Functions**: `analyze_risk_aggressive_llm()`

**File:** `neutral_risk_llm.py`
  - **Functions**: `analyze_risk_neutral_llm()`

**File:** `deterministic_risk.py`
  - **Functions**: `analyze_risk_conservative()`, `analyze_risk_aggressive()`, `analyze_risk_neutral()`, `make_portfolio_decision_deterministic()`

**File:** `investment_judge.py`
  - **Variables**: `REGIME_WEIGHT_MATRIX`
  - **Functions**: `resolve_regime_weights()`, `evaluate_debate()`


**File:** `portfolio_manager.py`
  - **Functions**: `make_portfolio_decision()`

**File:** `fact_sheet.py`
  - **Global Variables**: `logger`
  - **Functions**: `build_fact_sheet(session: AsyncSession, analysis_id: Any) -> Dict[str, Any]`

##### Folder: `trading-agent/analysis/validators`
**File:** `adjudication_verifier.py`
  - **Variables**: `ADJUDICATION_VERIFY_SCHEMA`, `ADJUDICATION_SYSTEM_PROMPT`
  - **Functions**: `verify_adjudication()`
**File:** `adversarial_check.py`
  - **Functions**: `run_adversarial_check()`
**File:** `confluence_verifier.py`
  - **Functions**: `verify_confluence()`
**File:** `core_data_validator.py`
  - **Functions**: `validate_core_data()`
**File:** `fundamental_verifier.py`
  - **Variables**: `VERIFIER_SCHEMA`, `FUNDAMENTAL_VERIFIER_SYSTEM_PROMPT`
  - **Functions**: `verify_fundamental_brief()`
**File:** `output_verifier.py`
  - **Functions**: `verify_output_structure()`

##### Folder: `trading-agent/analysis/providers`

**File:** `base_provider.py`
  - **Classes**: `BaseLLMClient`, `MockResponse`, `MockBlock`
    - *Methods*: `generate()`, `generate_content()`, `classify_json()`, `run_agent()`, `run_agent_from_messages()`, `run_tool_agent()`, `_log_tool_call()`, `_save_token_usage()`, `_infer_subsystem()`, `_get_session_affinity_headers()`, `_preserve_reasoning_signatures()`
  - **Functions**: `_flatten_system_prompt`, `extract_and_parse_json`


**File:** `anthropic_provider.py`
  - **Classes**: `AnthropicProvider`
    - *Methods*: `generate()`, `classify_json()`, `run_tool_agent()`, `run_agent()`, `run_chat_loop()`, `run_agent_from_messages()`, `_log_tool_call()` (Anti-Oscillation Tool Loop Guard active in tool execution loops)
  - **Functions**: `_build_system_blocks`
  - **Variables**: `THINKING_CAPABLE_MODELS`, `THINKING_BUDGETS`

**File:** `gemini_provider.py`
  - **Classes**: `GeminiProvider`
    - *Methods*: `_is_paid_key()`, `_get_api_key()`, `_handle_rate_limit_error()`, `_build_thinking_config()`, `generate()` (tuple system prompt separation, thinking headroom, unconditional auto-recovery on MAX_TOKENS), `classify_json()`, `run_tool_agent()`, `run_agent()`, `run_chat_loop()`, `run_agent_from_messages()` (Anti-Oscillation Tool Loop Guard active)
  - **Functions**: `_sanitize_schema_for_gemini`, `_check_gemini_block`
  - **Variables**: `GEMINI_MODEL_ALIASES`, `GEMINI_THINKING_LEVEL_MAP`

**File:** `openai_provider.py`
  - **Classes**: `OpenAIProvider`
    - *Methods*: `_apply_reasoning_params()` (dynamic reasoning token headroom, model-aware completion ceiling for Groq), `_build_prompt_cache_key()` (content-addressed hash monika_<sha256[:24]> for OpenAI prompt caching), `_call_chat_completions_with_recovery()` (self-healing 400 token ceiling recovery, parameter swap, prompt_cache_key retry), `_extract_usage()`, `generate()` (tuple system prompt separation), `generate_content()`, `classify_json()`, `run_tool_agent()`, `run_agent()`, `run_chat_loop()`, `run_agent_from_messages()` (Anti-Oscillation Tool Loop Guard active)
  - **Functions**: `_normalize_messages`, `_extract_message_text`, `_canonicalize_schema`

**File:** `deepseek_provider.py`
  - **Classes**: `DeepSeekProvider`

**File:** `provider_failover_classifier.py`
  - **Docstring**: Structured LLM error classification taxonomy and retry/failover decision engine (expanded with UPSTREAM_RATE_LIMIT, INVALID_REQUEST, BROKER_MARGIN_CALL, SILENT_OVERFLOW, LENGTH_STOP_OVERFLOW, COMPLETION_CEILING_EXCEEDED, HARD_QUOTA_EXHAUSTED, TRANSIENT_RATE_LIMIT).
  - **Classes**: `FailoverReason`
  - **Functions**: `classify_error()`, `extract_completion_ceiling()`

**File:** `error_classifier.py`
  - **Docstring**: Backward-compatibility shim re-exporting `FailoverReason` and `classify_error` from `provider_failover_classifier.py`.

**File:** `groq_provider.py`
  - **Classes**: `GroqProvider`
    - *Methods*: `_get_api_key()`, `_get_client_for_key()`, `_make_client()`, `_is_transient_error()`, `_handle_rate_limit_error()`, `generate()`, `classify_json()`, `run_tool_agent()`, `run_agent()`, `run_agent_from_messages()` (model-aware max_tokens clamping against capabilities ceiling)
  - **Variables**: `GROQ_MODEL_ALIASES`

**File:** `ollama_provider.py`
  - **Classes**: `OllamaProvider`
    - *Methods*: `_get_client()`, `generate()`, `classify_json()`

**File:** `openrouter_provider.py`
  - **Classes**: `OpenRouterProvider`
    - *Methods*: `_get_client_for_key()`, `_is_key_in_cooldown()`, `_get_api_key()`, `reset_cooldowns()`, `get_cooldown_status()`, `_apply_reasoning_params()`, `_handle_rate_limit_error()`, `generate()`, `generate_content()`, `classify_json()`, `run_tool_agent()`, `run_agent()`
  - **Variables**: `OPENROUTER_MODEL_ALIASES`, `_openrouter_limiter`, `_model_key_cooldowns`, `_key_cooldowns`, `_client_pool`, `_key_index`

**File:** `runtime_model_registry.py`
  - **Docstring**: Thread-safe dynamic model registry supporting live runtime model switching and hot-swaps without agent restarts.
  - **Classes**: `RuntimeModelRegistry`
    - *Methods*: `get_model()`, `set_model()`, `list_overrides()`, `reset()`
  - **Functions**: `get_model_registry()`

**File:** `capabilities.py`
  - **Classes**: `ModelCapabilities`
  - **Functions**: `get_model_capabilities()`, `get_capabilities()`, `resolve_effective_context_window()`
  - **Variables**: `MODEL_CAPABILITIES`, `DEFAULT_CAPABILITIES`

**File:** `structured_fallback.py`
  - **Classes**: `StructuredOutputResult`
  - **Functions**: `extract_and_parse_json()`, `extract_key_values_by_regex()`, `parse_structured_output()`, `invoke_structured_or_freetext()`

**File:** `llm_factory.py`
  - **Classes**:
    - `ProviderCircuitBreaker`
      - *Methods*: `can_execute()`, `record_success()`, `record_failure()`, `blacklist_model()`, `is_blacklisted()`, `get_stats()`, `reset()`
    - `LLMFactory`
      - *Methods*: `get_client_for_task()`, `_resolve_provider()`, `_resolve_thinking_level()`, `_create_client_instance()`, `_create_client_with_fallback()`
    - `FallbackClientWrapper`
      - *Methods*: `_execute_with_fallback()`, `_maybe_restore_primary()`, `set_thinking_budget()`
**File:** `pricing_catalog.py`
  - **Docstring**: Centralized AI Model Pricing Catalog re-exporting definitions and cost calculations from `utils.analytics.pricing`.
  - **Classes**: `Price`
  - **Functions**: `get_model_pricing()`, `calculate_cost()`, `cost_usd()`, `estimate_cost()`, `get_price()`, `is_free_tier()`, `infer_provider_from_model()`
  - **Variables**: `PRICING`, `FREE_TIER_MODELS`, `OPENROUTER_PRICING_MAP`

**File:** `typesafe_provider.py`
  - **Docstring**: TypeSafe (Jev) Provider: System One Decision-Making Engine. Integrates TypeSafe's Jev model family for fast, typed classification, scoring, and boolean decisions.
  - **Classes**: `TypeSafeProvider`
    - *Methods*: `_get_client()`, `classify_json()`, `generate()`, `run_chat_loop()`, `run_tool_agent()`, `ping()`

##### Folder: `trading-agent/analysis/memory`

**File:** `alpha_calculator.py`
  - **Classes**: `AlphaCalculator`

**File:** `background_review.py`
  - **Docstring**: Non-blocking asynchronous trade review engine powered by asyncio.Queue and background workers with negative constraint filtering.
  - **Classes**: `BackgroundReviewEngine`
    - *Methods*: `start()`, `stop()`, `enqueue_trade()`, `_worker_loop()`, `_review_worker()`
  - **Variables**: `DO_NOT_CAPTURE`

**File:** `chronicle_writer.py`
  - **Classes**: `ChronicleWriter` (Methods: `maybe_record_news_event`, `maybe_record_regime_shift`, `get_chronicle_context`, `seed_bootstrap_chronicles_if_empty`, `sync_macro_reality_from_file`, `get_chronicle_for_symbol`, `get_condensed_chronicle_bullets`, `get_macro_state_summary`)
  - **Variables**: `CHRONICLE_CATEGORIES`

**File:** `counterfactual_simulator.py`
  - **Docstring**: Validates candidate trading playbooks across historical trade setups before setting status to active.
  - **Classes**: `CounterfactualSimulator`
    - *Methods*: `simulate_candidate()`

**File:** `decision_log.py`
  - **Classes**: `DecisionLogger`

**File:** `failure_taxonomy.py`
  - **Classes**: `FailureCategory`, `ReasoningFailureRecord`, `FailureClassifier` (Methods: `classify_from_text`, `classify_from_metrics`)
  - **Variables**: `PREVENTATIVE_RULES`
  - **Functions**: `generate_negative_constraints()`, `get_negative_constraints_for_regime(symbol, regime, max_rules)`

**File:** `frozen_snapshot.py`
  - **Docstring**: Freeze-Snapshot Memory Engine & Prompt-Cache Preservation providing immutable, hash-verified memory snapshots.
  - **Classes**: `FrozenMemorySnapshot`, `FrozenSnapshotManager`
    - *Methods*: `get_snapshot()`, `rehydrate()`, `is_expired()`, `get_playbook()`
  - **Functions**: `get_frozen_snapshot_manager()`

**File:** `layered_memory.py`
  - **Classes**: `LayeredMemoryManager`
    - *Methods*: `get_frozen_snapshot()`, `get_stable_core_memory()`, `get_volatile_portfolio_memory()`, `get_core_memory()`, `get_symbol_memory()`, `get_macro_regime_memory()`, `get_playbook_memory()`, `_wrap_market_memory()`

**File:** `lesson_consolidator.py`
  - **Functions**: `consolidate_lessons_to_playbook`, `enforce_declarative_memory_rule`, `promote_lesson_to_playbook`, `cluster_lessons_semantically`, `auto_promote_high_confidence_rules`, `record_playbook_rule_outcome`

**File:** `negative_constraint_generator.py`
  - **Docstring**: Synthesizes actionable "DO NOT" rules from recent losing trades, reflections, and active market regimes to prevent recurring decision traps.
  - **Classes**: `NegativeConstraintGenerator`
    - *Methods*: `generate_negative_constraints_from_losses()`, `format_for_prompt()`

**File:** `outcome_linker.py`
  - **Classes**: `OutcomeLinker`
    - *Methods*: `process_closed_position()`, `process_paper_whatifs()`, `_check_path_dependent_outcome()`

**File:** `playbook_ledger.py`
  - **Docstring**: Append-only immutable audit ledger and content-addressed blob backup system for trading playbooks with 1-click rollback.
  - **Classes**: `LedgerEntry`, `PlaybookLedger`, `PlaybookState`, `PlaybookStatus`, `PlaybookMetadata`, `PlaybookLifecycleFSM`, `PlaybookLifecycleManager`
    - *Methods*: `record_mutation()`, `list_history()`, `rollback()`

**File:** `playbook_lifecycle.py`
  - **Docstring**: Autonomous lifecycle management for trading playbooks (Candidate -> Active -> Stale -> Archived) with rolling performance tracking, 48-hour cooldowns, and auto-rollback on loss streak.
  - **Classes**: `PlaybookState`, `PlaybookStatus`, `TradeRecord`, `PlaybookMetadata`, `PlaybookLifecycleFSM`, `PlaybookLifecycleManager`
    - *Methods*: `register_playbook()`, `get_status()`, `get_state()`, `get_metadata()`, `list_all_playbooks()`, `get_active_playbooks()`, `is_active()`, `revalidate()`, `record_trade_outcome()`, `evaluate_staleness()`

**File:** `playbook_linter.py`
  - **Docstring**: Strict linter for synthesized trading playbooks enforcing declarative rule structures, empirical metadata, numeric invariants, and anti-incident-log guards.
  - **Classes**: `PlaybookLintResult`, `PlaybookLinter`
    - *Methods*: `parse_frontmatter()`, `lint()`

**File:** `progressive_loader.py`
  - **Docstring**: 3-Tier progressive memory disclosure engine (Level 0 Index, Level 1 Symbol Playbook, Level 2 Tactical Reference).
  - **Classes**: `ProgressiveMemoryLoader`
    - *Methods*: `get_level0_index()`, `get_level1_playbook(symbol)`, `get_level2_tactical(symbol, topic)`

**File:** `reflector.py`
  - **Classes**: `TradeReflector`
    - *Methods*: `_verify_reflection_quality()`, `reflect_on_trade()`, `_fetch_enrichment_context()`

**File:** `session_search.py`
  - **Functions**:
    - `_detect_pgvector(session)` - Deteksi ketersediaan ekstensi pgvector di PostgreSQL
    - `compute_cosine_similarity(vec1, vec2)` - Computes cosine similarity with NumPy SIMD acceleration
  - **Classes**: `SessionSearchEngine`
    - *Methods*:
      - `__init__(self, db_path=None)`
      - `get_symbol_precedents(self, symbol, limit=3, session=None, regime=None)`
      - `_execute_symbol_precedents(self, session, clean_sym, limit, regime=None)`
      - `search(self, query, limit=5, session=None, query_vector=None)`
      - `_execute_search(self, session, query, limit, query_vector=None)`
      - `_format_reflection(self, r)`
      - `hybrid_search(self, query, symbol=None, query_vector=None, limit=5, session=None)`
      - `compute_precedent_hybrid_score(self, reflection, current_regime=None, setup_tokens=None, now=None)`
      - `get_symbol_precedents_hybrid(self, symbol, current_regime=None, setup_text=None, limit=3, session=None, query_vector=None)`
      - `_execute_symbol_precedents_hybrid(self, session, clean_sym, current_regime=None, setup_text=None, limit=3, query_vector=None)`
      - `index_session(self, *args, **kwargs)`
      - `update_session_outcome(self, *args, **kwargs)`
      - `index_reflection(self, session, reflection_id, custom_text=None)`
      - `update_reflection_outcome(self, session, reflection_id, outcome_data)`
**File:** `skill_crystallizer.py`
  - **Classes**: `SkillCrystallizer`, `ReadBeforeWriteGuard`
    - *Methods*: `evaluate_and_crystallize()`, `_crystallize_cluster()`, `_synthesize_tactical_rules()`, `get_crystallized_skills_for_symbol()`, `is_skill_deprecated()`, `deprecate_skill()`, `record_skill_attribution()`, `curate_and_prune_skills()`, `record_read()`, `can_write()`
**File:** `skill_curator.py`
  - **Docstring**: Autonomous Background Skill Curator managing Active -> Stale -> Archived lifecycle and deduplication.
  - **Classes**: `SkillCurator`
    - *Methods*: `calculate_similarity()`, `curate_db_rules()`, `curate_files()`, `run_once()`, `run_background_loop()`
**File:** `skill_evolution.py`
  - **Classes**: `MicroPlaybookCompiler`
    - *Methods*: `__init__(settings=None)`, `ensure_playbooks_dir()`, `evaluate_and_compile()`, `_synthesize_micro_playbook()`, `_promote_playbook()`
**File:** `working_scratchpad.py`
  - **Classes**: `WorkingScratchpad`
    - *Methods*: `to_system_injection()`, `update()`, `to_dict()`, `from_dict()`, `get_summary()`

##### Folder: `trading-agent/analysis/mcp`
**File:** `__init__.py`
**File:** `protocol.py`
  - **Classes**: `JsonRpcRequest`, `JsonRpcResponse`
  - **Functions**: `make_error_response()`, `make_result_response()`
**File:** `server.py`
  - **Docstring**: Monika Model Context Protocol (MCP) server exposing quantitative analysis, open positions, status, and playbooks over stdio JSON-RPC.
  - **Classes**: `MonikaMcpServer`
    - *Methods*: `get_tool_definitions()`, `handle_tool_call()`, `handle_request()`, `run_stdio()`
  - **Functions**: `run_mcp_server()`
**File:** `client.py`
  - **Docstring**: Model Context Protocol (MCP) client manager connecting to external MCP servers and bridging remote tools into Monika ToolRegistry.
  - **Classes**: `McpServerProcess`, `McpBridgeHandler`, `McpClientManager`
    - *Methods*: `start()`, `send_request()`, `list_tools()`, `call_tool()`, `initialize_servers()`, `stop()`

###### Folder: `trading-agent/analysis/mcp/servers`
**File:** `__init__.py`
**File:** `sqlite_server.py`
  - **Docstring**: Free read-only SQLite metrics and checkpointer MCP server.
  - **Classes**: `SqliteMcpServer`
**File:** `filesystem_server.py`
  - **Docstring**: Free sandboxed read-only filesystem MCP server for playbooks and trading files.
  - **Classes**: `FilesystemMcpServer`
**File:** `fetch_server.py`
  - **Docstring**: Free public web text extraction MCP server.
  - **Classes**: `FetchMcpServer`

#### Folder: `trading-agent/backtest`

**File:** `__init__.py`

**File:** `decision_memory.py`
  - **Global Variables**: logger
  - **Classes**:
    - `DecisionMemoryManager`
      - *Methods*:
        - `__init__(self)`
        - `log_decision(self)`
        - `update_outcome_and_reflect(self)`
        - `get_past_decisions_context(self)`

**File:** `monte_carlo_engine.py`
  - **Classes**:
    - `MonteCarloStressTester`
      - *Docstring*: Institutional Monte Carlo Stress Tester & Scenario Shock Engine.
      - *Methods*:
        - `__init__(self, seed: int = 42)`
        - `run_permutation_drawdown_test(self, trade_returns, num_simulations, initial_equity)`
        - `run_slippage_spread_shock_test(self, trade_returns, slippage_multipliers, base_friction_pct, num_simulations, initial_equity)`

**File:** `offline_signal_engine.py`
  - **Global Variables**: `logger`
  - **Classes**:
    - `OfflineSignalEngine`
      - *Docstring*: Vectorized version of structure.py and confluence_calculator.py using Pandas DataFrames for fast offline backtesting.
      - *Methods*:
        - `__init__(self, settings: Dict[str, Any])`
        - `_normalize_df(self, df: pd.DataFrame) -> pd.DataFrame`
        - `_calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series`
        - `_calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series`
        - `_calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series`
        - `generate_signals(self, df: pd.DataFrame) -> pd.DataFrame`
        - `calculate_stops_and_targets(self, df: pd.DataFrame, risk_reward_ratio: float = 2.0) -> pd.DataFrame`

**File:** `outcome_evaluator.py`
  - **Global Variables**: logger
  - **Classes**:
    - `OutcomeEvaluator`
      - *Docstring*: Cek bar-by-bar apakah trade hit TP/SL.
      - *Methods*:
        - `__init__(self, max_holding_hours, custom_friction_profile)`
        - `calibrate_from_db(self, session, lookback_days, as_of)`
        - `evaluate_trade(self)`
        - `get_contract_size(symbol: str) -> float`
        - `_calculate_outcome(self)`
        - `_get_session_spread_multiplier(self)`
        - `_get_volatility_slippage(self)`

**File:** `alpha_validation.py`
  - **Docstring**: Alpha validation metrics (directional bias, half-consistency, cost stress test).
  - **Classes**: `AlphaValidation`
  - **Functions**: `validate_alpha()`, `_calculate_sortino()`

**File:** `benchmark_tracker.py`
  - **Docstring**: Benchmark comparison tracker for backtesting (Alpha, Beta, Information Ratio, Tracking Error, Up/Down Capture Ratio).
  - **Classes**: `BenchmarkMetrics`, `BenchmarkTracker`
    - *Methods*:
      - `__init__(self, benchmark_symbol, ann_factor)`
      - `compute_metrics(self, strategy_returns, benchmark_returns, risk_free_rate)`

**File:** `statistical_tests.py`
  - **Docstring**: Statistical multiple-testing corrections: PSR, E[max], DSR, and FDR using Python stdlib.
  - **Functions**: `probabilistic_sharpe_ratio()`, `expected_max_sharpe()`, `deflated_sharpe_ratio()`, `compute_sample_moments()`, `benjamini_hochberg()`

**File:** `walk_forward_engine.py`
  - **Global Variables**: `logger`
  - **Classes**:
    - `WalkForwardFold`
    - `WalkForwardResult`
    - `WalkForwardEngine`
      - *Docstring*: Walk-Forward Optimization & Validation Engine with purging, embargo, DSR, and alpha validation.
      - *Methods*:
        - `__init__(self, start_date, end_date, is_window_days, oos_window_days, step_days, settings, mode, step_hours, purge_days, embargo_pct, n_trials)`
        - `generate_folds(self)`
        - `run(self)`
        - `generate_markdown_report(self, result)`

**File:** `point_in_time_engine.py`
  - **Global Variables**: logger, BacktestMode
  - **Classes**:
    - `PointInTimeBacktestEngine`
      - *Methods*:
        - `__init__(self)`
        - `_record_and_evaluate_trade(self, trade)`
        - `_settle_trades_up_to(self, as_of)`
        - `_resolve_trade(self, trade, evaluator)`
        - `execute_trade_parity(self, session, analysis)`
        - `get_point_in_time_data(self, session, model_cls, as_of, symbol, vintage_date, lookback_days)`
        - `run(self)`
        - `_run_full_mode(self)`
        - `_run_replay_mode(self)`
        - `_run_langgraph_parity_mode(self)`

**File:** `report_generator.py`
  - **Global Variables**: logger
  - **Classes**:
    - `ReportGenerator`
      - *Methods*:
        - `__init__(self)`
        - `calculate_metrics(self)`
        - `compute_monte_carlo_drawdowns(self, num_simulations)`
        - `_resample_daily_returns(self)`
        - `to_dict(self)`
        - `print_summary(self)`

**File:** `time_machine.py`
  - **Functions**:
    - `get_virtual_now()`
    - `is_backtest_mode()`
  - **Classes**:
    - `TimeMachine`
      - *Docstring*: Context manager for backtest mode.
      - *Methods*:
        - `__init__(self)`

#### Folder: `trading-agent/graph`

**File:** `state.py`
  - **Classes**: `TradingState`, `TradingSummary`, `AssetDecisionSummary`
  - **Functions**: `merge_dicts()`, `merge_lists()`

**File:** `workflow.py`
  - **Functions**: `build_trading_graph()`

##### Folder: `trading-agent/graph/nodes`

**File:** `data_node.py`
  - **Functions**: `fetch_data_node()`

**File:** `fundamental_node.py`
  - **Functions**: `fundamental_analysis_node()`

**File:** `per_asset_node.py`
  - **Functions**: `per_asset_analysis_node()`

**File:** `debate_node.py`
  - **Docstring**: Backward-compatible facade delegating to debate subgraph (`graph/nodes/debate/subgraph.py`).
  - **Functions**: `debate_node()`

**File:** `risk_gate_node.py`
  - **Functions**: `risk_gate_node()`

**File:** `plan_refinement_node.py`
  - **Functions**: `plan_refinement_node()`

**File:** `execution_node.py`
  - **Functions**: `execution_node()`

**File:** `reflection_node.py`
  - **Functions**: `reflection_node()`

#### Folder: `trading-agent/config`

**File:** `atomic_writer.py`
  - **Docstring**: Thread-safe atomic YAML configuration writer with ruamel.yaml comment preservation, tempfile sync, and automatic backup rotation.
  - **Classes**: `AtomicConfigWriter`
    - *Methods*: `_rotate_backups()`, `write()`, `update_in_place()`

**File:** `config_manager.py`
  - **Docstring**: Dynamic configuration manager with pub/sub event bus for zero-downtime hot-reloads of risk and execution parameters.
  - **Classes**: `ConfigManager`
    - *Methods*: `register_subscriber()`, `notify_subscribers()`, `update_setting()`, `get_setting()`

**File:** `config_migrations.py`
  - **Docstring**: Configuration version migrations auto-healing and backfilling institutional schemas.
  - **Variables**: `CURRENT_CONFIG_VERSION`, `DEFAULT_SUBSETS`
  - **Functions**: `migrate_settings()`, `check_and_migrate_file()`

**File:** `hot_reload.py`
  - **Classes**: `RiskParameterReloader` (Methods: `check_and_reload()`, `watch_and_reload()`)

**File:** `key_validator.py`
  - **Docstring**: Configuration key validator with fuzzy matching and candidate suggestion.
  - **Functions**: `validate_config_key()`

**File:** `migrations.py`
  - **Docstring**: Configuration schema version migrations and fail-closed parser validation.
  - **Variables**: `CURRENT_CONFIG_VERSION`, `MIGRATIONS`
  - **Functions**: `get_config_version()`, `migrate_config()`, `require_parseable_config()`

**File:** `schemas.py`
  - **Docstring**: Pydantic schema models validating application settings and YAML configurations at startup.
  - **Classes**: `SubscriptableConfig`, `RiskConfig`, `ExecutionConfig`, `PaperTradingConfig` (attributes: `initial_balance`, `tp_detection_method`, `realistic_sl_tp_conflict`, `max_paper_trade_holding_hours`, `spread_realistic_multiplier`, `spread_multipliers`), `SchedulerConfig`, `IndicatorsConfig`, `TradingConfig`, `TaskRoleConfig` (attributes: `primary`, `fallback_1..10`, `fallback`, `fallbacks`, `max_cost_per_call`), `LLMConfig`, `UIConfig`, `HarnessConfig`, `EvalsConfig`, `BenchmarkConfig`, `TradingAgentConfig`
  - **Functions**: `validate_config()`

**File:** `security.py`
  - **Docstring**: Security guardrails validating environment mutations and preventing leakage of sensitive credentials.
  - **Variables**: `BLOCKED_ENV_VARS`
  - **Functions**: `validate_env_mutation(key, value)`

**File:** `settings.py`
  - **Global Variables**: logger, DEFAULT_MONTHLY_BUDGET_USD, _LAST_KNOWN_GOOD_SETTINGS
  - **Functions**:
    - `load_settings()`
      - *Docstring*: Load master settings from YAML configuration file.
    - `load_settings_with_lkg()`
      - *Docstring*: Load settings with Last-Known-Good memory cache fallback.
    - `require_parseable_config()`
      - *Docstring*: Fail-closed validation ensuring config is parseable.
    - `load_all_config()`
      - *Docstring*: Load full configuration dictionary from YAML file (settings.yaml).
    - `get_settings()`
      - *Docstring*: Backward-compatible alias for `load_settings()`.

**File:** `settings.yaml`
  - **Description**: Global trading agent configuration (trading parameters, risk management, execution, schedulers, and llm.task_roles including `summarizer` and `context_compaction`).


**File:** `MACRO_REALITY.md`
  - **Docstring**: Ground-truth factual macroeconomic & geopolitical baseline store (verified 2026 facts: Fed Chair Kevin Warsh, Treasury Sec Scott Bessent, Strait of Hormuz / Red Sea disruptions, Russia-Ukraine war, Trump tariffs, BoJ Ueda rate hikes).

**File:** `TRADING_SOUL.md`
  - **Docstring**: Core identity and operating philosophy document (Layer 0 permanent memory).

#### Folder: `trading-agent/data_sources`

**File:** `__init__.py`

**File:** `cftc_cot.py`
  - **Global Variables**: logger, DISAGGREGATED_DATASET, DISAGGREGATED_URL, FINANCIAL_DATASET, FINANCIAL_URL, COMMODITY_CODES
  - **Classes**:
    - `CFTCCOTFetcher`
      - *Docstring*: COT report fetcher for CFTC Socrata API.
      - *Methods*:
        - `__init__(self, session, config)`
        - `fetch_all(self)`
        - `_fetch_and_save(self, url, params, market_name, market_code)`
        - `_parse_date(date_str)`
        - `_int(value)`

**File:** `circuit_breaker.py`
  - **Docstring**: Data Feed Circuit Breaker & Freshness Sentinel monitoring MT5 ticks, FRED macro series, Finnhub news, and Economic Calendar.
  - **Classes**: `FeedStatus`, `DataFeedCircuitBreaker`
    - *Methods*: `record_feed_heartbeat()`, `check_feed()`, `is_feed_stale()`, `trip()`, `reset()`, `is_tripped()`, `get_tripped_feeds()`, `evaluate_all_feeds()`, `get_health_report()`
  - **Functions**: `get_data_feed_circuit_breaker()`, `record_feed_heartbeat()`

**File:** `bond_yields_fetcher.py`
  - **Global Variables**: `logger`, `ECB_AAA_YIELD_URL`, `ECB_AAA_2Y_URL`, `FRED_BASE_URL`, `FRED_BOND_SERIES`
  - **Classes**:
    - `BondYieldFetcher`
      - *Docstring*: Fetcher yield obligasi pemerintah 10 tahun dan 2 tahun internasional (Jerman, UK, Jepang, Australia, US) menggunakan ECB Data Portal API, CentralBankWatch, dan FRED API fallback.
      - *Methods*:
        - `__init__(self, session, fred_api_key=None)`
        - `fetch(self, period="15d")` -> `dict[str, int]`
        - `_fetch_ecb_yield(self, url=ECB_AAA_YIELD_URL, label="DE_10Y")` -> `int`
        - `_fetch_fred_bond_series(self, series_id, label, limit=15)` -> `int`

**File:** `bond_yields_yfinance.py`
  - *Docstring*: Backward-compatible shim importing from bond_yields_fetcher.

**File:** `central_bank_watch.py`
  - **Global Variables**: `logger`, `CBW_BASE_URL`, `CBW_YIELD_URL`, `CARD_CLASS_TO_BANK`, `DEFAULT_HEADERS`
  - **Classes**:
    - `CentralBankWatchFetcher`
      - *Docstring*: Fetcher ekspektasi keputusan suku bunga pasar (Hike, Hold, Cut) dan kurva yield sovereign (2Y & 10Y) 5 bank sentral utama (Fed, ECB, BoE, BoJ, RBA) tanpa browser headless via HTTP async.
      - *Methods*:
        - `__init__(self, session)`
        - `fetch_expectations(self)` -> `dict`
        - `fetch_sovereign_yields(self)` -> `dict`
        - `fetch_all(self)` -> `dict`

**File:** `coinglass_funding.py`
  - **Global Variables**: `logger`, `BINANCE_FUNDING_URL`, `BYBIT_TICKERS_URL`, `COINGLASS_URL`
  - **Classes**:
    - `CoinglasFundingFetcher`
      - *Docstring*: Fetcher data funding rate BTC multi-source (Binance Futures primary, Bybit secondary, Coinglass tertiary).
      - *Methods*:
        - `__init__(self, session)`
        - `fetch(self)` -> `dict`

**File:** `dxy_yfinance.py`
  - **Global Variables**: logger, DXY_TICKER
  - **Classes**:
    - `DXYFetcher`
      - *Docstring*: US Dollar Index (DXY) market data fetcher from Yahoo Finance.
      - *Methods*:
        - `__init__(self)`
        - `_download(self)`
        - `get_latest(self) -> Optional[DXYData]`

**File:** `eia_oil_inventory.py`
  - **Global Variables**: logger, EIA_URL
  - **Classes**:
    - `EIAInventoryFetcher`
      - *Docstring*: Mengambil data inventaris minyak mentah komersial AS (series WCESTUS1).
      - *Methods*:
        - `__init__(self)`

**File:** `fear_greed.py`
  - **Global Variables**: logger, FEAR_GREED_URL
  - **Classes**:
    - `FearGreedFetcher`
      - *Docstring*: Mengambil Fear & Greed Index dan menyimpannya ke SystemConfig.
      - *Methods*:
        - `__init__(self)`
        - `_interpret(self)`

**File:** `fred_treasury_yield.py`
  - **Global Variables**: logger, FRED_BASE_URL, TENOR_SERIES, INTEREST_RATE_SERIES, SERIES_TO_TENOR, SERIES_TO_BANK
  - **Classes**:
    - `FREDDataFetcher`
      - *Docstring*: Retrieves treasury yields and benchmark interest rates from FRED API.
      - *Methods*:
        - `__init__(self)`
        - `_parse_date(self)`

**File:** `vix_yfinance.py`
  - **Global Variables**: logger, VIX_TICKER
  - **Classes**:
    - `VIXFetcher`
      - *Docstring*: Retrieves daily closing VIX volatility data from Yahoo Finance.
      - *Methods*:
        - `__init__(self)`
        - `_download(self)`

**File:** `web_search.py`
  - **Global Variables**: `logger`, `_global_web_search_service`
  - **Functions**:
    - `get_web_search_service(settings=None)`
      - *Docstring*: Singleton accessor for WebSearchService.
  - **Classes**:
    - `WebSearchService`
      - *Docstring*: Asynchronous web search service with key rotation and multi-tier fallback.
      - *Properties*: `tavily_keys`, `key_count`
      - *Methods*:
        - `__init__(self, settings=None)`
        - `_get_next_tavily_key(self)`
        - `_get_cache_key(self, query, topic, time_range, max_results)`
        - `search(self, query, topic="finance", search_depth="advanced", time_range="day", max_results=5)`
        - `_search_tavily_with_rotation(self, query, topic, search_depth, time_range, max_results)`
        - `_search_brave(self, query, max_results=5)`
        - `_search_duckduckgo(self, query, max_results=5)`

**File:** `academic_search.py`
  - **Classes**:
    - `AcademicSearchClient`
      - *Docstring*: Client for querying academic research papers on arXiv via public API.
      - *Methods*:
        - `__init__(self, timeout_seconds=15.0)`
        - `search_papers(self, query, max_results=5)`

**File:** `validators.py`
  - **Global Variables**: `MAX_OHLCV_STALE_DAYS`, `INTRADAY_CACHE_TTL_SECONDS`
  - **Functions**:
    - `validate_ohlcv_freshness()`
    - `is_intraday_cache_expired()`

**File:** `web_reader.py`
  - **Global Variables**: `MAX_BODY_BYTES`, `DEFAULT_HEADERS`, `DISALLOWED_TAGS`, `CHALLENGE_PHRASES`
  - **Functions**:
    - `is_challenge_or_empty(status, content, html)`
    - `is_prohibited_ip(ip_str)`
    - `validate_url_ip(url)`
  - **Classes**:
    - `WebReader`
      - *Docstring*: Service to fetch full webpage content and extract clean text with headless browser fallback.
      - *Methods*:
        - `__init__(self, max_chars=12000, timeout_seconds=12.0, max_body_bytes=MAX_BODY_BYTES, browser_fallback=True, browser_timeout_seconds=20.0)`
        - `_read_url_with_browser_sync(self, url)`
        - `_read_url_with_browser(self, url)`
        - `read_url(self, url)`
        - `_extract_content(self, url, html)`

#### Folder: `trading-agent/database`

**File:** `adapters.py`
  - **Global Variables**: logger, CURRENCY_KEYWORDS
  - **Functions**:
    - `extract_currency_tags()`
      - *Docstring*: Extracts currency tags from text via keyword matching.
    - `parse_timestamp()`
      - *Docstring*: Parsing berbagai format timestamp menjadi UTC datetime (timezone-aware).
    - `_now_utc()`
    - `_cross_check_all_currencies_priced_in()`
    - `scraped_news_to_model()`
      - *Docstring*: Konversi dataclass ScrapedNews menjadi model ORM NewsItem.
    - `calendar_event_to_model()`
      - *Docstring*: Konversi dataclass CalendarEvent menjadi model ORM EconomicCalendar.

**File:** `safe_ops.py`
  - **Global Variables**: logger
  - **Functions**:
    - `safe_commit()`
      - *Docstring*: Safely commits transactions with automatic rollback on failure to prevent session corruption.
    - `scraped_tweet_to_model()`
      - *Docstring*: Konversi dataclass ScrapedTweet menjadi model ORM NewsItem (sumber='twitter').
    - `fed_meeting_to_models()`
      - *Docstring*: Konversi dataclass FedMeeting menjadi model ORM FedWatchProbability.

**File:** `cleanup.py`
  - **Global Variables**: logger
  - **Functions**:
    - `cleanup_old_data(session, settings=None)`
      - *Docstring*: Prunes historical records to prevent database bloat, utilizing retention policy from settings['data_retention_days'].
    - `drop_expired_partitions(session, older_than_days=180)`
      - *Docstring*: Drops PostgreSQL partitions from price_ohlcv_partitioned for MVCC dead-tuple elimination.
    - `reset_paper_trading_history(session, create_backup=True, backup_dir=None, unlock_all=True)`
      - *Docstring*: Mereset seluruh riwayat paper trading dan data terkait secara aman, mereset loss streak ke 0, dan membuka kuncian sistem.

**File:** `async_db.py`
  - **Global Variables**: AsyncSessionLocal, async_engine
  - **Functions**:
    - `get_session()`
      - *Docstring*: Async generator yielding an AsyncSession with automatic commit/rollback.
    - `get_engine()`
      - *Docstring*: Returns the shared SQLAlchemy async engine instance.

**File:** `db.py`
  - **Global Variables**: logger, DATABASE_URL, _IN_MEMORY_EXECUTION_LOCKS
  - **Functions**:
    - `transactional_advisory_lock(session, lock_key)`
      - *Docstring*: Acquires PostgreSQL transaction advisory lock with fail-closed guarantee and per-key in-memory fallback.
    - `close_db()`

**File:** `event_store.py`
  - **Docstring**: Append-only asynchronous event store for audit, state transitions, and trace persistence.
  - **Classes**: `TradingEventStore`
    - *Methods*: `append()`, `query_by_trace()`, `query_recent()`

**File:** `models.py`
  - **Functions**:
    - `_utcnow()`
      - *Docstring*: Mengembalikan waktu saat ini dalam UTC (timezone-aware).
  - **Classes**:
    - `Base`
    - `TradingEvent`
      - *Docstring*: Append-only event store model for auditing and event-driven observability.
      - *Class Variables*: __tablename__, __table_args__
    - `Trade`
      - *Docstring*: Legacy trade model (retained for backward compatibility).
      - *Class Variables*: __tablename__
    - `NewsItem`
      - *Docstring*: Aggregated news articles from web scrapers and RSS feeds.
      - *Class Variables*: __tablename__, __table_args__
    - `NewsDigest`
      - *Docstring*: Compressed news digest generated for token-efficient LLM context.
      - *Class Variables*: __tablename__
    - `NewsDigestSlice`
      - *Docstring*: Rolling 2-hour digest snapshot per currency.
      - *Class Variables*: __tablename__, __table_args__
    - `MarketChronicle`
      - *Docstring*: Persistent chronicle of significant macroeconomic events.
      - *Class Variables*: __tablename__
    - `EconomicCalendar`
      - *Docstring*: Kalender ekonomi (rilis data makro).
      - *Class Variables*: __tablename__
    - `TreasuryYield`
      - *Docstring*: US Government treasury bond yields from FRED.
      - *Class Variables*: __tablename__, __table_args__
    - `BondYieldData`
      - *Docstring*: Yield obligasi pemerintah 10 tahun internasional (Jerman, UK, Jepang, Australia).
      - *Class Variables*: __tablename__, __table_args__
    - `InterestRate`
      - *Docstring*: Suku bunga bank sentral (FED, ECB, BOE, BOJ, RBA).
      - *Class Variables*: __tablename__
    - `CentralBankRateExpectation`
      - *Docstring*: Ekspektasi keputusan suku bunga bank sentral global (Fed, ECB, BoE, BoJ, RBA) mencakup probabilitas Hike %, Hold %, Cut %, tanggal rapat, dan derajat priced-in.
      - *Class Variables*: __tablename__, __table_args__
    - `FedWatchProbability`
      - *Docstring*: Federal Reserve rate target probabilities from CME FedWatch.
      - *Class Variables*: __tablename__
    - `COTReport`
      - *Docstring*: Commitment of Traders (COT) report — institutional positioning from CFTC API.
      - *Class Variables*: __tablename__, __table_args__
    - `VIXData`
      - *Docstring*: CBOE VIX volatility index from Yahoo Finance.
      - *Class Variables*: __tablename__
    - `DXYData`
      - *Docstring*: Daily US Dollar Index (DXY) series from Yahoo Finance.
      - *Class Variables*: __tablename__
    - `PriceOHLCV`
      - *Docstring*: Historical and live OHLCV price bars from MT5.
      - *Class Variables*: __tablename__, __table_args__
    - `TechnicalIndicator`
      - *Docstring*: Indikator teknikal terhitung (MA, RSI, MACD, dll).
      - *Class Variables*: __tablename__, __table_args__
    - `SwingPoint`
      - *Docstring*: Structural swing highs and swing lows identified from price action.
      - *Class Variables*: __tablename__, __table_args__
    - `SRZone`
      - *Docstring*: Support and resistance liquidity zones clustered from swing points.
      - *Class Variables*: __tablename__, __table_args__
    - `LiquidityZone`
      - *Docstring*: Zona likuiditas di atas/bawah swing points signifikan.
      - *Class Variables*: __tablename__, __table_args__
    - `FVGZone`
      - *Docstring*: Fair Value Gap (ICT/SMC concept).
      - *Class Variables*: __tablename__, __table_args__
    - `OrderBlock`
      - *Docstring*: Order Block (SMC concept) — candle terakhir sebelum pergerakan impulsif.
      - *Class Variables*: __tablename__, __table_args__
    - `StructureBreak`
      - *Docstring*: Break of Structure (BOS) / Change of Character (ChoCH).
      - *Class Variables*: __tablename__, __table_args__
    - `FundamentalBrief`
      - *Docstring*: Macroeconomic fundamental intelligence brief from Stage 1.
      - *Class Variables*: __tablename__, analyses
      - *Properties*: currency_bias, macro_narrative
    - `AssetAnalysis`
      - *Docstring*: Comprehensive per-asset analysis decisions from Stage 2.
      - *Class Variables*: __tablename__, brief, triggers, __table_args__
      - *Properties*: entry_price, invalidation_condition
      - *Debate & Context Tracking*: debate_bull_thesis, debate_bear_dissent, debate_verdict, debate_reason, decision_source, was_debate_modified, was_ssvp_suppressed
      - *Pairs Trading*: pair_group_id
    - `TradeTrigger`
      - *Docstring*: Stores vetted AI trading signals awaiting risk gate clearance.
      - *Class Variables*: __tablename__
    - `MT5Signal`
      - *Docstring*: Korelasi antara hasil analisis AI dan eksekusi MT5.
      - *Class Variables*: __tablename__, analysis
    - `InvalidOrderStateTransitionError`
      - *Docstring*: Raised when an illegal order lifecycle state transition is attempted.
    - `OrderStatus`
      - *Docstring*: Standardized 11-state order lifecycle enum with crash-idempotent semantics: PENDING_SUBMIT, INTENT_COMMITTED, SUBMITTED, ACCEPTED, PARTIALLY_FILLED, FILLED, REJECTED, EXPIRED, CANCELLED, INTERRUPTED, ABORT_REQUESTED.
      - *Properties*: is_terminal
      - *Methods*: can_transition_to(self, target)
    - `Order`
      - *Docstring*: Standalone order entity with typed state machine lifecycle, crash-idempotent replay policy ('never'), and intent/settlement timestamp tracking.
      - *Class Variables*: __tablename__, events, analysis, positions, replay_policy, intent_committed_at, settlement_committed_at
      - *Properties*: is_terminal
      - *Methods*: can_transition_to(self, target), transition_to(self, new_status, reason, ...)
    - `OrderEvent`
      - *Docstring*: Chronological audit trail log of order state transitions.
      - *Class Variables*: __tablename__, order
    - `Position`
      - *Docstring*: Active and closed trading positions tracking PnL and telemetry.
      - *Class Variables*: __tablename__, __table_args__, __allow_unmapped__, _mt5_close_reason, _mt5_exit_price, order_id, initial_volume, requested_volume, slippage_pips, partially_filled
      - *Pairs Trading*: pair_group_id
    - `TradeOutcome`
      - *Docstring*: Link antara AssetAnalysis → Position → actual P&L outcome.
      - *Class Variables*: __tablename__, __table_args__, was_debate_modified, decision_source
    - `PaperTradeRecord`
      - *Docstring*: Persistent paper trading tracker for simulated execution.
      - *Class Variables*: __tablename__, __table_args__, partially_filled, requested_lot
    - `OrderLog`
      - *Docstring*: Log of every order attempt (successful, rejected, or aborted).
      - *Class Variables*: __tablename__
    - `RiskState`
      - *Docstring*: Status risk harian — drawdown, PnL, pause status.
      - *Class Variables*: __tablename__
    - `TelegramConversation`
      - *Docstring*: Telegram conversation history for LLM context.
      - *Class Variables*: __tablename__
    - `TelegramTopicBinding`
      - *Docstring*: Telegram forum topic bindings for multi-turn session isolation and focus pairs.
      - *Class Variables*: __tablename__, __table_args__
    - `ActivityLog`
      - *Docstring*: Comprehensive system activity log for auditing.
      - *Class Variables*: __tablename__
      - *Methods*:
        - `validate_related_id()`
          - *Docstring*: Validasi agar related_id selalu berupa integer atau None, mencegah error asyncpg invalid input.
    - `TokenUsageLog`
      - *Docstring*: LLM API token consumption log for cost tracking and auditing.
      - *Class Variables*: __tablename__
    - `SystemConfig`
      - *Docstring*: Key-value storage for runtime configuration.
      - *Class Variables*: __tablename__
      - *Methods*:
        - `upsert()`
          - *Docstring*: Upsert key-value record safely.
    - `CyclePerformance`
      - *Docstring*: Tracks each analysis cycle for performance monitoring.
      - *Class Variables*: __tablename__
    - `ConfluenceFactorOutcome`
      - *Docstring*: IMP-11: Track individual confluence factor contribution per trade outcome.
      - *Class Variables*: __tablename__, __table_args__
    - `DecisionReflection`
      - *Docstring*: Decision Memory: Post-trade reflection for live trades and counterfactual what-ifs.
      - *Class Variables*: __tablename__, __table_args__
      - *Properties*: `pnl` (alias for `outcome_pnl_usd`)
    - `BacktestRun`
      - *Class Variables*: __tablename__
    - `BacktestTrade`
      - *Class Variables*: __tablename__
    - `DecisionMemory`
      - *Class Variables*: __tablename__
    - `PrescreenLog`
      - *Docstring*: Log tracking the Haiku prescreen decisions (skip/analyze) and calibration data.
      - *Class Variables*: __tablename__, __table_args__
    - `NewsClassificationOutcome`
      - *Class Variables*: __tablename__, __table_args__
    - `CandidateLesson`
      - *Docstring*: Candidate empirical trading lesson pending out-of-sample shadow validation.
      - *Class Variables*: __tablename__
    - `TimesFMForecast`
      - *Docstring*: Google TimesFM 3.0 multi-step probabilistic forecasts and quantiles.
      - *Class Variables*: __tablename__, __table_args__
    - `ContextSpillBlob`
      - *Docstring*: PostgreSQL storage for spilled tool observation payloads with offloaded blob management.
      - *Class Variables*: __tablename__, __table_args__
    - `PlaybookRuleAttribution`
      - *Docstring*: Playbook rule outcome attribution and closed-loop evolution tracking.
      - *Class Variables*: __tablename__, __table_args__
    - `UserMarketIntel`
      - *Docstring*: Market intelligence and steering directives supplied by operator via Telegram.
      - *Class Variables*: __tablename__, __table_args__
      - *Properties*: `affected_symbols_list`, `metadata_dict`
      - *Methods*:
        - `__init__(self, **kwargs)`
    - `TradePlan`
      - *Docstring*: Multi-phase stateful trade plan spanning probe and runner execution legs.
      - *Class Variables*: __tablename__, __table_args__
    - `TradePlanLeg`
      - *Docstring*: Individual execution leg within a multi-phase trade plan (probe or runner).
      - *Class Variables*: __tablename__, __table_args__
    - `TelegramTopicBinding`
      - *Docstring*: Forum topic binding isolating chat sessions and persistent symbol focus.
      - *Class Variables*: __tablename__, __table_args__
    - `CycleEvent`
      - *Docstring*: Event-sourced analytical and execution decision ledger for quantitative audit trails.
      - *Class Variables*: __tablename__, __table_args__


##### Folder: `trading-agent/database/domain_models`
**File:** `__init__.py`
  - **Docstring**: Modular domain model package re-exporting models partitioned by functional domain.
**File:** `base.py`
  - **Classes**: `Base`
  - **Functions**: `_utcnow`
**File:** `market.py`
  - **Docstring**: Market domain models: price data, SMC structure zones, yield curves, FedWatch.
  - **Classes**: `PriceOHLCV`, `TreasuryYield`, `BondYieldData`, `FedWatchProbability`, `CentralBankRateExpectation`, `TimesFMForecast`, `SMCStructureZone`
**File:** `trading.py`
  - **Docstring**: Execution and order domain models: trades, positions, triggers, plans.
  - **Classes**: `Trade`, `Position`, `TradeHistory`, `ActiveTrigger`, `TradePlan`, `TradePlanLeg`, `BacktestRun`, `BacktestTrade`
**File:** `memory.py`
  - **Docstring**: Memory and reflection domain models: lessons, chronicles, outcome attributions.
  - **Classes**: `DecisionReflection`, `DecisionMemory`, `MarketChronicle`, `CandidateLesson`, `ConfluenceFactorOutcome`, `PlaybookRuleAttribution`
**File:** `analysis.py`
  - **Docstring**: Analysis stage domain models: fundamental briefs, asset evaluations, prescreens.
  - **Classes**: `FundamentalBrief`, `AssetAnalysis`, `PrescreenLog`, `TimesFMForecast`
**File:** `system.py`
  - **Docstring**: System domain models: event store, audit tokens, system configuration, context spills.
  - **Classes**: `TradingEvent`, `TokenUsageLog`, `ActivityLog`, `SystemConfig`, `CyclePerformance`, `ContextSpillBlob`, `UserMarketIntel`, `TelegramTopicBinding`
**File:** `news.py`
  - **Docstring**: News and macro event domain models: scraped items, digests, calendar events.
  - **Classes**: `NewsItem`, `NewsDigest`, `NewsDigestSlice`, `EconomicCalendar`, `NewsClassificationOutcome`

##### Folder: `trading-agent/database/migrations`

**File:** `env.py`
  - **Functions**:
    - `run_migrations_offline()`
      - *Docstring*: Run migrations in 'offline' mode.
    - `run_migrations_online()`
      - *Docstring*: Run migrations in 'online' mode.

###### Folder: `trading-agent/database/migrations/archive`
  - *Description*: Archived scratch SQL migration scripts.

###### Folder: `trading-agent/database/migrations/versions`
  - *Description*: Production Alembic revision scripts.
  - **Files**:
    - `n1a2b3c4d5e6_make_decision_reflections_analysis_id_nullable.py`: Alembic revision making `decision_reflections.analysis_id` column nullable to support independent reflection records.
    - `q1a2b3c4d5e6_add_position_partial_fill_and_slippage_columns.py`: Alembic revision adding partial fill tracking and slippage columns to `positions` and `paper_trade_records`.

#### Folder: `trading-agent/evals`

**File:** `eval_metrics.py`
  - **Docstring**: Core evaluation metrics and A/B comparison engine computing accuracy, grounding pass rates, R:R capture, and Brier calibration scores.
  - **Classes**: `DecisionEvaluation`, `AggregateMetrics`, `ABReport`
  - **Functions**: `compute_brier_score()`, `aggregate_eval_metrics()`, `compare_ab_evaluations()`
**File:** `eval_runner.py`
  - **Docstring**: Automated A/B Evaluation Harness and experiment runner benchmarking prompt and model variants against golden fixtures.
  - **Classes**: `ABEvalRunner`
    - *Methods*: `load_fixtures()`, `evaluate_single_decision()`, `run_ab_benchmark()`
**File:** `runner.py`
  - **Docstring**: Institutional zero-LLM programmatic market evaluation runner executing deterministic rules and geometry oracles against golden fixtures.
  - **Classes**: `EvaluationResult`, `OfflineEvalRunner`
    - *Methods*: `run_fixture(fixture_data)`, `run_file(file_path)`, `run_all(fixtures_dir=None)`

##### Folder: `trading-agent/evals/oracles`
**File:** `risk_compliance_oracle.py`
  - **Functions**: `evaluate_risk_compliance(proposal, market_context)`
**File:** `smc_geometry_oracle.py`
  - **Functions**: `evaluate_smc_geometry(proposal, ground_truth)`
**File:** `trade_discipline_oracle.py`
  - **Functions**: `evaluate_trade_discipline(proposal, ground_truth)`

##### Folder: `trading-agent/evals/fixtures`
  - *Description*: Golden market offline evaluation fixtures covering SMC displacement, liquidity sweeps, spread traps, and drawdown limit enforcement.
  - **Files**:
    - `risk_trap_daily_dd.json`
    - `risk_trap_spread_spike.json`
    - `smc_bear_sweep.json`
    - `smc_bull_displacement.json`
    - `smc_choppy_trap.json`

#### Folder: `trading-agent/execution`


**File:** `__init__.py`

**File:** `broker_adapter.py`
  - **Global Variables**: logger
  - **Functions**:
    - `_get_pip_size(symbol: str)`
    - `_get_contract_size(symbol: str)`
  - **Classes**:
    - `BrokerAdapter`
      - *Docstring*: Abstract Base Class interface for broker order routing and execution.
      - *Methods*:
        - `submit_order(self, order, **kwargs)`
        - `cancel_order(self, client_order_id)`
        - `get_orders(self, symbol=None)`
        - `close_position(self, ticket, lots)`
        - `close_all_positions(self, symbol=None)`
        - `get_positions(self)`
        - `get_open_positions(self, symbol)`
        - `get_account_info(self)`
        - `get_tick(self, symbol)`
        - `get_current_price(self, symbol)`
        - `ensure_connected(self)`
        - `is_connected(self)`
    - `MT5LiveAdapter`
      - *Docstring*: Live broker adapter wrapping MT5Client with dry-run support and cross-compatibility.
      - *Methods*:
        - `get_orders(self, symbol=None)`
        - `cancel_order(self, client_order_id)`
        - `close_all_positions(self, symbol=None)`
        - `is_connected(self)`
    - `SimulatedBrokerAdapter`
      - *Docstring*: Simulated broker adapter with dynamic spreads, ATR slippage, fill latency, pending order matching, and account balances.
      - *Methods*:
        - `reset(self, balance)`
        - `set_tick(self, symbol, bid, ask, last, timestamp)`
        - `check_pending_orders(self, symbol)`
        - `get_orders(self, symbol=None)`
        - `cancel_order(self, client_order_id)`
        - `close_all_positions(self, symbol=None)`
    - `MT5RemoteGatewayAdapter`
      - *Docstring*: Remote REST/RPC broker gateway adapter for decoupled MT5 executions on a remote Windows VPS.
      - *Methods*:
        - `get_orders(self, symbol=None)`
        - `submit_order(self, order, **kwargs)`
        - `cancel_order(self, client_order_id)`
        - `get_positions(self)`
        - `close_position(self, ticket, lots)`
        - `get_account_info(self)`

**File:** `effect_gate.py`
  - **Global Variables**: logger
  - **Classes**:
    - `AbortRequested`
      - *Docstring*: Dilempar ketika efek samping ditolak karena sistem telah meminta abort/kill-switch.
    - `EffectGateResult`
      - *Docstring*: Hasil pembungkusan eksekusi efek gate.
    - `EffectGate`
      - *Docstring*: Synchronous admission gate for mutating side-effects (order execution / broker submit) with re-entrancy and state verification.
      - *Methods*:
        - `is_aborted`
        - `abort_reason`
        - `request_abort(reason="Emergency abort requested")`
        - `reset()`
        - `admit(effect_fn, abort_signal=None, context_name="order_submission")`

**File:** `execution_service.py`
  - **Global Variables**: logger, _EXECUTION_LOCK, _EXECUTED_ANALYSIS_IDS, _LAST_CLEANUP_TIME
  - **Classes**:
    - `ExecutionResult`
      - *Docstring*: Comprehensive result of an execution attempt from sizing through broker dispatch.
      - *Methods*:
        - `summary(self)`
    - `ExecutionService`
      - *Docstring*: Orchestrates entire pipeline from LLM analysis to MT5 execution. Backward-compatible facade composing OrderExecutorMixin, RiskEvaluatorMixin, PositionSynchronizerMixin, EmergencyManagerMixin from `trading-agent/execution/service/`.
      - *Methods*:
        - `__init__(self)`
        - `_count_open_positions(self)`
        - `_transition_order_state(self, session, order, new_status, reason, details, executed_price, ticket, slippage_pips)`
          - *Docstring*: Record order state transition in DB (Order + OrderEvent audit trail) and broadcast OrderStateChangedEvent on EventBus.
        - `execute_analysis(self, session, analysis)`
          - *Docstring*: Execute an asset analysis with risk gate validation and limit order market drift protection.
        - `kill_switch(self)`
        - `execute_paired_analyses(self)`
          - *Docstring*: Execute dual-leg trades together with notional-weighted lots.
        - `execute_preplanned_order(self, session, symbol, order_plan, trigger_id, analysis_id, account_equity)`
          - *Docstring*: Execute a pre-planned conditional order with deterministic sizing and RiskGate validation in <100ms.
        - `execute_proposal(self, session, proposal, account_equity=None)`
          - *Docstring*: Financial Fortress entrypoint executing an immutable TradeProposal guarded by IdempotencyGuard and RiskGate.

**File:** `health_check.py`
  - **Docstring**: Flake-tolerant MT5 health checker with TTL caching and grace-period failure dampening.
  - **Classes**:
    - `FlakeTolerantHealthChecker`
      - *Docstring*: Health checker for MT5 connection with caching and transient failure dampening.
      - *Methods*:
        - `is_healthy(self, force_check=False)`
        - `record_success(self)`
        - `record_failure(self)`
        - `get_status(self)`

**File:** `idempotency_guard.py`
  - **Docstring**: In-memory and DB-backed idempotency sentinel preventing duplicate order placement and handling reconnect race conditions.
  - **Classes**: `IdempotencyState`, `IdempotencyRecord`, `IdempotencyGuard`
    - *Methods*: `generate_key()`, `acquire_lock()`, `mark_completed()`, `mark_failed()`, `release_lock()`, `reconcile_with_broker()`
  - **Functions**: `get_idempotency_guard()`

**File:** `mt5_client.py`
  - **Global Variables**: logger, PRIORITY_CRITICAL, PRIORITY_STANDARD, PRIORITY_BACKGROUND
  - **Functions**:
    - `_build_timeframe_map()`
      - *Docstring*: Constructs mapping of timeframe strings to MT5 constants lazily upon initial call.
    - `_connect()`
    - `_disconnect()`
    - `_is_connected()`
    - `_get_account_info()`
    - `_get_symbol_info()`
    - `_copy_rates_from_pos()`
    - `_copy_rates_range(symbol: str, timeframe: int, date_from, date_to)`
    - `_get_last_tick()`
    - `_place_order()`
      - *Docstring*: Execute a trade request on MT5.
    - `_modify_position()`
      - *Docstring*: Modify SL/TP on an existing open position.
    - `_close_position()`
      - *Docstring*: Close an open position (fully or partially).
    - `_get_open_positions()`
      - *Docstring*: Fetch all open positions from MT5.
    - `_get_orders()`
      - *Docstring*: Fetch active pending orders from MT5.
    - `_cancel_order()`
      - *Docstring*: Cancel an active pending order on MT5.
    - `_get_deal_history()`
    - `_get_order_history()`
    - `get_mt5_client(settings=None)`
      - *Docstring*: Singleton getter for MT5Client instance.
  - **Classes**:
    - `MT5Client`
      - *Docstring*: Async wrapper for MetaTrader 5 Python library with prioritized worker queue.
      - *Methods*:
        - `__init__(self)`
        - `_ensure_worker(self)`
        - `_priority_worker_loop(self)`
        - `_resolve_priority(self, fn, priority: Optional[int] = None)`
        - `_resolve_timeframe(self)`
        - `place_order(self, symbol: str, direction: str, volume: float, price: Optional[float] = None, sl: Optional[float] = None, tp: Optional[float] = None, comment: str = "AIAgent", order_type: str = "market", max_spread_multiplier: Optional[float] = None)`
        - `cancel_order(self, ticket_or_id: Union[int, str], priority: Optional[int] = None)`
        - `get_order_history(self, ticket: int)`
        - `get_deal_history(self, ticket: int)`
        - `modify_position(self, ticket: int, sl: Optional[float] = None, tp: Optional[float] = None)`
        - `modify_order(self, ticket: int, sl: Optional[float] = None, tp: Optional[float] = None)`
        - `close_position(self, ticket: int, volume: Optional[float] = None, comment: str = "AIAgent-Close")`
        - `close_all_positions(self, comment: str = "AIAgent-CloseAll")`
        - `emergency_close_all(self, comment: str = "AIAgent-EmergencyCloseAll")`
        - `kill_switch(self, comment: str = "AIAgent-KillSwitch")`
        - `get_open_positions(self, symbol: Optional[str] = None)`
        - `get_orders(self, symbol: Optional[str] = None, priority: Optional[int] = None)`
        - `get_account_info(self)`
        - `get_symbol_info(self, symbol: str)`
        - `get_spread(self, symbol: str)`
        - `get_latest_tick(self, symbol: str)`
        - `get_rates(self, symbol: str, timeframe: str = "H4", count: int = 100)`
        - `copy_rates_range(self, symbol: str, timeframe: str = "H4", date_from = None, date_to = None, priority: Optional[int] = None)`
        - `start_tick_poller(self, symbols=None, interval_seconds=None, event_bus=None, loop=None)`
        - `stop_tick_poller(self)`
        - `_tick_poller_worker(self, symbols, interval_seconds, event_bus, loop)`

**File:** `order_emulator.py`
  - **Docstring**: Event-Driven Client Order Emulator for sub-second trailing stops & breakeven management via TickPriceEvent.
  - **Classes**:
    - `TrackedPosition`
    - `ClientOrderEmulator`
      - *Methods*:
        - `subscribe(self, event_bus: EventBus)`
        - `unsubscribe(self, event_bus: EventBus)`
        - `register_position(self, ticket, symbol, direction, entry_price, current_sl, atr, current_tp=None, analysis_id=None, pair_group_id=None, metadata=None)`
        - `unregister_position(self, ticket)`
        - `get_tracked_position(self, ticket)`
        - `get_all_tracked(self)`
        - `sync_positions(self, active_positions, atr_lookup=None)`
        - `on_tick(self, event)`
        - `_evaluate_tick_for_position(self, pos, bid, ask, last)`
        - `_dispatch_sl_modification(self, ticket, new_sl, reason, analysis_id)`

**File:** `rate_throttler.py`
  - **Docstring**: Dual-Window Sliding Leaky-Bucket Order Rate Throttler (2/sec, 15/min) for broker protection.
  - **Classes**:
    - `ThrottleVerdict`
    - `RateThrottler`
      - *Methods*:
        - `check(self, now=None)`
        - `acquire(self, now=None)`
        - `wait_and_acquire(self, timeout=10.0)`
        - `reset(self)`

**File:** `verification_engine.py`
  - **Classes**:
    - `EvidenceFirstVerifier`

##### Folder: `trading-agent/execution/backends`

**File:** `__init__.py`

**File:** `base.py`
  - **Classes**:
    - `MT5Backend`
      - *Docstring*: Abstract interface for MT5 execution backends (Native, Wine, Remote Gateway).
      - *Methods*: `initialize()`, `shutdown()`, `account_info()`, `terminal_info()`, `positions_get()`, `orders_get()`, `history_deals_get()`, `order_send()`, `order_check()`, `symbol_info()`, `symbol_info_tick()`

##### Folder: `trading-agent/execution/service`

**File:** `__init__.py`

**File:** `base.py`
  - **Classes**:
    - `_ExecutionServiceMixinBase`
      - *Docstring*: Static typing base (type-checking only) for all ExecutionService mixins.

**File:** `emergency_manager.py`
  - **Classes**:
    - `EmergencyManagerMixin`
      - *Methods*:
        - `close_position_by_ticket(self, session, ticket, reason="manual_close")`
        - `_close_paper_position(self, session, position, reason)`
        - `kill_switch(self, reason="Manual kill switch activated") — emergency liquidation protected by asyncio.Lock
        - `trigger_circuit_breaker(self, reason="circuit_breaker", cooldown_seconds=3600)`

**File:** `audit_logger.py`
  - **Classes**:
    - `ExecutionAuditLogger`
      - *Methods*: `log_decision()`, `log_state_change()`, `log_fill()`

**File:** `order_creator.py`
  - **Classes**:
    - `OrderCreator`
      - *Methods*: `create_order()`, `save_position()`

**File:** `order_executor.py`
  - **Functions**:
    - `_prune_executed_analysis_ids(ttl_seconds: float = 86400.0) -> None`
  - **Classes**:
    - `ExecutionResult`
      - *Docstring*: Comprehensive result of an execution attempt from sizing through broker dispatch.
    - `OrderExecutorMixin`
      - *Methods*:
        - `execute_analysis(self, session, analysis)`
        - `execute_preplanned_order(self, session, symbol, order_plan, trigger_id, analysis_id, account_equity)`
        - `execute_paired_analyses(self, session, primary_analysis, secondary_analysis)`
        - `_execute_analysis_internal(self, session, analysis)`
        - `_save_position(self, session, analysis, order, executed_price, lots, sl, tp, ticket, is_paper)`
        - `_transition_order_state(self, session, order, new_status, reason, details, executed_price, ticket, slippage_pips)`

**File:** `reconciliation.py`
  - **Classes**:
    - `OrderReconciliation`
      - *Methods*: `reconcile_orders()`

**File:** `self_healing_executor.py`
  - **Docstring**: Autonomous self-healing execution harness for MetaTrader 5 orders intercepting broker rejections and performing zero-token deterministic micro-repairs.
  - **Classes**:
    - `MT5SelfHealingExecutor`
      - *Methods*: `heal_and_reexecute()`, `_heal_stops()`, `_snap_volume()`, `_reprice_requote()`

**File:** `sizing_calculator.py`
  - **Classes**:
    - `SizingCalculator`
      - *Methods*: `calculate()`

**File:** `state_machine.py`
  - **Classes**:
    - `OrderStateMachine`
      - *Methods*: `transition()`
  - **Global Variables**: `VALID_TRANSITIONS`

**File:** `trade_confirm.py`
  - **Docstring**: Human-in-the-Loop trade confirmation manager with pop-before-execute token consumption, drift verification, and double-fill prevention.
  - **Classes**: `TradeConfirmationToken`, `TradeConfirmManager`
    - *Methods*: `create_confirmation()`, `pop_for_execution()`, `cancel_confirmation()`, `clean_expired()`

**File:** `position_synchronizer.py`
  - **Classes**:
    - `PositionSynchronizerMixin`
      - *Methods*:
        - `sync_positions(self, session)`
        - `reconcile_inflight_orders(self)`
          - *Docstring*: Reconciles in-flight orders stuck in INTENT_COMMITTED or SUBMITTED state. Strict replay_policy='never' ensures no blind re-execution upon service restart.
        - `_handle_stop_loss_hit(self, session, position, deal)`
        - `modify_position_sl_tp(self, session, ticket, sl, tp, reason="strategy_update")`

**File:** `risk_evaluator.py`
  - **Classes**:
    - `RiskEvaluatorMixin`
      - *Methods*:
        - `_count_open_positions(self, session, symbol=None)`
        - `_get_dynamic_risk_percent(self, session, symbol, raw_confidence)`
        - `_get_current_price(self, symbol)`
        - `_get_equity(self)`

##### Folder: `trading-agent/execution/ea_bridge`

**File:** `AIAgent_EA.mq5`

**File:** `heartbeat_writer.py`
  - **Global Variables**: logger, _DEFAULT_MT5_COMMON, HEARTBEAT_FILENAME, LEGACY_HEARTBEAT_FILENAME, EA_HEARTBEAT_FILENAME, HEARTBEAT_INTERVAL_SECONDS, EA_STALE_THRESHOLD_SECONDS, HeartbeatWriter
  - **Functions**:
    - `_get_default_mt5_common()`
  - **Classes**:
    - `HeartbeatManager`
      - *Docstring*: Manages heartbeat file synchronization between Python engine and MT5 Expert Advisor.
      - *Methods*:
        - `__init__(self, mt5_common_path=None)`
        - `run_forever(self)`
        - `stop(self)`
        - `_write_heartbeat(self)`
        - `check_ea_alive(self)`
        - `get_watchdog(self, check_interval_seconds=15.0)`

**File:** `watchdog.py`
  - **Docstring**: Dual Heartbeat EA Watchdog monitoring MQL5 EA heartbeat and tripping safety circuits upon terminal freezes or disconnects.
  - **Classes**: `EAWatchdog`
    - *Methods*: `check_now()`, `run_forever()`, `stop()`

#### Folder: `trading-agent/graph`

**File:** `reactive_graph.py`
  - **Classes**:
    - `ReactiveState` - Dedicated state container for reactive event-driven execution graph
  - **Functions**:
    - `route_after_ingest(state)`
    - `route_after_confluence(state)`
    - `route_after_debate(state)`
    - `route_after_risk(state)`
    - `event_ingestion_node(state, config)`
    - `confluence_filter_node(state, config)`
    - `fast_debate_node(state, config)`
    - `reactive_risk_gate_node(state, config)`
    - `reactive_execution_node(state, config)`
    - `reactive_checkpoint_node(state, config)`
    - `build_reactive_graph(checkpointer=None)`
    - `get_reactive_graph(checkpointer=None)`


**File:** `state.py`
  - **Classes**:
    - `TradingState` - Primary state TypedDict; list fields use Annotated merge_lists reducer (including approved_trades and actionable_trades), along with ssvp_per_symbol_contexts.
  - **Functions**:
    - `merge_dicts()` - Deep recursive merge for nested dictionaries; used as Annotated reducer
    - `merge_lists()` - Concatenation of two lists; used as Annotated reducer for list fields

**File:** `workflow.py`
  - **Functions**:
    - `build_trading_graph()`

##### Folder: `trading-agent/graph/checkpointers`
**File:** `__init__.py`
**File:** `dual_checkpointer.py`
  - **Classes**: `DualCheckpointSaver(BaseCheckpointSaver)`
    - *Docstring*: Dual-write LangGraph checkpointer orchestrating Primary (PostgreSQL) and Secondary (SQLite). Deprecated in favor of authoritative PostgreSQL checkpointer; retained for test compatibility.
    - *Properties*: `conn` (proxies primary connection pool), `_needs_setup`
    - *Methods*: `__init__()`, `a_setup()`, `get_tuple()`, `aget_tuple()`, `list()`, `alist()`, `put()`, `aput()`, `put_writes()`, `aput_writes()`
**File:** `sqlite_checkpointer.py`
  - **Classes**: `SqliteCheckpointSaver(InMemorySaver)`
    - *Docstring*: Local SQLite checkpointer providing crash-safe state persistence across restarts. Deprecated; retained for backward compatibility.
    - *Methods*: `__init__()`, `_init_db()`, `_load_from_sqlite()`, `put()`, `aput()`, `_persist_checkpoint_sync()`, `put_writes()`, `aput_writes()`, `_persist_writes_sync()`

##### Folder: `trading-agent/graph/nodes`

**File:** `data_node.py`
  - **Functions**:
    - `fetch_data_node()`

**File:** `debate_node.py`
  - **Docstring**: Backward-compatible facade delegating to `build_debate_subgraph()` in `graph/nodes/debate/subgraph.py`.
  - **Global Variables**: logger
  - **Functions**:
    - `debate_node()`

###### Folder: `trading-agent/graph/nodes/debate`

**File:** `__init__.py`

**File:** `bear_dissent_node.py`
  - **Functions**:
    - `bear_dissent_node(state: TradingState) -> Dict[str, Any]`

**File:** `bull_advocate_node.py`
  - **Global Variables**: `_SEMAPHORE`
  - **Functions**:
    - `bull_advocate_node(state: TradingState) -> Dict[str, Any]`

**File:** `debate_judge_node.py`
  - **Functions**:
    - `debate_judge_node(state: TradingState) -> Dict[str, Any]`

**File:** `helpers.py`
  - **Functions**:
    - `_get_recent_sl_streak(session, symbol: str) -> int`
    - `_get_correlated_exposure_summary(session, symbol: str) -> List[str]`
    - `_is_grounded(claim_dict: dict, current_price: float) -> bool`
    - `_apply_deterministic_risk_clamp(pm_decision: dict, risk_stances: dict, actual_risk_state: dict | None) -> dict`
    - `compute_actual_risk_state(session, settings: dict, mt5_client=None) -> Dict[str, Any]`
    - `inject_coherence_and_intel(session, sym: str, bull_thesis: str, user_market_intel: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]`
    - `sync_facade_patches()`

**File:** `rebuttal_node.py`
  - **Functions**:
    - `rebuttal_node(state: TradingState) -> Dict[str, Any]`

**File:** `risk_evaluator_node.py`
  - **Functions**:
    - `risk_evaluator_node(state: TradingState) -> Dict[str, Any]`

**File:** `round_robin_risk_nodes.py`
  - **Functions**:
    - `conservative_risk_node(state: TradingState) -> Dict[str, Any]`
    - `aggressive_risk_node(state: TradingState) -> Dict[str, Any]`
    - `neutral_risk_node(state: TradingState) -> Dict[str, Any]`
    - `portfolio_judge_node(state: TradingState) -> Dict[str, Any]`

**File:** `subgraph.py`
  - **Functions**:
    - `should_continue_debate(state: TradingState) -> str`
    - `build_debate_subgraph(checkpointer=None)`

**File:** `execution_node.py`
  - **Functions**:
    - `execution_node()`

**File:** `fundamental_node.py`
  - **Functions**:
    - `fundamental_analysis_node()`

**File:** `per_asset_node.py`
  - **Functions**:
    - `per_asset_analysis_node()`

**File:** `reflection_node.py`
  - **Global Variables**: logger
  - **Functions**:
    - `reflection_node()` - Cross-asset reflection prior to execution; enforces defensive VIX fallback (VIX=25.0 on query failure) preventing filter bypass when DB is unavailable

**File:** `plan_refinement_node.py`
  - **Global Variables**: logger
  - **Functions**:
    - `plan_refinement_node()` - Evaluates negotiable trade rejections (tight SL, portfolio heat, staleness drift) and refines trade proposal parameters up to 2 iterations

**File:** `risk_gate_node.py`
  - **Global Variables**: `PORTFOLIO_SYNTHESIS_SCHEMA`
  - **Functions**:
    - `_ai_portfolio_synthesis()`
    - `risk_gate_node()`

**File:** `state_pruner.py`
  - **Functions**:
    - `prune_after_fundamental(state: TradingState) -> Dict[str, Any]`
    - `prune_after_debate(state: TradingState) -> Dict[str, Any]`
    - `prune_before_execution(state: TradingState) -> Dict[str, Any]`

#### Folder: `trading-agent/indicators`

**File:** `__init__.py`

**File:** `order_flow.py`
  - **Global Variables**: logger
  - **Functions**:
    - `fetch_latest_order_flow(session, symbol: str) -> OrderFlowSnapshot`
  - **Classes**:
    - `OrderFlowSnapshot`
      - *Docstring*: Snapshot of order flow and liquidity metrics for a symbol (OBI, CVD, absorption divergence, DOM depth).
    - `OrderFlowEngine`
      - *Docstring*: Dual-mode Order Flow & Liquidity Engine. Real DOM Level-2 order book tracking with automatic fallback to Lee-Ready synthetic tick rule CVD.
      - *Methods*:
        - `__init__(self, mt5_client=None, settings=None)`
        - `analyze_order_flow(self, session, symbol: str, lookback: int = 200, df=None) -> OrderFlowSnapshot`
        - `_check_and_subscribe_dom(self, symbol: str) -> bool`
        - `_compute_dom_l2_snapshot(self, symbol: str) -> OrderFlowSnapshot`
        - `_compute_tick_rule_cvd_snapshot(self, session, symbol: str, lookback: int = 200, df=None) -> OrderFlowSnapshot`

**File:** `structure.py`
  - **Global Variables**: logger, `FVG_MAX_DISTANCE`
  - **Classes**:
    - `MarketStructureAnalyzer`
      - *Docstring*: Detects and extracts market structure elements (BOS, CHoCH, Order Blocks, FVGs) from OHLCV.
      - *Methods*:
        - `__init__(self)`
        - `_prune_old_data(self)`
        - `_find_swings(self)`
        - `_find_sr_zones(self)`
        - `_find_liquidity_zones(self)`
        - `_find_fvg(self)`
        - `_check_fvg_filled(self)`
        - `_find_order_blocks(self)`
        - `_detect_structure_breaks(self)`
        - `get_structure_snapshot(self)`

**File:** `microstructure.py`
  - **Global Variables**: `VPIN_SYMBOLS`, `KYLE_SYMBOLS`, `AMIHUD_SYMBOLS`
  - **Functions**: `compute_vpin()`, `compute_amihud_illiquidity()`, `compute_kyle_lambda()`, `get_microstructure_metrics()`

**File:** `regime_detector.py`
  - **Classes**: `RegimeState`, `SchmittRegimeDetector`
    - *Methods*: `compute_edge_density()`, `update()`
  - **Functions**: `get_schmitt_regime_detector()`

**File:** `technical.py`
  - **Global Variables**: logger
  - **Functions**: `compute_yang_zhang_volatility()`, `compute_lag1_autocorrelation()`
  - **Classes**:
    - `TechnicalIndicatorCalculator`
      - *Docstring*: Computes and stores multi-timeframe technical indicators from OHLCV series.
      - *Methods*:
        - `__init__(self)`
        - `_compute_all(self, df, is_final)`
        - `get_snapshot(self)`
        - `get_latest(self)`

**File:** `timesfm_engine.py`
  - **Global Variables**: logger
  - **Classes**:
    - `TimesFMEngine`
      - *Docstring*: Google TimesFM computational engine for zero-shot probabilistic quantile price forecasting.
      - *Methods*:
        - `__init__(self, settings)`
        - `_init_model(self)`
        - `_fetch_multivariate_series(self, session, symbol, timeframe, limit)`
        - `compute_forecast(self, session, symbol, timeframe, horizon_steps)`
        - `_compute_metrics_from_quantiles(self, target_series, q_matrix, horizon_steps)`
        - `save_forecast(self, session, forecast_data)`
        - `get_latest_forecast(self, session, symbol, timeframe, max_age_hours, as_of)`
        - `generate_and_store_universe_forecasts(self, session, symbols, timeframe, horizon_steps)`

#### Folder: `trading-agent/logging_observability`

**File:** `__init__.py`

**File:** `activity_logger.py`
  - **Global Variables**: CATEGORIES, LOG_FORMAT_FILE, LOG_FORMAT_CONSOLE, DATE_FORMAT
  - **Functions**:
    - `setup_logging()`
      - *Docstring*: Setup root logger (File Rotating & Console).
    - `shutdown_logging()`
      - *Docstring*: Stop background QueueListener worker thread cleanly.
    - `get_activity_logger()`
      - *Docstring*: Mendapatkan singleton instance `ActivityLogger`.
  - **Classes**:
    - `ActivityLogger`
      - *Docstring*: Penulis log asinkron ke DB `activity_log`.
      - *Methods*: `__init__()`, `log()`, `trading()`, `analysis()`, `risk()`, `system()`, `scraping()`, `telegram()`, `log_fallback_event()`, `bulk()`

**File:** `metrics_exporter.py`
  - **Global Variables**: metrics
  - **Classes**:
    - `MetricsCollector`
      - *Docstring*: Thread-safe in-memory metric collector producing Prometheus/OpenMetrics formatted output.
      - *Methods*:
        - `__new__(cls)`
        - `inc_counter(self, name, value, labels)`
        - `set_gauge(self, name, value, labels)`
        - `record_histogram(self, name, value)`
        - `generate_prometheus_metrics(self)`

**File:** `report_writer.py`
  - **Classes**:
    - `ReportWriter`
      - *Docstring*: Writes per-cycle markdown reports.
      - *Methods*:
        - `__init__(self)`
        - `write_cycle_report(self, cycle_id: str, state: dict)`
        - `write_cycle_report_async(self, cycle_id: str, state: dict) -> None`

**File:** `token_budgeter.py`
  - **Docstring**: Unified token quota and budget manager allocating subsystem quotas and triggering adaptive degradation tiers.
  - **Classes**:
    - `DegradationTier`
    - `TokenBudgetManager`
      - *Methods*:
        - `record_usage(subsystem, tokens, cost)`
        - `get_current_tier()`
        - `is_subsystem_throttled(subsystem)`
        - `get_budget_status()`
  - **Functions**: `get_token_budget_manager(settings=None)`

**File:** `operator_feedback.py`
  - **Docstring**: Operator Feedback Capture allowing human reviewers to rate, categorize, and annotate trade rationales linked into cycle event streams.
  - **Classes**:
    - `AnalysisFeedback`
    - `OperatorFeedbackManager`
      - *Methods*: `submit_feedback()`, `get_feedback_for_cycle()`
  - **Functions**: `get_operator_feedback_manager()`

**File:** `trading_cycle_event_log.py`
  - **Docstring**: Monotonic Event-Sourced Trading Cycle Log and Decision Lineage Tracing with contiguous sequence numbers per cycle and cryptographic SHA-256 hash chaining.
  - **Classes**:
    - `CycleEventType`
    - `CycleEvent`
      - *Methods*: `to_dict()`, `calculate_hash()`
    - `TradingCycleEventLog`
      - *Methods*: `record_event()`, `get_events_for_cycle()`, `trace_decision_lineage()`, `reconstruct_cycle()`, `verify_cycle_integrity()`
  - **Functions**: `get_cycle_event_log()`, `compute_event_hash()`

##### Folder: `trading-agent/logging_observability/reporting`

**File:** `__init__.py`

**File:** `tearsheet_generator.py`
  - **Classes**:
    - `TearsheetResult`
      - *Docstring*: Dataclass encapsulating comprehensive quant tearsheet analytics.
      - *Methods*: `to_dict()`, `to_markdown()`, `to_telegram_html()`
    - `QuantTearsheetGenerator`
      - *Docstring*: Quantitative performance reporting engine calculating institutional tearsheets.
      - *Methods*: `generate_from_trades(trades, initial_equity=10000.0, start_date=None, end_date=None)`

##### Folder: `trading-agent/logging_observability/tracing`
**File:** `__init__.py`
**File:** `context.py`
  - **Functions**: `get_current_trace_id()`, `get_current_span_id()`, `set_trace_context()`, `clear_trace_context()`
**File:** `exporters.py`
  - **Classes**: `SpanExporter`, `InMemorySpanExporter`, `InMemoryTraceStore`, `ConsoleSpanExporter`, `JsonFileSpanExporter`
    - *Methods*: `InMemoryTraceStore.search_spans()`
**File:** `otlp_exporter.py`
  - **Classes**: `OTLPSpanExporter`
  - **Variables**: `global_otlp_exporter`
**File:** `spans.py`
  - **Functions**: `cycle_span()`, `node_span()`, `llm_span()`, `tool_span()`
**File:** `tracer.py`
  - **Classes**: `Tracer`, `TracerProvider`
  - **Functions**: `get_tracer()`, `trace_span()`

##### Folder: `trading-agent/logging_observability/dashboard`

**File:** `__init__.py`

**File:** `api.py`
  - **Global Variables**: logger, app, _FRONTEND_DIST, _dependencies
  - **Classes**:
    - `TriggerCycleRequest`
    - `OverrideRiskRequest`
    - `ClosePositionRequest`
  - **Functions**:
    - `_mount_frontend()`
      - *Docstring*: Mount statis React build jika ada (fallback index.html).
    - `_safe_json()`
      - *Docstring*: Safely parses JSON text, returning original string on syntax failure.
    - `set_dashboard_dependencies(**kwargs)`
      - *Docstring*: Register runtime agent dependencies for interactive dashboard endpoints.
    - `get_dashboard_dependency(name)`
      - *Docstring*: Retrieve runtime agent dependency by name.
    - `action_trigger_cycle(body)`
      - *Docstring*: Trigger LangGraph analysis cycle immediately via POST /api/actions/trigger-cycle.
    - `action_override_risk(payload)`
      - *Docstring*: Update dynamic risk parameters in SystemConfig and runtime via POST /api/actions/override-risk.
    - `action_close_position(payload)`
      - *Docstring*: Close floating position in MT5/broker or paper trade via POST /api/actions/close-position.
    - `action_approve_trade(trade_id)`
      - *Docstring*: Approve pending trade trigger or asset analysis via POST/PUT /api/actions/approve-trade/{id}.
    - `run_dashboard()`
      - *Docstring*: Starts FastAPI dashboard server from main process in synchronous entrypoint.
    - `get_debate_outcomes()`
      - *Docstring*: Ambil ringkasan hasil debate bull/bear & adjudikasi spesialis.
    - `get_mt5_signals()`
      - *Docstring*: Retrieves signal history and corresponding broker execution telemetry.
    - `get_trade_triggers()`
      - *Docstring*: Ambil daftar trade triggers kondisional.
    - `websocket_live_feed(websocket)`
      - *Docstring*: Real-time WebSocket streaming endpoint for live price ticks, open positions, and activity logs.
    - `broadcast_live_event(event_type, payload)`
      - *Docstring*: Broadcasts events across all active dashboard WebSocket client connections.
    - `get_traces(cycle_id, trace_id, kind, limit)`
      - *Docstring*: Retrieve distributed trace spans from the in-memory trace store via GET /api/traces.
    - `get_trace_tree(trace_id)`
      - *Docstring*: Retrieve hierarchical trace tree for a specific trace_id via GET /api/traces/{trace_id}.
    - `get_cycle_trace_summary(cycle_id)`
      - *Docstring*: Retrieve aggregate telemetry and trace spans for a cycle via GET /api/traces/cycle/{cycle_id}.
    - `get_playbook_tree()`
      - *Docstring*: Graph visualization of micro-playbook derivations via GET /api/observability/playbook-tree.
    - `get_prompt_cache_metrics(limit)`
      - *Docstring*: Grafik metrik prompt cache hit rate vs miss rate per siklus via GET /api/observability/prompt-cache-metrics.
    - `get_tool_latencies()`
      - *Docstring*: Histogram dan distribusi latensi eksekusi tool handler via GET /api/observability/tool-latencies.
    - `get_config_settings()`
      - *Docstring*: Read settings.yaml config dictionary via GET /api/config/settings.
    - `get_config_schema()`
      - *Docstring*: JSON schema for TradingAgentConfig validation via GET /api/config/schema.
    - `update_config_settings(payload)`
      - *Docstring*: Validate, backup, and update settings.yaml with hot-reload via PUT /api/config/settings.
    - `list_sessions(source, limit)`
      - *Docstring*: List Telegram and Dashboard conversation sessions via GET /api/sessions.
    - `get_session_messages(session_id, limit)`
      - *Docstring*: Retrieve conversation transcript for a session via GET /api/sessions/{session_id}/messages.
    - `get_auth_role(request)`
      - *Docstring*: Return caller's resolved RBAC role via GET /api/auth/role.
    - `websocket_agent_chat(websocket, token)`
      - *Docstring*: WebSocket interactive agent chat with live streaming and 3-tier HITL approval actions.
    - `_build_graph_state_for_cycle(cycle_id)`
      - *Docstring*: Constructs LangGraph DAG topology state with node statuses, execution durations, tokens, and payloads.
    - `get_graph_state(cycle_id)`
      - *Docstring*: Retrieve topology, execution status, latencies, tokens, and payloads for the LangGraph multi-agent pipeline visualizer via GET /api/observability/graph-state.

**File:** `rbac.py`
  - **Classes**:
    - `Role(str, Enum)`: User role hierarchy (viewer, operator, admin).
  - **Functions**:
    - `resolve_role(api_key, is_localhost)`: Parse multi-role DASHBOARD_API_KEYS or legacy DASHBOARD_API_KEY.
    - `require_role(minimum_role)`: Decorator protecting endpoints requiring specific role clearance.

###### Folder: `trading-agent/logging_observability/dashboard/routes`
**File:** `__init__.py`
  - Re-exports all route routers in priority match order: `system_router`, `tokens_router`, `config_router`, `trading_router`, `trace_search_router`, `observability_router`, `websocket_router`, `backtest_router`, `intelligence_router`.
**File:** `backtest.py`
  - **Variables**: `backtest_router`
  - **Classes**: `BacktestRunRequest`
  - **Functions**: `list_backtest_runs()`, `get_backtest_run_details()`, `trigger_backtest_run()`, `_execute_background_backtest()`
**File:** `trace_search.py`
  - **Variables**: `trace_search_router`
  - **Functions**: `search_traces()`, `slow_llm_calls()`
**File:** `common.py`
  - **Classes**: `TriggerCycleRequest`, `OverrideRiskRequest`, `ClosePositionRequest`
  - **Functions**: `set_dashboard_dependencies()`, `get_dashboard_dependency()`, `broadcast_live_event()`, `_safe_json()`, `_resolve_settings_path()`
**File:** `config.py`
  - **Functions**: `get_config_settings()`, `get_config_schema()`, `update_config_settings()`
**File:** `memory.py`
  - **Docstring**: Memory Browsing Endpoints (Reflections, Lessons, Playbooks, Search).
  - **Variables**: `memory_router`
  - **Classes**: `MemorySearchRequest`
  - **Functions**: `get_reflections()`, `get_lessons()`, `get_playbooks()`, `search_memory()`
**File:** `observability.py`
  - **Functions**: `get_traces()`, `get_trace_tree()`, `get_cycle_trace_summary()`, `get_playbook_tree()`, `get_prompt_cache_metrics()`, `get_tool_latencies()`, `get_graph_state()`
**File:** `system.py`
  - **Functions**: `get_system_health()`, `get_system_metrics()`, `ping()`, `get_diagnostics()`, `get_daily_brief()`, `get_vix_data()`, `get_gemini_quota()`, `get_auth_role()`
**File:** `tokens.py`
  - **Functions**: `get_token_summary()`, `get_context_tracker_metrics()`, `get_tokens_by_role()`, `get_tokens_by_subsystem()`, `get_tokens_by_symbol()`, `get_recent_token_logs()`, `get_tokens_by_cycle()`, `get_per_turn_cost_metrics()`
**File:** `trading.py`
  - **Functions**: `get_overview()`, `get_paper_trading_summary()`, `get_open_positions()`, `get_recent_activity()`, `get_recent_analysis()`, `get_factor_analysis()`, `get_recent_orders()`, `get_current_risk()`, `get_edge_metrics()`, `get_decision_distribution()`, `get_analysis_quality()`, `get_ssvp_health()`, `get_debate_outcomes()`, `get_mt5_signals()`, `get_trade_triggers()`, `action_trigger_cycle()`, `action_override_risk()`, `action_close_position()`, `action_emergency_kill()`, `action_approve_trade()`
**File:** `websocket.py`
  - **Classes**: `TokenCoalescingBuffer`
    - *Methods*: `push()`, `flush()`, `stream_text()`
  - **Functions**: `websocket_live_feed()`, `websocket_agent_chat()`, `list_sessions()`, `get_session_messages()`

###### Folder: `trading-agent/logging_observability/dashboard/frontend`

**File:** `README.md`
**File:** `package.json`
**File:** `tsconfig.app.json`
**File:** `tsconfig.node.json`
**File:** `vite.config.ts`

####### Folder: `trading-agent/logging_observability/dashboard/frontend/src`
**File:** `App.css`
**File:** `App.tsx`
**File:** `index.css`
**File:** `main.tsx`
**File:** `vite-env.d.ts`

######## Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/charts`
**File:** `DecisionDistribution.tsx`
**File:** `EquityChart.tsx`
**File:** `FactorHeatmap.tsx`
**File:** `VixSparkline.tsx`
**File:** `WinRateGauge.tsx`

######## Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/layout`
**File:** `BreadcrumbBar.tsx`
**File:** `GlobalStatusBar.tsx`
**File:** `Header.tsx`
**File:** `MobileNavDrawer.tsx`
**File:** `navigation.ts`
**File:** `Sidebar.tsx`

######## Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/panels`
**File:** `ActivityFeed.tsx`
**File:** `AgentChatPanel.tsx`
**File:** `AgentStatusBar.tsx`
**File:** `AnalysisGrid.tsx`
**File:** `BacktestPanel.tsx`
**File:** `ConfigEditorPanel.tsx`
**File:** `DebateOutcomesPanel.tsx`
**File:** `EdgeMetricsPanel.tsx`
**File:** `GraphVisualizerPanel.tsx`
**File:** `MarketDataPanel.tsx`
**File:** `MemoryBrowserPanel.tsx`
**File:** `ObservabilityPanel.tsx`
**File:** `PerformancePanel.tsx`
**File:** `PositionsTable.tsx`
**File:** `RetroCockpitBar.tsx`
**File:** `RiskPanel.tsx`
**File:** `SessionBrowserPanel.tsx`
**File:** `SignalsTriggersPanel.tsx`
**File:** `SystemPanel.tsx`
**File:** `TokenAuditPanel.tsx`

######### Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/panels/config`
**File:** `ConfigDiffModal.tsx`
**File:** `ConfigSection.tsx`

######### Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/panels/graph`
**File:** `GraphControls.tsx`
**File:** `GraphEdge.tsx`
**File:** `GraphInspector.tsx`
**File:** `GraphNode.tsx`
**File:** `graphUtils.ts`

######### Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/panels/tokens`
**File:** `TokenCharts.tsx`
**File:** `TokenRoleTable.tsx`

######## Folder: `trading-agent/logging_observability/dashboard/frontend/src/components/ui`
**File:** `AnalogDial.tsx`
**File:** `ApprovalModal.tsx`
**File:** `Badge.tsx`
**File:** `BootSequence.tsx`
**File:** `Card.tsx`
**File:** `ConfirmModal.tsx`
**File:** `EmptyState.tsx`
**File:** `ErrorBoundary.tsx`
  - **Classes**:
    - `ErrorBoundary`
      - *Methods*: `getDerivedStateFromError()`, `componentDidCatch()`, `handleReset()`, `render()`
**File:** `KeyboardShortcutsPanel.tsx`
**File:** `LedgerTable.tsx`
**File:** `MetricCard.tsx`
**File:** `MonikaInfiniteIcon.tsx`
**File:** `RetroIcons.tsx`
**File:** `RetroVuMeter.tsx`
**File:** `SegmentedProgressBar.tsx`
**File:** `Skeleton.tsx`
**File:** `StatusIndicator.tsx`
**File:** `ThemeToggle.tsx`
**File:** `TickerTape.tsx`
**File:** `TypewriterButton.tsx`
**File:** `VintageIcons.tsx`
**File:** `WeekendGapBanner.tsx`
**File:** `WindowFrame.tsx`

######## Folder: `trading-agent/logging_observability/dashboard/frontend/src/hooks`
**File:** `useAgentChatWs.ts`
**File:** `usePolling.ts`
**File:** `useWebSocket.ts`


######## Folder: `trading-agent/logging_observability/dashboard/frontend/src/lib`
**File:** `api.ts`
**File:** `formatters.ts`
**File:** `soundEffects.ts`

######## Folder: `trading-agent/logging_observability/dashboard/frontend/src/store`
**File:** `dashboardStore.ts`

######## Folder: `trading-agent/logging_observability/dashboard/frontend/src/types`
**File:** `api.ts`

#### Folder: `trading-agent/plugins`

**File:** `__init__.py`

**File:** `manifest.py`
  - **Docstring**: Plugin Manifest Definition & Schema Validation. Defines metadata, dependencies, custom tools, and 12 lifecycle hook endpoints.
  - **Classes**: `PluginManifest`
  - **Global Variables**: `SUPPORTED_HOOKS`

**File:** `loader.py`
  - **Docstring**: Plugin Dependency Resolver and Topological Loader. Orders plugins by dependency graph before initialization, preventing missing dependency failures and detecting circular dependency cycles at startup.
  - **Classes**: `PluginDependencyError`, `MissingDependencyError`, `CircularDependencyError`, `PluginLoader`
    - *Methods*: `discover_plugins()`, `load_plugins_from_directory()`, `unload_plugin()`
  - **Functions**: `load_manifest_file()`, `topological_sort_plugins()`

##### Folder: `trading-agent/plugins/alerts/discord_alert`
**File:** `plugin.yaml`
**File:** `discord_alert.py`
  - **Functions**: `initialize(manager, config)`

##### Folder: `trading-agent/plugins/indicators/custom_indicator`
**File:** `plugin.yaml`
**File:** `custom_indicator.py`
  - **Functions**: `initialize(manager, config)`

##### Folder: `trading-agent/plugins/scrapers/example_scraper`
**File:** `plugin.yaml`
**File:** `example_scraper.py`
  - **Functions**: `initialize(manager, config)`

#### Folder: `trading-agent/provider`

**File:** `__init__.py`

**File:** `credential_pool.py`
  - **Docstring**: Monika Unified Credential Pool & Multi-Key Health Tracker.
  - **Classes**: `KeyHealth` (alias `CredentialState`), `CredentialPool` (alias `APICredentialPool`), `LLMCredentialPool`
    - *Methods*: `add_key()`, `get_key()`, `get_active_key()`, `report_success()`, `report_rate_limit()`, `report_failure()`, `is_model_available()`, `all_exhausted()`, `get_cumulative_cost()`, `get_pool_status()`
  - **Functions**: `get_credential_pool()`

**File:** `error_taxonomy.py`
  - **Docstring**: Monika Unified Error Taxonomy & Recovery Strategy Assignment.
  - **Classes**: `FailoverReason`, `ErrorCategory`, `RecoveryAction`, `ClassifiedError`, `ErrorClassifier`
  - **Functions**: `sanitize_unicode_surrogates()`, `fallback_multimodal_to_text()`

#### Folder: `trading-agent/risk`

**File:** `__init__.py`

**File:** `approval_hub.py`
  - **Docstring**: Unified multi-surface Human-In-The-Loop approval bus with synchronized state and steering.
  - **Classes**: `ApprovalRequest`, `ApprovalHub`
    - *Methods*: `get_instance()`, `submit_approval_request()`, `resolve_request()`, `steer()`, `register_surface_listener()`, `get_open_requests()`

**File:** `correlation_matrix.py`
  - **Docstring**: Dynamic Correlation Matrix and Portfolio Covariance Engine calculating rolling returns correlation and covariance matrices to evaluate portfolio heat.
  - **Classes**: `DynamicCorrelationMatrix`
    - *Methods*: `calculate_pearson_correlation()`, `get_matrix()`, `calculate_portfolio_heat()`

**File:** `execution_simulator.py`
  - **Global Variables**: logger
  - **Classes**:
    - `SlippageScenario`
      - *Docstring*: Data container for simulated slippage scenario (baseline, elevated, stress).
    - `ExecutionSimulationResult`
      - *Docstring*: Evaluation result of tick-level slippage simulation.
    - `ExecutionSimulator`
      - *Docstring*: Pre-execution sandbox for simulating tick slippage resilience.
      - *Methods*:
        - `__init__(self, settings=None, mt5_client=None)`
        - `fetch_recent_ticks(self, symbol, count=100, session=None)`
        - `simulate_execution(self, symbol, direction, entry_price, stop_loss, take_profit, volume=0.1, ticks=None, session=None)`

**File:** `position_sizing.py`
  - **Global Variables**: logger
  - **Functions**:
    - `get_instrument_spec(symbol: str, mt5_client=None) -> InstrumentSpec`
      - *Docstring*: Retrieves dynamic instrument specifications and pip precision across asset classes (Forex, Metals, Crypto, Indices).
    - `calculate_lot_size(symbol, entry_price, stop_loss, risk_pct=1.0, direction=None, session=None, settings=None, mt5_client=None, account_equity=None, **kwargs)`
      - *Docstring*: Public helper function for deterministic position sizing with automated MT5 live equity resolution.
  - **Classes**:
    - `InstrumentSpec`
      - *Docstring*: Spesifikasi instrumen trading.
      - *Methods*:
        - `pip_value_per_lot(self)`
    - `SizingResult`
      - *Docstring*: Hasil perhitungan ukuran posisi (lot).
      - *Methods*:
        - `summary(self)`
        - `sl_pips(self)`
    - `PositionSizer`
      - *Docstring*: Menghitung rekomendasi ukuran lot berdasarkan parameter risiko dan equity.
      - *Methods*:
        - `__init__(self)`
        - `calculate(self)`
        - `calculate_with_session(self)`
        - `_get_instrument_spec(self)`
        - `_get_instrument_spec_dynamic(self)`
        - `pip_value_per_lot(self)`
        - `_round_lots(self)`
        - `_invalid(self)`

**File:** `portfolio_correlation_gate.py`
  - **Global Variables**: logger
  - **Functions**:
    - `get_correlation(sym1, sym2)`
      - *Docstring*: Returns static correlation from CORRELATION_PAIRS.
    - `filter_correlated_proposals(actionable_trades, threshold)`
      - *Docstring*: Given a list of tuples (symbol, result_dict), filter out trades that are highly correlated with each other to avoid overexposure. Keeps the trade with the higher confidence.

**File:** `risk_gate.py`
  - **Global Variables**: logger
  - **Functions**:
    - `get_trading_day_start(settings, now=None)`
      - *Docstring*: Menghitung waktu mulai hari perdagangan berdasarkan broker daily rollover (default 21:00 UTC / 17:00 NY).
    - `get_daily_risk_cutoff(now, risk_cfg)`
      - *Docstring*: Helper alias for get_trading_day_start accepting (now, risk_cfg).
    - `get_current_risk_state(session=None, settings=None)`
      - *Docstring*: Retrieves snapshot of current portfolio risk and cumulative drawdown metrics.
  - **Classes**:
    - `RiskVerdict`
      - *Docstring*: Outcome and validation details produced by Risk Gate.
      - *Methods*:
        - `summary(self)`
    - `RiskGate`
      - *Docstring*: Validates prospective orders against portfolio risk constraints and trading rules.
      - *Methods*:
        - `__init__(self)`
        - `update_parameters(self, new_risk_cfg)`
        - `evaluate(self, session, symbol, direction, sizing, account_equity, analysis, as_of, simulated_positions, simulated_equity, simulated_daily_pnl, is_backtest, pair_group_id, is_paper)`
        - `evaluate_proposal(self, session, proposal, account_equity=None, as_of=None, is_backtest=False, is_paper=None)` (alias: `check_proposal`)
        - `check_correlation_exposure(self, session, symbol, direction, simulated_positions, as_of, open_positions)`
        - `assess_weekend_gap_risk(self, session, symbol: str)` (alias: `_check_weekend_gap_risk`)

**File:** `trade_proposal.py`
  - **Docstring**: Immutable contract schema and FortressAdmissionValidator gatekeeper defining the boundary between Plane 1 (Analysis Playground) and Plane 2 (Financial Fortress).
  - **Classes**: `TradeProposal`, `FortressAdmissionValidator`
    - *Methods*: `validate_proposal()`, `from_analysis()`, `compute_reasoning_hash()`

##### Folder: `trading-agent/risk/invariants`
**File:** `__init__.py`
**File:** `position_count_invariant.py`
  - **Docstring**: Position Count Invariant. Asserts that open position count does not breach maximum account limits.
  - **Functions**: `assert_position_count_invariant(open_positions, max_concurrent_positions)`, `check_position_count_invariant(context)`
**File:** `registry.py`
  - **Docstring**: Runtime Invariant Registry Framework coordinating non-negotiable safety rules and invariant failure attribution.
  - **Classes**: `InvariantStatus`, `InvariantResult`, `InvariantRegistry`
    - *Methods*: `get_instance()`, `reset_instance()`, `register()`, `unregister()`, `list_invariants()`, `run_all()`, `assert_all()`
  - **Functions**: `get_global_invariant_registry()`, `reset_global_invariant_registry()`
**File:** `risk_gate_invariant.py`
  - **Docstring**: Risk Gate Runtime Invariant Listener. Enforces hard mathematical ceilings and non-negotiable risk constraints.
  - **Classes**: `InvariantViolationError`, `RiskGateInvariant`
  - **Functions**: `assert_risk_gate_invariants(proposal, current_drawdown_pct, max_drawdown_limit, min_rr_ratio)`, `check_risk_gate_invariants(context)`
**File:** `state_immutability_invariant.py`
  - **Docstring**: State Immutability Invariant Listener. Verifies that graph state and context snapshots cannot be corrupted by in-place mutations.
  - **Classes**: `StateFreezeGuard`
  - **Functions**: `compute_state_digest(state, protected_keys)`, `assert_state_immutability(initial_state, current_state, protected_keys)`

#### Folder: `trading-agent/security`

**File:** `__init__.py`

**File:** `credential_vault.py`
  - **Docstring**: Secure Credential Vault & Sensitive Output Masking for Monika Trading Agent. Integrates with Windows Credential Manager via ctypes for plaintext-free storage on Windows, with in-memory and environment variable fallback for VPS/Linux. Includes automated sensitive token masking for logs and telemetry.
  - **Classes**: `CredentialVault`, `SensitiveMaskingFilter`
    - *Methods*: `get_secret()`, `set_secret()`, `delete_secret()`, `register_secret()`, `mask_sensitive()`
  - **Functions**: `get_secret()`, `set_secret()`, `delete_secret()`, `mask_sensitive()`

#### Folder: `trading-agent/scheduler`

**File:** `__init__.py`

**File:** `active_calendar_poller.py`
  - **Global Variables**: logger
  - **Classes**:
    - `ActiveCalendarPoller`
      - *Docstring*: Active Calendar Polling. Monitors economic calendar at release timestamps with aggressive polling to capture actual macro data instantly.
      - *Methods*:
        - `__init__(self)`
        - `start(self)`
        - `stop(self)`
        - `_check_schedule(self)`
        - `_poll_for_events(self)`
        - `_generate_pseudo_news(self)`

**File:** `alpha_discovery_scheduler.py`
  - **Global Variables**: logger
  - **Classes**:
    - `AlphaHypothesis`
    - `CandidateAlphaProposal`
      - *Methods*: `to_dict()`
    - `AlphaDiscoveryScheduler`
      - *Docstring*: Autonomous scheduler loop that generates and backtests alpha hypotheses using WalkForwardEngine, vetting candidates with WFE > 0.60.
      - *Methods*:
        - `__init__(self, settings, interval_hours, lookback_days, is_window_days, oos_window_days, step_days, min_wfe, min_oos_sharpe, recovery_event, notifier)`
        - `generate_hypotheses(self, symbols)`
        - `evaluate_hypothesis(self, hypothesis)`
        - `_persist_proposal(self, proposal)`
        - `promote_to_paper_active(self, proposal_id, session=None)`
        - `run_discovery_cycle(self, max_evaluations)`
        - `start(self)`
        - `stop(self)`

**File:** `cycle_scheduler.py`
  - **Global Variables**: logger
  - **Classes**:
    - `CycleScheduler`
      - *Docstring*: Executes full multi-stage market analysis cycle.
      - *Methods*:
        - `__init__(self)`
        - `_pre_cycle_setup(self)`
        - `_get_symbol_paper_stats(self, session, symbol)`
        - `run_once(self)`
        - `stop(self)`

**File:** `digest_slice_scheduler.py`
  - **Global Variables**: logger
  - **Classes**:
    - `DigestSliceScheduler`
      - *Docstring*: Background scheduler generating NewsDigestSlice every 2 hours.
      - *Methods*:
        - `__init__(self)`
        - `run_once(self, session, trigger)`
        - `start(self)`
        - `stop(self)`

**File:** `edge_strategy_runner.py`
  - **Global Variables**: logger
  - **Classes**:
    - `EdgeStrategyRunner`
      - *Docstring*: Standalone background runner evaluating quantitative edge strategies (tsm_momentum, gap_fade, xau_trend_engine) with position limits and cooldown enforcement.
      - *Methods*:
        - `__init__(self, settings, execution_service=None, poll_seconds=60, market_data_scheduler=None, recovery_event=None)`
        - `start(self)`
        - `stop(self)`
        - `hot_reload_strategy(self, strategy_id, parameters)`
        - `reload_strategies_from_db(self, session)`
        - `_is_in_cooldown(self, session, strategy_id, symbol, now_ts)`
        - `run_once(self)`
        - `_is_disabled(self, session, strategy_id, symbol)`
        - `_materialize_and_route(self, session, sig)`: Materialisasi order, evaluasi level intraday, dan pre-filter rasio R:R >= min_rr sebelum routing ke Reactive Graph.

**File:** `graph_cycle_scheduler.py`
  - **Global Variables**: `logger`
  - **Classes**:
    - `GraphCycleScheduler`
      - *Docstring*: Orchestration wrapper adapting LangGraph execution workflow into the core agent lifecycle.
      - *Attributes*: `_cycle_lock`, `_checkpointer_ready`, `_recovery_complete_event` (asyncio.Event, recovery coordination), `_first_cycle_done`, `execution_service`
      - *Methods*:
        - `__init__(self, settings, mt5_client=None, fundamental_stage=None, per_asset_stage=None, dry_run=False, recovery_event=None, macro_data_scheduler=None, execution_service=None)`
        - `_ensure_checkpointer_setup(self)` — Initializes and verifies checkpointer connection pool with retries and fallback
        - `_update_adaptive_thresholds_realtime(self)` — Real-time threshold adjustment
        - `_should_run_session_trigger(self)` — Checks for London/NY open market sessions
        - `run_session_trigger(self)` — Executes session-aligned analysis cycle
        - `run_session_trigger_loop(self)` — Background loop for session-aligned triggers
        - `run_once(self)` — Executes single cycle waiting for recovery completion before state acquisition
        - `start(self)`
        - `stop(self)`
        - `aclose(self)` — async teardown checkpointer pool
        - `cleanup_user_market_intel(self, cycle_id)`
        - `_check_system_health_trend(self)`

**File:** `macro_data_scheduler.py`
  - **Global Variables**: `logger`
  - **Classes**:
    - `MacroDataScheduler`
      - *Docstring*: Background worker refreshing 11 macro and sentiment data feeds (VIX, DXY, CFTC COT, FedWatch, Yields, Oil Inventory) at 30-minute intervals.
      - *Methods*:
        - `_get_global_lock(cls)`
        - `__init__(self, settings)`
        - `refresh_macro_data(self)`
        - `start(self)`
        - `stop(self)`

**File:** `market_data_scheduler.py`
  - **Global Variables**: logger
  - **Classes**:
    - `MarketDataScheduler`
      - *Docstring*: Background worker for periodic synchronization of MT5 market data (OHLCV & indicators) with auto-healing reconnection.
      - *Methods*:
        - `__init__(self, settings, mt5_client=None)`
        - `sync_now(self, session=None)`
        - `start(self)`
        - `stop(self)`

**File:** `flash_crash_detector.py`
  - **Global Variables**: `logger`, `DEFAULT_SYMBOL_RULES`
  - **Classes**:
    - `FlashCrashDetector`
      - *Docstring*: Flash-crash monitor and circuit breaker using dual-threshold confluence (Relative ATR + minimum % move) with automated stop-loss tightening to breakeven.
      - *Methods*:
        - `__init__(self, settings, execution_service=None, notifier=None)`
        - `get_symbol_thresholds(self, symbol)`
        - `load_persisted_blocks(self, session)`
        - `is_symbol_blocked(self, symbol)` -> `bool`
        - `check(self, session)` -> `list[dict]`
        - `_protect_open_positions(self, session, symbol, now)`

**File:** `news_watcher.py`
  - **Global Variables**: logger, HIGH_IMPACT_KEYWORDS, MEDIUM_IMPACT_KEYWORDS
  - **Classes**:
    - `NewsWatcher`
      - *Docstring*: Monitors incoming news items to detect high-impact breaking events and trigger targeted re-analysis.
      - *Methods*:
        - `__init__(self)`
        - `run_once(self)` — cek berita terbaru & klasifikasi dampak
        - `start(self)`
        - `stop(self)`
        - `_text_for_classification(self)`
        - `_is_high_impact(self)`
        - `_is_shock_only_strict(self)`
        - `_matches_recent_calendar_window(self)`
        - `_is_medium_impact(self)`
        - `_get_affected_symbols(self)`
        - `_run_targeted_reanalysis_and_route(self)`

**File:** `order_reconciler.py`
  - **Global Variables**: logger
  - **Classes**:
    - `OrderReconciler`
      - *Docstring*: High-frequency Active Order and Position Reconciliation Worker. Ensures bidirectional order state synchronization, detection of executed MT5 limit/stop orders, tracking of external cancellations/expirations, partial fills, closed position detection (SL/TP hit), TradePlan status updates, and live position modifications.
      - *Properties*:
        - `is_running(self)` -> `bool`
      - *Methods*:
        - `__init__(self, settings=None, mt5_client=None, execution_service=None, broker_adapter=None, interval_seconds=15.0)`
        - `get_terminal_orders(self)` -> `Optional[List[dict]]`
        - `get_terminal_positions(self)` -> `Optional[List[dict]]`
        - `reconcile_orders(self, session, terminal_orders, terminal_positions)` -> `dict`
          - *Docstring*: Reconciles active order states between broker terminal and database with in-flight grace periods, tracking fills, partials, and expirations.
        - `reconcile_positions(self, session, terminal_positions)` -> `dict`
          - *Docstring*: Menyelaraskan posisi terbuka antara broker dan database. Mendeteksi penutupan eksternal (SL/TP hit), perubahan volume/SL/TP, pembaruan drawdown RiskGate, dan adopsi posisi tidak terlacak.
        - `reconcile_once(self, session=None)` -> `dict`
          - *Docstring*: Executes a complete order and position reconciliation cycle with fail-safe abortion when broker terminal is disconnected.
        - `start(self)`
        - `stop(self)`

**File:** `playbook_curator.py`
  - **Docstring**: Autonomous Playbook Curator Daemon distilling winning trade reflections into validated strategy playbooks.
  - **Classes**: `PlaybookCurator`
    - *Methods*: `__init__(settings=None)`, `run_once(session=None)`, `curate_symbol(session, symbol)`, `start(interval_hours=24)`, `stop()`

**File:** `position_guardian.py`
  - **Global Variables**: logger, SYMBOL_CURRENCIES
  - **Classes**:
    - `PositionGuardian`
      - *Docstring*: Evaluates economic calendar for upcoming high-impact events and applies defensive position protections.
      - *Attributes*: `_kill_switch_triggered` (state-latch debouncing for emergency kill switch)
      - *Methods*:
        - `__init__(self)`
        - `check_and_protect(self)` — evaluates calendar and executes open position protections with debounced kill switch
        - `on_tick(self, event)` — EventBus subscriber handler for TickPriceEvent with debounced kill switch
        - `_protect_position(self)` — eksekusi tindakan proteksi (alert/close)
        - `check_friday_close_protection(self)` — R-4: Friday close protection + auto_close_friday_positions option
        - `evaluate_position_threat_with_jev(self, position, current_price=None)` — Sub-100ms real-time position threat assessment via TypeSafe Jev System One (evaluates adverse momentum & stop loss threat)

**File:** `position_exit_reviewer.py`
  - **Global Variables**: logger
  - **Classes**:
    - `PositionExitReviewer`
      - *Docstring*: Subsystem periodically reviewing open positions based on latest price action and market structure with TypeSafe Jev System One pre-screen gating.
      - *Methods*:
        - `__init__(self)`
        - `start(self)`
        - `stop(self)`
        - `_review_positions(self)` — periodically reviews open positions with Jev System One thesis prescreen before executing full Stage 2 analysis
        - `_get_minimal_ohlcv(self)`

**File:** `position_supervisor.py`
  - **Docstring**: Unified Position Supervisor consolidating MT5 position polling into a single high-efficiency supervisor loop and distributing snapshots to downstream evaluators.
  - **Classes**:
    - `PositionSupervisor`
      - *Methods*:
        - `__init__(self, mt5_client, settings=None, poll_interval_seconds=10.0)`
        - `register_evaluator(self, name, callback)`
        - `unregister_evaluator(self, name)`
        - `get_latest_snapshot(self)`
        - `poll_once(self)`
        - `start(self)`
        - `stop(self)`

**File:** `post_release_analyzer.py`
  - **Global Variables**: `logger`, `CURRENCY_TO_SYMBOLS`
  - **Classes**:
    - `PostReleaseAnalyzer`
      - *Docstring*: Event-driven re-analyzer triggered post-high-impact economic release (waits 15-minute price settlement, then triggers Stage 2 solely for impacted currency pairs with actual vs consensus surprises).
      - *Methods*:
        - `__init__(self, settings, per_asset_stage=None, execution_service=None, notifier=None, poll_seconds=120, settle_seconds=900)`
        - `is_event_handled(self, event_id)` -> `bool`
        - `_get_affected_symbols(self, currencies)` -> `list[str]`
        - `_build_surprise_context(self, events)` -> `str`
        - `run_once(self)`
        - `start(self)`
        - `stop(self)`

**File:** `scraper_runner.py`
  - **Global Variables**: logger, DEFAULT_SCRAPER_TIMEOUTS
  - **Classes**:
    - `ScraperRunner`
      - *Docstring*: Executes data scrapers (news, calendar, social, macro) via rate-limited staggered queues
      - *Methods*:
        - `__init__(self)`
        - `_register_scraper(self, scraper)`
        - `_unregister_scraper(self, scraper)`
        - `_cleanup_timed_out_scrapers(self)`
        - `run_all(self)`
        - `stop(self)`

**File:** `strategy_synthesis_scheduler.py`
  - **Global Variables**: logger
  - **Classes**:
    - `SynthesizedStrategyCandidate`
      - *Docstring*: Metadata and backtest performance for a synthesized strategy candidate.
      - *Methods*: `to_dict()`
    - `HistoricalSliceSession`
      - *Docstring*: Proxy AsyncSession for sandbox backtesting that guarantees zero-lookahead bias.
      - *Methods*: `execute(self, stmt)`, `commit(self)`, `rollback(self)`
    - `StrategySynthesisScheduler`
      - *Docstring*: Synthesizes novel quantitative edge strategies, compiles and tests in a backtesting sandbox, and registers qualified candidates passing quant thresholds (Sharpe > 1.5, Max DD < 10%).
      - *Methods*:
        - `__init__(self, settings, interval_hours=48.0, min_sharpe=1.5, max_drawdown_pct=10.0, min_trades=5, target_symbols=None, recovery_event=None, notifier=None, edge_strategy_runner=None)`
        - `validate_code_safety(self, code_str)`
        - `_lint_check_code(cls, code_str)`
        - `sanitize_strategy_code(cls, code_str)`
        - `_repair_unclosed_delimiters(cls, code_str)`
        - `_reindent_unindented_methods(cls, code_str)`
        - `_repair_unclosed_try_blocks(cls, code_str)`
        - `compile_strategy_class(self, code_str, class_name)`
        - `run_backtest_sandbox(self, strategy_cls, symbol, simulated_returns=None)`
        - `run_historical_simulation(self, strategy_cls, symbol, lookback_candles=300, min_candles=60)`
        - `run_walk_forward_validation(self, strategy_cls, symbol, returns=None, split_ratio=0.60)`
        - `synthesize_code(self, symbol, concept)`
        - `evaluate_and_register_candidate(self, strategy_id, class_name, code_str, symbol, simulated_returns=None)`
        - `_persist_candidate(self, candidate)`
        - `run_synthesis_cycle(self)`
        - `start(self)`
        - `stop(self)`

**File:** `trailing_stop_manager.py`
  - **Global Variables**: logger
  - **Classes**:
    - `TrailingStopManager`
      - *Docstring*: Manages automated trailing stops and structural breakeven shifts for open positions.
      - *Methods*:
        - `__init__(self)`
        - `run_once(self)` — cek posisi terbuka & update stop loss
        - `start(self)`
        - `stop(self)`

**File:** `trigger_checker.py`
  - **Global Variables**: logger
  - **Classes**:
    - `TriggerChecker`
      - *Docstring*: Evaluates pending price and macro triggers; fires targeted re-analysis upon fulfillment.
      - *Properties*: `asset_universe`, `dry_run`, `_mt5`, `execution_service`
      - *Methods*:
        - `__init__(self)`
        - `run_once(self)` — satu iterasi evaluasi trigger
        - `check_invalidation_conditions(self)`
        - `start(self)`
        - `stop(self)`
        - `_handle_force_close(self)`
        - `_expire_stale_triggers(self)`
        - `_get_pending_triggers(self)`
        - `_fire_trigger(self)`
        - `_evaluate_trigger(self)`
        - `_check_price_level(self)`
        - `_check_indicator(self)`
        - `_check_time(self)`
        - `_trigger_age_exceeded(self)`
        - `_background_reanalysis(self, symbol)` — decoupled background reanalysis after preplanned order trigger
        - `_spawn_background_reanalysis(self, symbol)` — spawns deduplicated background task with retained reference

#### Folder: `trading-agent/scrapers`

**File:** `base_scraper.py`
  - **Global Variables**: logger
  - **Functions**:
    - `kill_process_tree(pid: Optional[int]) -> bool`
      - *Docstring*: Terminates a process and all its children/descendants using psutil or Windows taskkill fallback.
  - **Classes**:
    - `BaseScraper`
      - *Methods*:
        - `__init__(self)`
        - `__del__(self)`
        - `__enter__(self)`
        - `__exit__(self, *args)`
        - `_cleanup_stale_profile_locks(profile_dir: Path)`
        - `_detect_browser_path(self)`
        - `_initialize_browser(self)`
        - `_is_cloudflare_challenge(self)`
        - `_handle_cloudflare_challenge(self)`
        - `navigate_with_fallback(self)`
        - `_fallback(self)`
        - `close(self)`
        - `_cleanup_temp_dir(self)`

**File:** `models.py`
  - **Classes**:
    - `CalendarEvent`
    - `ScrapedNews`
    - `ScrapedTweet`
    - `FedProbability`
    - `FedMeeting`

##### Folder: `trading-agent/scrapers/calendar`

**File:** `__init__.py`

**File:** `calendar_finnhub.py`
  - **Global Variables**: logger, _IMPACT_MAP, COUNTRY_TO_CURRENCY
  - **Classes**:
    - `FinnhubCalendarScraper`
      - *Docstring*: Fetches economic calendar events from Finnhub API.
      - *Class Variables*: BASE_URL
      - *Methods*:
        - `__init__(self)`
        - `fetch_today_events(self)`
        - `fetch_events(self)`
        - `afetch_today_events(self)`
        - `afetch_events(self)`

**File:** `calendar_forexfactory.py`
  - **Global Variables**: logger
  - **Classes**:
    - `ForexFactoryCalendarScraper`
      - *Methods*:
        - `__init__(self)`
        - `fetch_events(self)`

**File:** `calendar_investing.py`
  - **Global Variables**: logger
  - **Classes**:
    - `InvestingCalendarScraper`
      - *Methods*:
        - `__init__(self)`
        - `_find_calendar_table(self)`
        - `_apply_time_filter_human_like(self)`
        - `_load_all_calendar_rows(self)`
        - `fetch_events(self)`

##### Folder: `trading-agent/scrapers/macro`

**File:** `__init__.py`

**File:** `cme_fedwatch.py`
  - **Global Variables**: logger
  - **Classes**:
    - `FedWatchScraper`
      - *Methods*:
        - `__init__(self)`
        - `fetch_probabilities(self)`

##### Folder: `trading-agent/scrapers/news`

**File:** `__init__.py`

**File:** `kitco_news.py`
  - **Global Variables**: logger
  - **Classes**:
    - `KitcoNewsScraper`
      - *Methods*:
        - `__init__(self)`
        - `fetch_news(self)`

**File:** `rss_base.py`
  - **Global Variables**: logger
  - **Classes**:
    - `RssBaseScraper`
      - *Docstring*: RSS scraper menggunakan feedparser — TIDAK memerlukan browser.
      - *Methods*:
        - `__init__(self)`
        - `fetch_news(self)`
        - `close(self)`

**File:** `rss_bloomberg.py`
  - **Classes**:
    - `BloombergRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_boe.py`
  - **Classes**:
    - `BoeRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_boj.py`
  - **Classes**:
    - `BojRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_cnbc.py`
  - **Classes**:
    - `CnbcRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_coindesk.py`
  - **Classes**:
    - `CoindeskRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_dow_jones.py`
  - **Classes**:
    - `DowJonesRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_ecb.py`
  - **Classes**:
    - `EcbRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_fed.py`
  - **Classes**:
    - `FedRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_forexlive.py`
  - **Classes**:
    - `ForexliveRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_ft.py`
  - **Classes**:
    - `FinancialTimesRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_fxstreet.py`
  - **Classes**:
    - `FxstreetRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_investing.py`
  - **Classes**:
    - `InvestingRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_marketwatch.py`
  - **Classes**:
    - `MarketwatchRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_rba.py`
  - **Classes**:
    - `RbaRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_reuters.py`
  - **Classes**:
    - `ReutersRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `rss_wsj.py`
  - **Classes**:
    - `WsjRssScraper`
      - *Methods*:
        - `__init__(self)`

**File:** `tradingview_news.py`
  - **Global Variables**: logger
  - **Classes**:
    - `TradingViewNewsScraper`
      - *Methods*:
        - `__init__(self)`
        - `fetch_news(self)`

##### Folder: `trading-agent/scrapers/sentiment`

**File:** `binance_sentiment.py`
  - **Global Variables**: logger
  - **Classes**:
    - `BinanceSentimentFetcher`
      - *Methods*:
        - `__init__(self)`

**File:** `fxssi_sentiment.py`
  - **Global Variables**: logger, `SYMBOL_ALIASES`
  - **Classes**:
    - `FXSSISentimentFetcher`
      - *Methods*:
        - `__init__(self)`
        - `_parse_html(self)`
        - `fetch_sync(self)`

**File:** `myfxbook_sentiment.py`
  - **Global Variables**: logger, `SYMBOL_ALIASES`
  - **Classes**:
    - `MyFxBookSentimentFetcher`
      - *Methods*:
        - `__init__(self)`
        - `_parse_html(self)`
        - `fetch_sync(self)`

##### Folder: `trading-agent/scrapers/social`

**File:** `__init__.py`

**File:** `twitter_watch.py`
  - **Global Variables**: logger
  - **Classes**:
    - `TwitterWatchScraper`
      - *Methods*:
        - `__init__(self)`
        - `_load_quarantined(self)`
        - `_mark_quarantined(self)`
        - `_pick_session(self)`
        - `_load_cookies(self)`
        - `_parse_iso(self)`
        - `_get_url_hash(self)`
        - `fetch_latest_tweets(self)`

#### Folder: `trading-agent/skills`

**File:** `__init__.py`

**File:** `curator.py`
  - **Docstring**: Skill lifecycle curator managing Active -> Stale -> Archived transitions and core skill protection.
  - **Classes**: `SkillCurator`
    - *Methods*: `apply_lifecycle_transitions()`
    - *Variables*: `STALE_AFTER_DAYS`, `ARCHIVE_AFTER_DAYS`, `PROTECTED_SKILLS`

**File:** `loader.py`
  - **Global Variables**: logger, _SKILLS_DIR
  - **Functions**:
    - `is_playbook_eligible()`
      - *Docstring*: Verify if a playbook is currently eligible for production use (not demoted/archived in ledger).
    - `get_progressive_playbook_index()`
      - *Docstring*: Level 0: Compact index of available playbooks and setups (< 150 tokens).
    - `load_skill()`
      - *Docstring*: Muat isi skill markdown berdasarkan nama (tanpa .md).
    - `list_skills()`
      - *Docstring*: Lists all detected skill specification files in the repository.
    - `compose_system_prompt()`
      - *Docstring*: Rangkai beberapa skill menjadi satu system prompt dan isi template variables.
    - `get_dynamic_micro_skills()`
      - *Docstring*: Dynamically routes specialized domain trading playbooks based on asset class and regime.
    - `invalidate_cache()`
      - *Docstring*: Clears in-memory LRU cache for loaded skills.
  - **Classes**:
    - `SafeDict`
      - *Docstring*: Dictionary helper leaving missing template variables untouched.
      - *Methods*:
        - `__missing__(self)`

**File:** `usage_tracker.py`
  - **Docstring**: Skill usage telemetry tracking (.usage.json ledger) for execution and inspection counts.
  - **Classes**: `SkillUsageTracker`
    - *Methods*: `load()`, `save()`, `record_use()`, `record_view()`

**File:** `trading_skill_linter.py`
  - **Docstring**: Automated linter and validator for trading playbook skills enforcing description limits, market regimes, heading standards, and anti-bloat rules.
  - **Classes**: `LintIssue`, `TradingSkillLinter`
    - *Methods*: `lint_skill()`, `lint_file()`, `lint_directory()`, `is_valid_skill()`

##### Folder: `trading-agent/skills/crystallized`

**File:** `eurusd_trend.md`
- Crystallized institutional playbook for EURUSD verified across winning cycles with empirical track record, tactical directives, execution invariants, and invalidation scenarios.

##### Folder: `trading-agent/skills/trading`

**File:** `adjudication_framework.md`
- Rule specifications for Stage 2 Synthesis Adjudicator (governing dynamic trust weights, evidence hierarchy, conflict resolution).

**File:** `caveman_mode.md`
- Token efficiency skill providing scope-limited compression on non-analytical text while preserving full reasoning depth.

**File:** `central_banks_framework.md`
- Authoritative institutional framework for the 5 major central banks (The Fed, ECB, BoE, BoJ, RBA), reaction functions, interest rate expectations, yield differentials, and multi-channel transmission to currency valuation.
- **Sections**: Core Foundational Principle (interest rate expectations as dominant currency driver), The 5 Major Central Banks (The Fed Dual Mandate 2% Core PCE vs labor, ECB Single Mandate HICP medium-term & Two-Pillar, BoE Tiered Mandate CPI 2% & Gilt/fiskal, BoJ Deflation Exit Shunto & Carry trade, RBA Triple Mandate 2-3% Trimmed Mean & Iron ore terms of trade), Relative Attractiveness Evaluation (nominal policy rate differentials, forward guidance divergence, real yield spreads, neutral rate r* estimates per bank), Seven Independent Non-Rate Channels (Safe-Haven vs Risk-On, Reserve Currency Status, Sovereign Fiscal Risk / Gilt, Commodity Terms of Trade / Iron Ore, Carry Trade Unwind, Geopolitics / Tariffs, Institutional Credibility), and Currency Synthesis Matrix for Stage 1 & Stage 2.

**File:** `commodity_analysis.md`

**File:** `crypto_analysis.md`

**File:** `event_probability_playbook.md`
- Authoritative institutional playbook for central bank decision probabilities (FOMC, ECB, BOE, BOJ), market expectation deconstruction vs policy reality, sell-the-news risk mitigation, and asset pricing asymmetry evaluation.
- **Sections**: 5-Stage Thinking Flow Protocol (Data Gathering, Priced-In Testing, Historical Precedents Matching, Press Conference / SEP Decoding, Multi-Scenario Trading Plan & LangGraph Handshake), 5 Canonical Historical Fed Surprise Precedents (1994 Greenspan, 2013 Bernanke No-Taper, 2015 Yellen Global Risk Hold, 2019 Powell Hawkish Cut, 2022 Powell WSJ Leak), Taxonomy of 5 Consensus Failure Mechanisms (Financial Conditions Feedback Loop, Mandate Asymmetry Minimax, Institutional Credibility Defense, Information Asymmetry, Forward Guidance Ambiguity), Analog Matching Engine Rubric, 4-Quadrant Action vs Guidance Matrix, 6-Section Institutional Output Format, and 3-Scenario Trading Plan LangGraph Handshake (`user_market_intel`).

**File:** `lessons_learned.md`
- Empirical trade lessons standard operating procedures and adaptive execution directives.
- **Sections**: Post-SL Rules (anti-revenge trade, liquidity validation), Fakeout Avoidance (priced-in >=7, FVG confirmation), Multi-Timeframe Discipline (D1 dominance, R:R minimum), High-Probability Entry Signals (London Open, post-NFP/CPI, NY-London overlap), Win Rate Adaptation Protocol (threshold auto-adjustment), Confluence Score Sufficiency Rules, WAIT Over-Use Warning.

**File:** `liquidity_and_macro_edge.md`
- Skill/Edge-layer rules for Liquidity Sweeps, Macro Bias, and Volatility Regimes.

**File:** `macro_analysis_framework.md`

**File:** `market_dynamics_framework.md`

**File:** `performance_notes.md`

**File:** `risk_management_principles.md`

**File:** `session_timing_rules.md`
- Market session timing guidelines with UTC trading windows, liquidity session modifiers, and ADR expansion rules.
- **Sections** (expanded): Session Windows & Characteristics, Session Modifiers, Intraday Range Remaining, Prime Entry Windows (★★★★★ windows), AVOID Windows (Off-Peak/Friday/Monday/Pre-news), Crypto (BTCUSD) Timing Rules, Oil (XTIUSD) Timing Rules.

**File:** `smc_ict_playbook.md`
- Institutional Smart Money Concepts playbook featuring structured tool invocation sequences, confluence scorecards, and safety gates.
- **Sections** (expanded): Added CRITICAL Anti-Over-Conservative Directive — Active Opportunity Scan checklist (D1/H4/Alignment/Blocker), WAIT Correct/WRONG conditions, D1 ADX > 25 Bonus (-1 threshold), 3/3 Specialist Consensus Bonus (-1 threshold).


**File:** `telegram_persona.md`

#### Folder: `trading-agent/telegram_bot`

**File:** `__init__.py`

**File:** `bot.py`
  - **Global Variables**: logger
  - **Classes**:
    - `TelegramBot`
      - *Docstring*: Operational Telegram Bot interface for Monika quantitative trading platform.
      - *Methods*:
        - `__init__(self)`
        - `_register_handlers(self)`
        - `request_fallback_consent(self)`
        - `_is_authorized(self)`
        - `_is_admin(self)`
        - `_balance_markdown_chunk(chunk)`
        - `_chunk_text(self)`
        - `_cmd_intel(self, update, context)`
        - `_cmd_archive_intel(self, update, context)`
        - `_cmd_tearsheet(self, update, context)`
        - `_cmd_unsuspend(self, update, context)`
        - `_cmd_closeall(self, update, context)`
        - `_cmd_override(self, update, context)`
        - `_cmd_regime(self, update, context)`
        - `_cmd_audit(self, update, context)`
        - `_cmd_calendar(self, update, context)`
        - `_cmd_skills(self, update, context)`
        - `_cmd_plugins(self, update, context)`
        - `_cmd_memory(self, update, context)`
        - `_cmd_strategies(self, update, context)`
        - `_resolve_action_agent(self, action_id, fallback_chat_id=None)`
        - `stop(self)`


**File:** `chat_agent.py`
  - **Global Variables**: logger, TELEGRAM_MAX_CHARS, HISTORY_WINDOW, MAX_HISTORY_CHARS, SESSION_TIMEOUT_HOURS
  - **Functions**:
    - `_sanitize_telegram_format(text)`
  - **Classes**:
    - `PendingAction`
      - *Docstring*: Temporary storage for proposed trading actions awaiting operator confirmation.
      - *Methods*:
        - `__init__(self)`
        - `is_expired(self)`
        - `to_dict(self)`
        - `from_dict(cls, d)`
    - `ChatAgent`
      - *Docstring*: Manages conversational chat session and LLM context for authorized Telegram users.
      - *Methods*:
        - `__init__(self)`
        - `_detect_model_preference(self)`
        - `_classify_query_complexity(self)`
        - `handle(self)`
        - `_persist_pending_action(self, action)`
        - `_delete_persisted_pending_action(self, action_id)`
        - `get_pending_action(self, action_id)`
        - `_run_with_gemini(self)`
        - `_run_with_groq(self)`
        - `_run_with_claude(self)`
        - `_run_tier_deep_research(self, ...)`
        - `_create_pending_action(self)`
        - `is_symbol_session_approved(self, symbol)`
        - `add_session_approval(self, symbol)`
        - `approve_for_session(self, action_id)`
        - `_stream_response(self, text_stream, thinking_msg, original_prompt, model_name, start_time, update=None)`
        - `_handle_streaming(self, user_id, message_text, model_name, thinking_msg, start_time, update=None, session_id=None)`
        - `_execute_db_mutation(self, params)`
        - `set_tool_event_listener(self, listener)`
        - `interrupt(self, redirect_message)`
        - `steer(self, feedback)`
        - `redirect(self, new_instruction)`
        - `hard_cancel(self)`

**File:** `chat_compaction.py`
  - **Docstring**: Micro-compactor for Telegram chat history maintaining high-fidelity recent turns and summarizing older context.
  - **Classes**: `ChatMicroCompactor`
    - *Methods*: `compact_history()`

**File:** `chat_tool_router.py`
  - **Global Variables**: logger, DATABASE_PATTERNS
  - **Classes**:
    - `ChatToolRouter`
      - *Docstring*: Routes Telegram queries to relevant tool subsets via hybrid regex and TF-IDF vector matching for token efficiency.
      - *Methods*:
        - `__init__(self, all_tools)`
        - `_build_vector_space(self)`
        - `_extract_query_vector(self, query)`
        - `_cosine_similarity(self, vec_a, vec_b)`
        - `_get_tools_by_names(self, names)`
        - `route_tools_for_query(self, query)`

**File:** `command_router.py`
  - **Global Variables**: logger
  - **Classes**:
    - `CommandType`
      - *Class Variables*: DIRECT, CHAT, ADMIN
    - `ParsedCommand`
    - `CommandRouter`
      - *Docstring*: Parser dan router pesan Telegram.
      - *Methods*:
        - `__init__(self)`
        - `is_authorized(self)`
        - `is_admin(self)`
        - `parse(self)`
        - `build_help_text(self)`
        - `build_confirm_keyboard(self)`
        - `build_close_keyboard(self)`

**File:** `fuzzy_router.py`
  - **Docstring**: 3-Tier fuzzy command resolution engine (Exact -> Alias -> Levenshtein) for Telegram bot commands.
  - **Classes**: `FuzzyCommandRouter`
    - *Methods*: `register_command()`, `resolve_command()`, `get_command_help()`

**File:** `topic_manager.py`
  - **Global Variables**: logger
  - **Classes**:
    - `TopicManager`
      - *Docstring*: Manages Telegram forum topic bindings and lifecycle for chat session isolation.
      - *Methods*:
        - `__init__(self, session_factory=None)`
        - `get_session_for_topic(self, chat_id, topic_id)`
        - `create_topic_session(self, chat_id, topic_id, topic_name=None, focus_pair=None)`
        - `cleanup_deleted_topic(self, chat_id, topic_id)`
        - `list_topics_for_chat(self, chat_id)`

**File:** `vintage_formatter.py`
  - **Docstring*: Vintage Teletype Slip Formatters for Telegram Bot.
  - **Functions**:
    - `make_header(title, width=46)`: Create a telegraph dispatch slip header.
    - `make_footer(width=46)`: Create a telegraph dispatch slip footer.
    - `format_status_slip(status_text, pos_count, daily_pnl, drawdown, last_analysis, now_str=None, width=46)`: Format agent status as teletype slip.
    - `format_positions_slip(positions, width=46)`: Format open positions as fixed-width ledger.
    - `format_risk_slip(status_text, mode, streak_policy, suspended_symbols, daily_pnl=None, drawdown=None, reason=None, width=46)`: Format risk state as teletype slip.
    - `format_stats_slip(stats, equity_curve=None, width=46)`: Format paper trading performance as telegraph slip.
    - `format_alert_slip(title, detail, severity="PERINGATAN", width=46)`: Format system dispatch alert.
    - `format_help_slip(commands, width=46)`: Format bot command index.

**File:** `voice_handler.py`
  - **Global Variables**: logger
  - **Classes**:
    - `VoiceHandler`
      - *Docstring*: Handles Telegram voice notes and audio memos with Gemini multimodal transcription.
      - *Methods*:
        - `__init__(self, bot_token, chat_agent, topic_manager=None, gemini_api_key=None)`
        - `_download_voice(self, file_id)`
        - `_transcribe_audio(self, audio_bytes, mime_type='audio/ogg')`
        - `handle_voice(self, update, context)`

**File:** `voice_safety_gate.py`
  - **Docstring**: Deterministic voice trade extraction safety gate with strict phoneme cleaning, symbol resolution, and parameter bounds.
  - **Classes**:
    - `VoiceTradeIntent`
    - `VoiceSafetyGate`
      - *Methods*: `extract_intent()`, `is_actionable()`

**File:** `test_architecture_fixes.py`
  - **Classes**:
    - `TestStateReducers` - Tests merge_dicts deep merge and merge_lists concatenation
    - `TestCacheBeforeCommitFix` - Tests cache update following MT5 execution
    - `TestRaceConditionRecheck` - Tests open position verification prior to order placement
    - `TestEdgeTrackerAutoEnforce` - Tests automatic pause during negative edge regimes
    - `TestReflectionVIXDefensive` - Tests defensive VIX fallback behavior

**File:** `test_paper_tracker_fix.py`
  - **Functions**:
    - `test_paper_trade_detection()`

**File:** `test_stage1_prefetcher.py`
  - **Functions**:
    - `test_stage1_data_bundler()`

**File:** `tests/analysis/test_llm_memory_cache_enhancements.py`
  - **Classes**:
    - `TestLLMMemoryCacheEnhancements` - Uji optimasi token, memory persistence, KV cache invariance, dan grounding fact sheet
      - *Methods*:
        - `test_gemini_thinking_none_no_inflation()`
        - `test_chronicle_writer_preserves_structural_events()`
        - `test_specialist_prompts_symbol_agnostic()`
        - `test_fact_sheet_includes_layer1_core_memory()`

**File:** `tests/analysis/test_audit_sota_enhancements.py`
  - **Functions**:
    - `test_cache_breakpoint_manager_dynamic_padding()`
    - `test_prompt_compressor_protects_stress_test_and_invalidation()`
    - `test_bull_and_bear_analyst_fallback_schema()`

**File:** `tests/analysis/test_composite_tools.py`
  - **Functions**:
    - `test_composite_tools_execution()`
    - `test_stage2_tools_v2_definitions()`

**File:** `tests/analysis/test_session_search.py`
  - **Functions**:
    - `test_session_search_postgresql_engine()`

**File:** `tests/execution/test_phase1_remediation.py`
  - **Functions**:
    - `test_direction_normalization()`
    - `test_mt5_place_order_direction_case_insensitive()`
    - `test_mt5_close_position_lots_keyword_compatibility()`
    - `test_precommit_gate_with_populated_trade_levels()`
    - `test_precommit_gate_db_fallback_when_sl_tp_missing()`
    - `test_position_sizing_blown_account_protection()`
    - `test_execution_service_mt5_parity()`
    - `test_evidence_verifier_assert_9_with_rationale_fallback()`
    - `test_provider_max_tokens_and_kwargs_signatures()`
    - `test_telegram_cmd_interrupt_synchronous()`
    - `test_trading_event_store_savepoint_isolation()`

**File:** `tests/execution/test_phase2_remediation.py`
  - **Functions**:
    - `test_group_a_inspect_iscoroutinefunction()`
    - `test_cw4_task_registry_core_tasks()`
    - `test_cw1_adhoc_scheduler_proxy_data_node()`
    - `test_sc5_trigger_checker_properties()`
    - `test_ex7_ex8_simulated_broker_adapter_parity_and_pending_sltp()`
    - `test_ex9_order_emulator_sell_breakeven_guard()`
    - `test_db10_risk_gate_flush_not_commit()`
    - `test_db9_portfolio_correlation_gate_negative_correlation()`
    - `test_an3_adversarial_check_prompt_initialization()`
    - `test_an8_fundamental_brief_schema_harmonization()`
    - `test_lu3_credential_pool_groq_multikey()`

**File:** `tests/execution/test_phase3_remediation.py`
  - **Functions**:
    - `test_db13_atomic_in_memory_locks()`
    - `test_sc1_position_sync_order_reconciler_exclusion()`
    - `test_sc3_session_trigger_loop_flag_and_stop()`
    - `test_cw3_recovery_event_waiting()`
    - `test_sc6_sc7_news_watcher_concurrency_and_cycle_lock()`
    - `test_sc8_duplicate_position_close_prevention()`
    - `test_sc9_background_tasks_cancellation()`
    - `test_cw5_graceful_shutdown_order()`
    - `test_cw6_pid_lock_release_helper()`
    - `test_db14_risk_gate_daily_trade_count_paper_vs_live()`
    - `test_db15_risk_gate_no_duplicate_pair_group()`

**File:** `tests/execution/test_phase4_remediation.py`
  - **Functions**:
    - `test_settings_and_schema_validation()`
    - `test_task_registry_and_core_tasks()`
    - `test_wall_clock_sleep_with_shutdown_event()`
    - `test_order_reconciler_shutdown_event()`
    - `test_order_executor_lot_step_zero_guard()`
    - `test_position_synchronizer_ea_heartbeat_guard()`
    - `test_order_emulator_watermark_trailing()`
    - `test_safe_ops_cancelled_error_handling()`
    - `test_claude_rate_limiter_tpm_tracking()`
    - `test_event_bus_type_validation()`
    - `test_agent_harness_turn_cost_calculation()`
    - `test_verified_market_snapshot_timeframe_filter()`

**File:** `tests/telegram_bot/test_telegram_enhancements.py`
  - **Functions**:
    - `test_streaming_cursor_and_throttling()`
    - `test_streaming_skips_when_empty()`
    - `test_provider_base_streaming_generator()`
    - `test_topic_manager_crud_and_session_resolution()`
    - `test_topic_manager_cleanup_deleted_topic()`
    - `test_topic_context_isolation()`
    - `test_bot_thread_id_routing_and_topic_binding()`
    - `test_voice_handler_transcription_and_routing()`
    - `test_voice_handler_handles_error_gracefully()`
    - `test_stream_response_error_handling()`

**File:** `tests/telegram_bot/test_chat_tool_router_stress.py`
  - **Functions**:
    - `test_slash_macro_variations(router)`
    - `test_slash_research_variations(router)`
    - `test_slash_command_case_insensitivity(router)`
    - `test_slash_help_returns_zero_tools(router)`
    - `test_unknown_slash_command_falls_through(router)`
    - `test_pure_greetings_zero_tools(router)`
    - `test_greeting_with_symbol_retains_tools(router)`
    - `test_greeting_masking_functional_query(router)`
    - `test_contoh_pertanyaan_full_routing(router)`
    - `test_contoh_pertanyaan_macro_excerpts(router)`
    - `test_timesfm_hijacking_macro_queries(router)`
    - `test_mixed_macro_and_technical(router)`
    - `test_mixed_macro_and_portfolio(router)`
    - `test_multi_domain_complex_fallback(router)`
    - `test_trade_intent_hijacking_research_and_macro(router)`
    - `test_empty_input_returns_all_tools(router)`
    - `test_whitespace_input_returns_all_tools(router)`
    - `test_non_string_inputs(router)`
    - `test_ultra_long_input(router)`
    - `test_symbols_and_emojis(router)`
    - `test_prompt_injection_like_strings(router)`

**File:** `tests/telegram_bot/test_chat_agent_deep_research_stress.py`
  - **Classes**:
    - `TestInjectMacroPlaybooksIdempotency`
      - *Methods*: `test_idempotency_string_prompt_repeated_calls()`, `test_idempotency_tuple_prompt_repeated_calls()`, `test_idempotency_under_asymmetric_skill_load_failure()`
    - `TestPromptTypePolymorphism`
      - *Methods*: `test_inject_returns_exact_type_and_structure()`, `test_run_tier_deep_research_with_tuple_and_string_prompts()`
    - `TestLoadSkillGracefulDegradation`
      - *Methods*: `test_inject_degrades_gracefully_when_both_skills_raise()`, `test_inject_degrades_gracefully_when_only_one_skill_fails()`, `test_inject_handles_empty_or_none_returns_from_load_skill()`, `test_deep_research_completes_when_skill_loading_fails()`
    - `TestSynthesizerToolWiringAndPropagation`
      - *Methods*: `test_synthesizer_wiring_when_tool_executor_is_provided()`, `test_synthesizer_wiring_when_tool_executor_is_none()`, `test_create_pending_action_accepts_save_market_intelligence()`, `test_create_pending_action_rejects_unknown_action_type()`, `test_create_pending_action_respects_circuit_breaker()`, `test_deep_research_resilience_to_status_callback_exceptions()`, `test_deep_research_resilience_when_specialist_workers_fail()`

**File:** `tests/telegram_bot/test_chat_agent_stress_challenge.py`
  - **Classes**:
    - `TestContohPertanyaanBenchmark`
      - *Methods*: `test_full_contoh_pertanyaan_file()`, `test_exact_chat_prompt_block()`, `test_prompt_block_with_markdown_fences()`, `test_benchmark_individual_paragraphs()`
    - `TestDiverseMacroEventQueriesSupported`
      - *Methods*: `test_short_macro_queries_supported()`, `test_long_macro_queries()`, `test_mixed_language_macro_queries()`, `test_greetings_with_macro_queries()`, `test_case_insensitivity_and_spacing()`
    - `TestMacroRoutingVulnerabilities`
      - *Methods*: `test_vulnerability_fed_without_the()`, `test_vulnerability_historical_precedents_r1_library()`, `test_vulnerability_asymmetric_intent_and_events()`
    - `TestNonMacroAndActionQueries`
      - *Methods*: `test_simple_commands_route_to_simple()`, `test_common_simple_queries()`, `test_short_greetings()`, `test_action_verbs_route_to_complex()`, `test_non_macro_complex_queries()`, `test_common_medium_queries()`
    - `TestBoundaryAndAdversarialInputs`
      - *Methods*: `test_empty_string_and_whitespace()`, `test_emojis_and_unusual_characters()`, `test_injection_payloads()`, `test_regex_special_characters()`, `test_zero_width_characters()`, `test_non_latin_scripts()`, `test_super_long_payloads()`, `test_vulnerability_non_string_type_crash()`

**File:** `tests/skills/test_event_probability_playbook.py`
  - **Classes**:
    - `TestEventProbabilityPlaybook`
      - *Methods*:
        - `test_playbook_loads_and_has_substantial_content()`
        - `test_playbook_discovered_in_skills_list()`
        - `test_compose_system_prompt_with_event_probability_playbook()`
        - `test_playbook_contains_5_stage_thinking_flow()`
        - `test_playbook_contains_5_canonical_historical_precedents()`
        - `test_playbook_contains_5_consensus_failure_mechanisms()`
        - `test_playbook_contains_analog_matching_engine()`
        - `test_playbook_contains_4_quadrant_action_vs_guidance()`
        - `test_playbook_contains_institutional_output_template()`
        - `test_playbook_contains_langgraph_integration()`
        - `test_playbook_priced_in_methodologies_alignment()`

**File:** `tests/skills/test_event_probability_stress.py`
  - **Classes**:
    - `TestEventProbabilityPlaybookStress`
      - *Methods*:
        - `test_concurrent_loading_and_invalidation()`
        - `test_composition_with_all_major_skills()`
        - `test_composition_under_tight_token_budget()`
        - `test_safedict_with_playbook_content()`
        - `test_template_substitution_adversarial_values()`
        - `test_path_traversal_attempts()`
        - `test_four_quadrants_exhaustive_coverage()`
        - `test_historical_precedents_multi_asset_coverage()`
        - `test_analog_matching_rubric_weights_sum_to_100()`
        - `test_decision_tree_covers_all_5_precedents()`
        - `test_institutional_output_template_has_all_6_sections()`
        - `test_save_market_intelligence_contract_parameters()`

**File:** `tests/skills/test_playbook_stress_challenge.py`
  - **Classes**:
    - `TestPlaybookStressChallenge`
      - *Methods*:
        - `test_spike_avoidance_rules_defined()`
        - `test_remedy_1_quadrant_2_avoids_pre_release_orders()`
        - `test_remedy_2_analog_matching_rubric_includes_powell_2019()`
        - `test_remedy_3_priced_in_score_clamping_and_gate_alignment()`
        - `test_remedy_4_timing_h4_close_reconciled_with_presser_entry()`
        - `test_distinct_five_failure_mechanisms()`
        - `test_action_vs_guidance_four_quadrants()`
        - `test_downstream_save_market_intelligence_schema_compatibility()`

**File:** `tests/test_cli_theme.py`
  - **Functions**:
    - `test_theme_color_constants()`
    - `test_stamp_formatters()`
    - `test_get_console()`
    - `test_build_tui_css()`
    - `test_build_chat_css()`

**File:** `tests/test_event_probability_flow.py`
  - **Docstring**: Comprehensive Integration Test Suite for Macro Event Probability Flow & Trading Plan Integration.
  - **Classes**:
    - `TestBenchmarkQueryClassification`
      - *Methods*: `test_exact_benchmark_prompt_classified_as_deep_research()`, `test_full_benchmark_file_classified_as_deep_research()`, `test_benchmark_query_variations_classified_as_deep_research()`
    - `TestIsMacroEventQuery`
      - *Methods*: `test_benchmark_query_returns_true()`, `test_constituent_sentences_return_true()`, `test_negative_cases_return_false()`
    - `TestInjectMacroPlaybooks`
      - *Methods*: `test_inject_macro_playbooks_loads_both_skills_string_prompt()`, `test_inject_macro_playbooks_tuple_format()`, `test_inject_macro_playbooks_idempotent()`
    - `TestDynamicSubagentPoolMacroDecomposition`
      - *Methods*: `test_worker_macro_spawned_with_required_toolset()`
    - `TestDeepResearchSynthesizer`
      - *Methods*: `test_synthesizer_runs_with_tools_and_tool_executor()`
    - `TestSaveMarketIntelligencePendingAction`
      - *Methods*: `test_create_pending_action_from_save_market_intelligence()`, `test_deep_research_reply_captures_pending_action_in_agent()`, `test_execute_action_dispatches_to_tool_save_market_intelligence()`
    - `TestFullEventProbabilityEndToEndIntegration`
      - *Methods*: `test_full_pipeline_flow()`

**File:** `tests/test_m2_empirical_stress.py`
  - **Classes**:
    - `TestSubagentSpawnerStress`
      - *Methods*: `test_worker_macro_empty_available_tools()`, `test_worker_macro_malformed_available_tools()`, `test_worker_macro_all_15_macro_tools_assigned()`, `test_worker_macro_powerset_target_tools()`, `test_worker_macro_strict_domain_isolation()`, `test_worker_macro_duplicate_tools_handling()`, `test_worker_macro_across_pool_configurations()`, `test_worker_macro_system_prompt_checklist_immutability()`, `test_cross_asset_specialist_receives_treasury_yields()`, `test_subagent_pool_concurrency_stress_oracle()`
    - `TestFedWatchProbabilitiesStress`
      - *Methods*: `test_fedwatch_fallback_under_null_session_states()`, `test_fedwatch_empty_database_fallback()`, `test_fedwatch_valid_database_rows_and_limit()`, `test_fedwatch_malformed_json_resilience()`, `test_fedwatch_deduplication_keeps_latest_snapshot()`, `test_fedwatch_timezone_naive_and_aware_support()`
    - `TestEndToEndRoutingAndMacroIntegration`
      - *Methods*: `test_contoh_pertanyaan_end_to_end_worker_macro_pipeline()`, `test_fedwatch_null_session_resilience_under_extreme_limits()`

**File:** `tests/test_telegram_vintage_formatter.py`
  - **Functions**:
    - `test_make_header_and_footer()`
    - `test_format_status_slip()`
    - `test_format_positions_slip_empty()`
    - `test_format_positions_slip_with_items()`
    - `test_format_risk_slip()`
    - `test_format_stats_slip()`
    - `test_format_alert_slip()`
    - `test_format_help_slip()`

**File:** `tests/test_audit_round3_remediation.py`
  - **Docstring**: Comprehensive unit tests for Code Consistency Audit Round 3 remediations.
  - **Classes**:
    - `TestIndicatorsRemediation`
      - *Methods*: `test_technical_order_flow_snapshot_timestamp()`, `test_timesfm_engine_scalar_baseline_atr()`, `test_order_flow_snapshot_vpin_field()`, `test_microstructure_nan_guards()`, `test_structure_fvg_max_distance_and_div_zero_guard()`
    - `TestBacktestRemediation`
      - *Methods*: `test_outcome_evaluator_oil_contract_sizes()`, `test_outcome_evaluator_friday_profit_only_close()`, `test_alpha_validation_sortino_and_equity_curve_normalization()`, `test_monte_carlo_engine_final_equity_distribution_key()`, `test_report_generator_final_equity_set()`, `test_point_in_time_engine_canonical_universe()`
    - `TestDataSourcesRemediation`
      - *Methods*: `test_validators_intraday_cache_expired_string_parsing()`, `test_dxy_yfinance_get_latest()`
    - `TestCLIBenchmarkScrapersSkillsRemediation`
      - *Methods*: `test_benchmark_judge_score_null_handling()`, `test_benchmark_deterministic_boolean_init()`, `test_skills_loader_prefix_and_deduplication()`, `test_cli_theme_persist_preserves_comments()`, `test_rss_base_scraper_no_raise_and_ua()`, `test_scrapers_calendar_country_and_aliases()`





**File:** `tests/deploy/test_deployment_configs.py`
  - **Docstring**: Comprehensive validation test suite for VPS deployment files (docker-compose.vps.yml, Dockerfile.mt5-wine, entrypoint_mt5.sh, vps_deployment_guide.md).
  - **Functions**:
    - `test_docker_compose_syntax_and_services()`
    - `test_dockerfile_mt5_wine_stages()`
    - `test_entrypoint_mt5_structure()`
    - `test_deployment_guide_contents()`

#### Folder: `trading-agent/utils`

**File:** `__init__.py`
  - **Variables**: `__all__`

**File:** `chart_generator.py`
  - **Global Variables**: `logger`, `DARK_STYLE`
  - **Functions**:
    - `generate_candlestick_chart(ohlcv_rows, symbol, timeframe, show_volume, show_ma, indicators)` -> `io.BytesIO`
      - *Docstring*: Headless dark-themed PNG candlestick chart generator for Telegram Bot dispatches.
    - `generate_candlestick_chart_async(ohlcv_rows, symbol, timeframe, show_volume, show_ma, indicators)` -> `io.BytesIO`
      - *Docstring*: Non-blocking asynchronous wrapper dispatching chart rendering to a dedicated background thread.

**File:** `clock.py`
  - **Functions**: `now`, `set_simulated_now`, `get_simulated_now`, `is_simulated`, `utc_now_iso`, `frozen_time`, `async_frozen_time`

**File:** `constants.py`
  - **Global Variables**: `MARKET_OUTCOME_EXIT_REASONS`, `NON_MARKET_EXIT_REASONS`, `AI_MAGIC_NUMBER`, `CLAUDE_MAGIC_NUMBER`, `ANALYSIS_TIMEFRAMES`, `H4_DATA_MAX_AGE_HOURS`, `D1_DATA_MAX_AGE_HOURS`

**File:** `retry_decorator.py`
  - **Docstring**: Retry decorator with exponential backoff and jitter for transient failures.
  - **Global Variables**: `logger`, `F`
  - **Functions**: `retryable`, `_calculate_delay`

**File:** `turn_marker.py`
  - **Docstring**: Atomic file-based turn marker manager for crash recovery, in-flight state tracking, and session resumption.
  - **Classes**: `TurnMarker`, `TurnMarkerManager`
    - *Methods*: `create_turn()`, `complete_turn()`, `check_unresolved_turn()`, `clean_stale_markers()`


##### Folder: `trading-agent/utils/analytics`
**File:** `adversarial_outcome_tracker.py`
**File:** `agent_performance_monitor.py`
**File:** `analysis_tracker.py`
  - **Functions**: `compute_analysis_quality_report(session: AsyncSession, days_back: int = 30) -> dict`, `get_adaptive_threshold_hints(session: AsyncSession) -> dict`, `get_per_asset_bias_report(session: AsyncSession, days_back: int = 14) -> dict`, `analyze_debate_impact(session: AsyncSession, days_back: int = 30) -> dict`, `compute_factor_effectiveness(session: AsyncSession, days_back: int = 60) -> dict`, `get_confluence_calibration_status(session: AsyncSession) -> dict`, `get_direction_accuracy_report(session: AsyncSession, days_back: int = 30) -> dict`, `detect_score_inflation(session: AsyncSession, days_back: int = 30) -> dict`, `compute_factor_weights_recommendation(session: AsyncSession, min_trades: int = 50) -> dict`, `compute_dynamic_factor_weights(session: AsyncSession) -> str`, `compute_model_source_performance(session: AsyncSession, days_back: int = 30) -> dict`, `compute_and_persist_factor_point_overrides(session: AsyncSession, min_trades: int = 30) -> dict`
**File:** `cds_outcome_tracker.py`
**File:** `cost_tracker.py`
  - **Classes**: `CostTracker`
    - *Methods*: `log_cycle_cost(session: AsyncSession, stage1_input: int, stage1_output: int, stage2_input: int, stage2_output: int, settings: dict = None, cycle_id: Optional[str] = None) -> float`, `check_and_update_budget_status(session: AsyncSession, settings: dict, history: list = None, latest_cost: float = 0.0) -> dict`, `_check_budget(session: AsyncSession, history: list, latest_cost: float, settings: dict) -> None`, `is_budget_paused_cached() -> bool`, `is_budget_paused(session: AsyncSession, settings: dict = None, force_recheck: bool = False) -> bool`, `clear_budget_pause(session: AsyncSession) -> None`, `get_rolling_7day_cost(session: AsyncSession) -> dict`
**File:** `models_dev_sync.py`
  - **Docstring**: Synchronizer for upstream dynamic LLM pricing data with ETag conditional caching.
  - **Classes**: `ModelsDevSync`
    - *Methods*: `get_cache_path()`, `load_cache()`, `save_cache()`, `sync_pricing()`, `get_model_pricing()`
**File:** `pricing.py`
  - **Data Classes**: `Price`, `PricingTier`
  - **Functions**: `infer_provider_from_model(model_name: str) -> str`, `is_free_tier(model_name: str, provider: Optional[str] = None, is_direct_free_tier: Optional[bool] = None) -> bool`, `get_price(model_name: str) -> Price`, `cost_usd(model_name: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0, provider: Optional[str] = None, is_direct_free_tier: Optional[bool] = None) -> float`, `estimate_cost`
  - **Global Variables**: `PRICING`, `OPENROUTER_PRICING_MAP`, `FREE_TIER_MODELS`, `_FREE`
**File:** `edge_tracker.py`
  - **Functions**: `binomial_confidence_interval(wins: int, total: int, confidence: float = 0.95)`, `is_trade_win(r) -> bool`, `compute_edge_status(session: AsyncSession) -> dict`
**File:** `news_classification_tracker.py`
**File:** `paper_tracker.py`
  - **Classes**: `PaperTracker`
    - *Methods*: `update_paper_trade_sl()`, `open_paper_trade()`, `check_and_close_trades()`, `get_statistics()`, `check_and_alert_winrate()`, `simulate_equity_curve()`, `get_suspended_symbols()`, `check_and_suspend_poor_performers()`, `unsuspend_symbol()`, `unsuspend_all()`, `get_streak_status()`, `should_regenerate_performance_notes()`
  - **Functions**: `_group_by_symbol(history)`, `_group_by_symbol_direction(history)`
**File:** `specialist_tracker.py`
**File:** `token_auditor.py`
  - **Classes**: `TokenAuditor`
    - *Methods*: `get_summary()`, `get_role_breakdown()`, `get_subsystem_breakdown()`, `get_symbol_breakdown()`, `get_provider_breakdown()`, `get_stage_and_slot_breakdown()`, `get_cache_performance_audit()`, `get_recent_logs()`, `get_cycle_cost_breakdown()`
**File:** `trade_autopsy.py`
**File:** `performance_reviewer.py`
  - **Functions**: `generate_fundamental_performance_review(session: AsyncSession) -> str`, `generate_weekly_review(session: AsyncSession, settings: dict) -> str`, `should_regenerate_fundamental_notes(session: AsyncSession) -> tuple[bool, str]`


##### Folder: `trading-agent/utils/calibration`
**File:** `cds_threshold_calibrator.py`
**File:** `confidence_calibrator.py`
**File:** `cot_thresholds.py`
**File:** `prescreen_calibrator.py`

##### Folder: `trading-agent/utils/protocol`
**File:** `__init__.py`
**File:** `brief_contamination_guard.py`
**File:** `coherence_flag_tracker.py`
**File:** `context_coherence.py`
**File:** `context_snapshot.py`
**File:** `cross_agent_sync.py`
**File:** `enhanced_cds.py`
**File:** `event_bus.py`
  - **Docstring**: Typed asynchronous EventBus with strongly-typed dataclasses, priority pub-sub, exception isolation, and buffered queue streaming.
  - **Classes**: `AppEvent`, `TickPriceEvent`, `BarClosedEvent`, `OrderStateChangedEvent`, `RiskBreachEvent`, `CircuitBreakerEvent`, `Subscription`, `EventBus`
    - *Methods*: `subscribe()`, `unsubscribe()`, `get_subscribers()`, `publish()`, `publish_nowait()`, `publish_threadsafe()`, `get_or_create_queue()`, `publish_buffered()`, `start_queue_worker()`, `stop_workers()`, `clear()`, `get_default_bus()`, `subscribe_default()`, `unsubscribe_default()`, `publish_default()`
  - **Functions**: `get_event_bus`, `reset_event_bus`
**File:** `ssvp_coordinator.py`

##### Folder: `trading-agent/utils/api`
**File:** `claude_rate_limiter.py`
  - **Classes**: `ClaudeRateLimiter`
    - *Methods*: `acquire_session_slot()`, `record_call()`, `get_current_rpm()`, `get_current_tpm()`
    - *Variables*: `MAX_REQUESTS_PER_MINUTE`, `MAX_TOKENS_PER_MINUTE`, `MIN_DELAY_BETWEEN_SESSIONS`
**File:** `credential_pool.py`
  - **Docstring**: Credential pool managing multi-key rotation, per-key health tracking, and circuit breaking.
  - **Classes**: `KeyHealth`, `APICredentialPool` (alias `CredentialPool`)
    - *Methods*: `get_healthy_key()`, `report_failure()`, `report_success()`, `get_status()`, `is_model_available()`
**File:** `groq_rate_limiter.py`
  - **Classes**: `GroqRateLimiter`
    - *Methods*: `try_acquire()`, `check_quota()`, `get_usage()`, `mark_cooldown()`, `reset()`, `_save_state()`, `_ensure_loaded()`
  - **Functions**: `get_api_keys`
  - **Variables**: `GROQ_QUOTA`, `DEFAULT_QUOTA`
**File:** `http_retry.py`
  - **Classes**: `RateLimitError`
  - **Functions**: `fetch_with_retry`, `_jittered_delay`, `_jitter_retry_after`
  - **Variables**: `_CIRCUIT_BREAKER`, `_DEFAULT_SSL_CONTEXT`
**File:** `openrouter_rate_limiter.py`
  - **Classes**: `OpenRouterRateLimiter`
    - *Methods*: `try_acquire()`, `check_quota()`, `get_usage()`, `mark_cooldown()`, `reset()`, `_save_state()`, `_ensure_loaded()`
  - **Functions**: `get_paid_key`, `get_free_keys`, `get_all_keys`, `is_free_tier_model`
  - **Variables**: `DEFAULT_FREE_QUOTA`, `DEFAULT_PAID_QUOTA`
**File:** `streaming.py`
  - **Classes**: `StreamTimeoutError`, `StreamSafetyTimeoutError`, `StreamConfig`, `StreamResult`, `StreamWriterFence`
  - **Functions**: `consume_sse_stream`, `streaming_request`

##### Folder: `trading-agent/utils/validation`
**File:** `data_temporal_validator.py`
**File:** `data_validator.py`
  - **Global Variables**: `DEFAULT_OHLCV_AGE`, `DEFAULT_IND_AGE`, `DEFAULT_MACRO_AGE_DAYS`
  - **Functions**: `is_crypto_symbol`, `is_forex_market_closed`, `is_market_reopen_window`, `validate_data_freshness`, `is_spread_acceptable`, `check_data_coherence`
**File:** `indicator_sanitizer.py`
  - **Functions**: `safe_float`
**File:** `tool_response_validator.py`

##### Folder: `trading-agent/utils/llm`
**File:** `adaptive_thinking.py`
  - **Classes**: `PerSymbolAdaptiveThinkingAllocator` (Methods: `compute_symbol_budget`, `get_thinking_level`, `get_thinking_budget_for_task`), `QuantizedThinkingAllocator` (Methods: `quantize`)
  - **Variables**: `ASSET_VOLATILITY_WEIGHTS`, `DEFAULT_WEIGHT`, `QUANTIZED_THINKING_BUCKETS`
**File:** `cache_miss_detector.py`
  - **Classes**: `CacheMissReport`, `CacheMissDetector`
  - **Variables**: `global_cache_miss_detector`
**File:** `constrained_sampling.py`
  - **Classes**: `ConstrainedSamplingConfig`
  - **Functions**: `make_strict_json_schema()`, `resolve_grammar_for_provider()`
**File:** `deferred_dispatcher.py`
  - **Classes**: `DispatchMode`, `DeferredRequest`, `DeferredResult`, `DeferredLLMDispatcher`
  - **Variables**: `global_deferred_dispatcher`
**File:** `cache_breakpoint_manager.py`
  - **Classes**: `CacheBreakpointManager` (Constants: `MIN_CACHEABLE_CHARS`, `GEMINI_3_MIN_CACHEABLE_CHARS`, `GEMINI_25_MIN_CACHEABLE_CHARS`, `CANONICAL_INVARIANT_RULES`, `CANONICAL_TIER0_ANCHOR`; Methods: `get_min_cacheable_chars`, `pad_system_prompt_to_threshold`, `wrap_system_tiers`, `apply_to_messages`, `find_completed_transaction_endpoints`, `wrap_classify_json` [padded anchor guarantee >= 1,024 tokens]). *Note*: Maintained as compatibility shim; structural context engine (PR-06) governs KV cache alignment.
**File:** `caveman_compressor.py`
  - **Variables**: `PRECISION_BY_SYMBOL`, `DEFAULT_PRECISION`
  - **Functions**: `_round_for_symbol`, `compress_tool_payload`
**File:** `context_compaction.py`
  - **Classes**: `ContextCompactionEngine` (Methods: `micro_prune`, `check_and_compact`, `compact_with_summary_model`, `mask_aged_observations`, `_extract_decisive_state` [expanded with optimal levels, sweeps, COT, macro], `check_tool_family_quota`, `_prune_ohlcv_output`)
  - **Variables**: `TOOL_FAMILIES`, `FAMILY_QUOTAS`, `DEFAULT_FAMILY_QUOTA`
  - **Functions**: `mask_aged_observations`
**File:** `context_tracker.py`
  - **Classes**: `ContextTracker` (Methods: `record_usage()`, `get_stats()`, `reset()`, `get_utilization()`, `get_context_summary()`, `get_history()`, `export_dict()`)
  - **Functions**: `get_global_context_tracker()`
**File:** `cycle_budget_guard.py`
  - **Classes**: `CycleBudgetGuard` (Methods: `from_settings`, `record`, `check`, `is_exceeded`, `get_stats`, `reset`)
  - **Functions**: `get_cycle_budget_guard`
  - **Variables**: `_global_guard`
**File:** `data_dedup.py`
  - **Docstring**: In-memory market data query deduplication ledger avoiding redundant tool fetches per cycle.
  - **Classes**: `DataFetchDeduplicator`
    - *Methods*: `make_key()`, `check()`, `record()`, `invalidate_on_compaction()`
**File:** `embedding.py`
  - **Docstring**: Gemini Embedding vector generation utility for semantic precedent retrieval and session search.
  - **Functions**: `generate_gemini_embedding()`
**File:** `memory_compressor.py`
**File:** `model_discipline.py`
  - **Docstring**: Model-family prompt discipline and verification rules injector.
  - **Variables**: `TOOL_USE_ENFORCEMENT_GUIDANCE`, `TRADING_VERIFICATION_GUIDANCE`
  - **Functions**: `get_model_discipline()`
**File:** `prompt_ab_test.py`
  - **Classes**: `PromptABTest` (Methods: `get_variant`, `get_variant_bandit`, `record_outcome`, `get_bandit_state`, `get_results`), `OfflinePromptOptimizer` (Methods: `score_variant_performance`, `select_champion`, `record_champion`)
**File:** `prompt_assembler.py`
  - **Classes**: `PromptAssembler` (Methods: `assemble_stage1_tiers`, `assemble_stage1_system_tuple`, `assemble_stage1`, `assemble_stage2_tiers`, `assemble_stage2_system_tuple`, `assemble_stage2`), `PromptSection`
  - **Functions**: `_flatten_system_prompt()`, `_split_memory()`, `compare_sections()`, `compose_ordered_prompt()`
  - **Global Variables**: `STAGE1_TIER1`, `STAGE2_TIER1`, `STAGE2_TIER1_TEMPLATE`, `MANDATORY_RULES`, `TIER2_TOOL_STUBS`, `SECTION_ORDERS`
**File:** `prompt_caching.py`
  - **Classes**: `PromptCacheController`
  - **Functions**: `get_cache_header()`, `apply_caching_breakpoint()`
**File:** `prompt_disciplines.py`
  - **Docstring**: Universal XML semantic prompt disciplines enforcing mandatory tool use, anti-mental arithmetic, literal preservation, parallel tool dispatch, and anti-laziness guardrails.
  - **Functions**: `get_universal_execution_discipline()`, `get_mandatory_tool_discipline()`, `get_literal_preservation_discipline()`, `get_anti_laziness_discipline()`
**File:** `prompt_compressor.py`
  - **Classes**: `ContextCompressor` (Methods: `compress_ohlcv` [regular stride subsampling], `compress_indicators`, `compress_stage1_dict`, `compress_stage1_bundle`, `compress_stage2_bundle`, `compress_stage2_dict`, `_prune_text_bundle_safely`)
  - **Functions**: `estimate_tokens`, `truncate_to_budget` (enhanced with Lossless Financial Structural Projection / LFSP: regular stride subsampling preserving unmitigated SMC zones, structural anchors, and high-impact calendar events)
**File:** `prompt_tiering.py`
  - **Classes**: `TieredPrompt`
  - **Functions**: `build_tiered_prompt()`
**File:** `prompt_tiers.py`
  - **Docstring**: Three-tier system prompt architecture designed for prompt cache stability and ephemeral prefix caching.
  - **Classes**: `PromptTier`, `TieredSystemPrompt`
    - *Methods*: `assemble()`, `compile_tuple()`
  - **Functions**: `get_ephemeral_overlay()`
**File:** `model_capabilities.py`
  - **Docstring**: Declarative model capability table for multi-provider LLM integration.
  - **Classes**: `ModelCapabilities`
  - **Functions**: `get_capabilities()`
  - **Global Variables**: `MODEL_CAPABILITIES`
**File:** `credential_pool.py`
  - **Docstring**: Multi-provider Credential Pooling and Automatic Rotation across all LLM providers.
  - **Classes**: `CredentialState`, `LLMCredentialPool` (alias `CredentialPool`)
    - *Methods*: `from_env()`, `get_key()`, `report_failure()`, `report_success()`, `get_status()`, `all_exhausted()`
**File:** `spill_subsystem.py`
  - **Classes**: `PostgresSpillSubsystem` (Methods: `maybe_spill`, `retrieve_spill`)
**File:** `tool_condenser.py`
  - **Classes**: `ToolObservationCondenser`
    - *Methods*: `condense_observation()`, `_extract_lfsp_projection()`, `_summarize_generic_tool()`

##### Folder: `trading-agent/utils/market`
**File:** `bias_utils.py`
  - **Docstring**: Centralized helper untuk normalisasi & perbandingan currency_bias (5-state to 3-state collapse).
  - **Functions**: `normalize_bias(bias: Optional[str]) -> str`, `bias_strength(bias: Optional[str]) -> float`, `normalize_currency_bias_dict(currency_bias: dict) -> dict`, `is_bullish(bias: Optional[str]) -> bool`, `is_bearish(bias: Optional[str]) -> bool`, `is_neutral(bias: Optional[str]) -> bool`
**File:** `brent_yfinance.py`
  - **Functions**: `get_brent_price`
**File:** `currency_utils.py`
  - **Docstring**: Utilitas pemetaan simbol instrumen trading ke mata uang terkait.
  - **Variables**: `SYMBOL_CURRENCIES`
  - **Functions**: `get_symbol_currencies(symbol)`
**File:** `direction.py`
  - **Docstring**: Market Direction Normalization Utility enforcing strict lowercase ('buy' | 'sell').
  - **Functions**: `normalize_direction(direction)`, `is_valid_direction(direction)`
**File:** `dynamic_correlation.py`
  - **Variables**: `STATIC_CORRELATION_FALLBACK`
  - **Functions**: `get_rolling_correlation(session, symbol1, symbol2, lookback_bars=60, as_of=None, method="ewma", span=30)`
**File:** `instrument_identity.py`
  - **Classes**: `InstrumentIdentity`, `InstrumentRegistry`
  - **Functions**: `resolve_instrument()`, `get_pip_multiplier()`
**File:** `news_impact_keywords.py`
  - **Variables**: `SHOCK_KEYWORDS` (tightened: single-word triggers replaced with multi-word specific phrases to reduce false BREAKING positives), `HIGH_IMPACT_KEYWORDS`, `DEESCALATION_KEYWORDS`, `REHASH_KEYWORDS`
**File:** `session_info.py`
  - **Docstring**: Market session tracking and timing rules utility.
  - **Functions**: `get_current_market_session(dt=None)`
**File:** `swap_estimator.py`
  - **Functions**: `estimate_swap_cost`
**File:** `usd_strength_proxy.py`
  - **Functions**: `compute_usd_strength_proxy`

##### Folder: `trading-agent/utils/plugins`
**File:** `__init__.py`
**File:** `extension_loader.py`
  - **Docstring**: Dynamic plugin extension loader importing external hooks from plugins directory.
  - **Functions**: `load_plugins()`, `load_single_plugin()`, `teardown_single_plugin()`
**File:** `manager.py`
  - **Docstring**: Lightweight Plugin & Extension Architecture with lifecycle hooks, filter pipelines, and dynamic tool registration.
  - **Classes**: `PluginManager` (methods: `register_hook()`, `unregister_hook()`, `emit()`, `apply_filter()`, `register_tool()`, `unregister_tool()`, `list_registered_tools()`, `clear()`), `PluginHook` (with `PRE_STAGE1`, `POST_STAGE1`, `PRE_STAGE2`, `POST_STAGE2`, `ON_TOOL_EXECUTION`, `ON_RISK_CHECK`), `BasePlugin` (methods: `setup()`, `teardown()`)
  - **Functions**: `get_plugin_manager()`

##### Folder: `trading-agent/utils/infra`
**File:** `audit_settings_keys.py`
**File:** `container.py`
  - **Docstring**: Lightweight service container supporting dependency injection and singleton lifecycle management.
  - **Classes**: `ServiceContainer`
    - *Methods*: `register()`, `resolve()`, `has()`, `clear()`
**File:** `db_backup.py`
**File:** `env_file_manager.py`
  - **Docstring**: Atomic, comment-preserving .env configuration file manager with schema-aware updates and configuration validation.
  - **Classes**: `EnvFileManager`
    - *Methods*: `load()`, `get()`, `update()`, `is_configured()`
**File:** `event_loop.py`
  - **Docstring**: Windows event loop configuration helper enforcing SelectorEventLoop on Python 3.14+.
  - **Functions**: `get_loop_factory()`, `run_async()`
**File:** `log_redactor.py`
  - **Docstring**: Logging redactor masking credentials, passwords, and sensitive tokens in stdout and log files.
  - **Classes**: `RedactingFormatter`
  - **Functions**: `redact_sensitive_text()`
  - **Variables**: `SENSITIVE_PATTERNS`
**File:** `notifier.py`
  - **Functions**: `get_notifier()`, `sanitize_telegram_html()`
  - **Classes**: `AgentNotifier`
    - *Methods*: `_send()`, `flush_outbox()`, `flush_outbox_loop()`, `send()`, `send_message()`, `send_alert()`, `send_critical()`, `send_warning()`, `send_info()`, `send_markdown()`, `send_cycle_summary()`
    - *Variables*: `_outbox`
**File:** `platform_compat.py`
  - **Docstring**: Universal cross-platform compatibility helper for Windows and Linux runtime environments.
  - **Variables**: `IS_WINDOWS`, `IS_LINUX`
  - **Functions**: `configure_event_loop()`, `safe_subprocess_run()`, `normalize_path()`

##### Folder: `trading-agent/utils/scheduling`
**File:** `wall_clock.py`
  - **Docstring**: Wall-clock scheduling helpers.
  - **Functions**:
    - `get_tzinfo(tz_name: str)`
    - `parse_time_list(times: Sequence[str]) -> list[dtime]`
    - `next_occurrence(times_local: Sequence[dtime], tz_name: str = 'Asia/Jakarta', now_utc: datetime | None = None) -> datetime`
    - `previous_occurrence(times_local: Sequence[dtime], tz_name: str = 'Asia/Jakarta', now_utc: datetime | None = None) -> datetime`
    - `sleep_until_next(times_local: Sequence[dtime], tz_name: str = 'Asia/Jakarta', label: str = 'task', shutdown_event: Optional[asyncio.Event] = None) -> datetime`

##### Folder: `trading-agent/utils/streaming`
**File:** `__init__.py`
**File:** `stream_scrubber.py`
  - **Docstring**: Stateful Stream Scrubber Pipeline buffering and scrubbing reasoning tokens (<think>...</think>), internal context tags, and secrets across streaming deltas.
  - **Classes**: `StatefulStreamScrubber`
    - *Methods*: `process_delta()`, `flush()`, `scrub_text()`, `_apply_redactions()`
    - *Properties*: `accumulated_thinking`
  - **Variables**: `SECRET_PATTERNS`, `STRIP_TAG_PAIRS`

##### Folder: `trading-agent/utils/security`
**File:** `__init__.py`
**File:** `threat_detector.py`
  - **Docstring**: Multi-scope content threat & prompt injection detector across all ingested surfaces.
  - **Classes**: `ThreatDetector`
    - *Methods*: `scan()`, `sanitize()`, `is_clean()`
  - **Variables**: `INJECTION_PATTERNS`, `EXFILTRATION_PATTERNS`, `INVISIBLE_CHARS`, `threat_detector`
**File:** `threat_scanner.py`
  - **Docstring**: Threat scanner and sanitization engine inspecting external tool content for prompt injections, role hijacking, and unauthorized trade manipulation.
  - **Classes**: `SecurityAction`, `ScanVerdict`
  - **Functions**: `scan_content()`, `sanitize_or_block()`
  - **Variables**: `SUSPICIOUS_PATTERNS`, `INJECTION_PATTERNS`, `TRADING_MANIPULATION_PATTERNS`

##### Folder: `trading-agent/utils/typesafe`
**File:** `__init__.py`
  - **Docstring**: TypeSafe & Jev System One Utilities.
**File:** `jev_primitives.py`
  - **Docstring**: TypeSafe Jev Primitives & Question Builders for Quantitative Trading Agent.
  - **Functions**:
    - `schema_to_jev_questions(schema: dict, base_prompt: str = "") -> dict`
    - `parse_jev_response_to_dict(response: SystemOneResponse, schema: Optional[dict] = None) -> dict`
    - `is_high_confidence(result: dict, min_confidence: float = 0.70) -> bool`
    - `build_news_classification_questions() -> dict`
    - `build_prescreen_questions(symbol: str) -> dict`
    - `build_shadow_check_questions() -> dict`
    - `build_adjudication_questions() -> dict`
    - `build_realtime_news_questions(open_positions: Optional[list] = None) -> dict`
    - `build_fundamental_verifier_questions() -> dict`
    - `build_news_classification_verify_questions() -> dict`
    - `build_digest_consistency_questions() -> dict`
    - `build_position_guard_questions(symbol: str, direction: str) -> dict`
    - `build_telegram_intent_questions() -> dict`
    - `build_risk_gate_neutral_questions(symbol: str, direction: str) -> dict`
    - `build_exit_review_prescreen(symbol: str, direction: str) -> dict`
    - `build_scenario_branch_questions(symbol: str) -> dict`
    - `build_adversarial_check_questions(symbol: str) -> dict`
    - `classify_news_batch_with_jev(client, batch, now_utc, calendar_priors, macro_context, min_confidence) -> Optional[list]`

##### Folder: `trading-agent/utils/storage`
**File:** `spill_store.py`
  - **Docstring**: Output Spill Store for Large Artifacts. Offloads oversized tool outputs, news transcripts, and raw order book data to disk, returning bounded head/tail previews to context to preserve LLM token budgets.
  - **Classes**: `SpillStore`
    - *Methods*: `generate_preview(text, max_chars, head_ratio)`, `spill_artifact(content, artifact_type, artifact_id, preview_chars)`, `load_artifact(artifact_id_or_path)`
  - **Functions**: `get_spill_store()`
  - **Variables**: `DEFAULT_SPILL_DIR`
