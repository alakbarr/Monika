# ==============================================================================
# File: application/analysis/tools/definitions/system.py
# ==============================================================================

"""
System diagnostics, code execution, skills, reports, terminal, and utility tool definitions.
"""

from __future__ import annotations

from monika.application.analysis.tools.definitions.base import _tool

GET_SYSTEM_HEALTH = _tool(
    name="get_system_health",
    description=(
        "Fetch comprehensive system health status: cycle scheduler status, last cycle run timestamp, "
        "risk circuit breaker / paused status, active scrapers health, MT5 connection status, and recent error count."
    ),
    properties={},
    required=[],
)


GET_TOKEN_USAGE_AND_COSTS = _tool(
    name="get_token_usage_and_costs",
    description=(
        "Fetch AI token consumption and estimated API costs for today and past days across models and task roles."
    ),
    properties={
        "days_back": {
            "type": "integer",
            "description": "Number of days back to report. Default: 1 (today).",
        },
    },
    required=[],
)


INSPECT_DATABASE_SCHEMA = _tool(
    name="inspect_database_schema",
    description=(
        "Inspect database tables and schema structure. Exclusively available to Admin. "
        "Returns list of all available tables in the database with their columns, primary keys, and types. "
        "Provide table_name to view detailed column definitions for a specific table, or omit to list all available tables."
    ),
    properties={
        "table_name": {
            "type": "string",
            "description": "Optional specific table name (e.g. 'system_config', 'positions', 'paper_trade_records', 'trade_triggers') to inspect in detail.",
        }
    },
    required=[],
)


READ_DATABASE_RECORDS = _tool(
    name="read_database_records",
    description=(
        "Query records from any database table. Exclusively available to Admin. "
        "Returns formatted records with sensitive fields masked. "
        "Supports equality filtering, sorting, pagination, and column selection. Read-only operation."
    ),
    properties={
        "table_name": {
            "type": "string",
            "description": "Name of the table to query (e.g. 'system_config', 'positions', 'paper_trade_records', 'trade_triggers').",
        },
        "filters": {
            "type": "object",
            "description": "Optional key-value equality filters, e.g. {'symbol': 'EURUSD', 'status': 'open'} or {'key': 'trailing_stop'}.",
        },
        "columns": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of column names to retrieve. If omitted, returns all columns.",
        },
        "order_by": {
            "type": "string",
            "description": "Optional column name to sort by, with optional 'asc' or 'desc', e.g. 'created_at desc' or 'id desc'.",
        },
        "limit": {"type": "integer", "description": "Maximum number of records to return (default 10, max 50)."},
        "offset": {"type": "integer", "description": "Number of records to skip for pagination (default 0)."},
    },
    required=["table_name"],
)


EXECUTE_ANALYSIS_CODE = _tool(
    name="execute_analysis_code",
    description=(
        "Execute a Python script to perform batch data operations efficiently. "
        "Use when you need to call multiple tools with similar parameters (e.g., "
        "fetching price history for 8 pairs, or computing indicators across timeframes). "
        "The script has access to a 'tools' object where you can call any registered tool "
        "as tools.tool_name(param=value). Print final results to stdout as JSON. "
        "This avoids multiple LLM round-trips for repetitive operations."
    ),
    properties={
        "code": {
            "type": "string",
            "description": "Python code to execute. Use tools.get_price_history(symbol='EURUSD', timeframe='H4') etc.",
        },
    },
    required=["code"],
)


RETRIEVE_SPILLED_CONTEXT = _tool(
    name="retrieve_spilled_context",
    description=(
        "Retrieve spilled tool observations or large context blobs from PostgreSQL or disk caches by blob_id. "
        "Supports pagination via offset/max_chars, line pagination via line_offset/line_limit, "
        "or search via grep_pattern."
    ),
    properties={
        "blob_id": {
            "type": "string",
            "description": "The blob pointer or identifier (e.g. 'spill_1234abcd' or 'db://spill/spill_1234abcd').",
        },
        "storage_key": {
            "type": "string",
            "description": "Backward-compatible alias for blob_id.",
        },
        "offset": {
            "type": "integer",
            "description": "Starting character offset for pagination (default 0).",
        },
        "max_chars": {
            "type": "integer",
            "description": "Maximum characters to retrieve (default 4000, max 15000).",
        },
        "grep_pattern": {
            "type": "string",
            "description": "Optional regex or substring pattern to search lines within the spilled content with surrounding context.",
        },
        "line_offset": {
            "type": "integer",
            "description": "Starting line offset (0-based) for line pagination.",
        },
        "line_limit": {
            "type": "integer",
            "description": "Maximum number of lines to retrieve when using line pagination (1-500).",
        },
    },
    required=["blob_id"],
)


DELEGATE_SPECIALIST_ANALYSIS = _tool(
    name="delegate_specialist_analysis",
    description=(
        "Delegate deep specialized analysis to an isolated subagent. "
        "The specialist runs with isolated context, avoiding parent history pollution, "
        "and returns a structured analytical summary. "
        "Roles: 'macro_specialist', 'technical_specialist', 'sentiment_specialist', 'risk_specialist'."
    ),
    properties={
        "specialist_role": {
            "type": "string",
            "enum": ["macro_specialist", "technical_specialist", "sentiment_specialist", "risk_specialist"],
            "description": "Specialist subagent role to execute.",
        },
        "task_prompt": {
            "type": "string",
            "description": "Concrete prompt detailing the specialized task to analyze.",
        },
        "symbol": {
            "type": "string",
            "description": "Optional trading instrument symbol (e.g. 'EURUSD', 'XAUUSD').",
        },
    },
    required=["specialist_role", "task_prompt"],
)


SKILLS_LIST_TOOL = _tool(
    name="skills_list",
    description=(
        "List all available institutional trading playbooks, analytical frameworks, and tactical skills. "
        "Returns skill names, categories, and concise capability summaries. "
        "Use this to discover specialized frameworks without prompt token bloat."
    ),
    properties={},
    required=[],
)


SKILL_VIEW_TOOL = _tool(
    name="skill_view",
    description=(
        "Retrieve and view the full content and operational guidelines of a specific trading skill or playbook by name. "
        "Available skills include: 'central_banks_framework', 'event_probability_playbook', 'smc_ict_playbook', "
        "'macro_analysis_framework', 'market_dynamics_framework', 'adjudication_framework', etc."
    ),
    properties={
        "skill_name": {
            "type": "string",
            "description": "Exact name of the skill or playbook to inspect (without .md extension).",
        }
    },
    required=["skill_name"],
)


CREATE_SKILL_TOOL = _tool(
    name="create_skill",
    description=(
        "Create, author, and register a new persistent trading skill or playbook markdown file in the system. "
        "Use when user asks to create a new skill, save an identified edge/pattern into a playbook, or distill learnings into a reusable skill."
    ),
    properties={
        "skill_name": {
            "type": "string",
            "description": "Identifier for the skill (e.g. 'gold_london_sweep_playbook', 'orderblock_reversal').",
        },
        "content": {
            "type": "string",
            "description": "Complete markdown instructions, entry/exit criteria, and rules for the skill.",
        },
        "category": {
            "type": "string",
            "description": "Category for the skill: 'trading', 'tactical', 'macro', 'technical', 'discipline'. Default: 'trading'.",
        },
        "description": {
            "type": "string",
            "description": "Short 1-sentence description or summary of the skill.",
        },
    },
    required=["skill_name", "content"],
)


MANAGE_CRON = _tool(
    name="manage_cron",
    description=(
        "Schedules, lists, or removes dynamic recurring cron tasks or reminders. "
        "Use when the operator asks to schedule a recurring scan, report, or reminder."
    ),
    properties={
        "action": {"type": "string", "enum": ["add", "list", "remove", "clear"], "description": "Action to perform"},
        "name": {"type": "string", "description": "Unique identifier name for the cron job."},
        "cron_expression": {
            "type": "string",
            "description": "Standard 5-part cron expression (e.g. '0 9 * * 1-5', '*/30 * * * *').",
        },
        "instruction": {"type": "string", "description": "The command, prompt, or instruction to execute on schedule."},
        "description": {"type": "string", "description": "Optional memo/description."},
    },
    required=["action"],
)


TRIGGER_LEARNING_CYCLE = _tool(
    name="trigger_learning_cycle",
    description=(
        "Trigger the system self-reflection and learning loop: reviews recent closed trades, identifies error patterns, "
        "synthesizes negative constraints, and updates institutional playbooks."
    ),
    properties={
        "days_back": {"type": "integer", "description": "Lookback days for reflection (default: 7)."},
    },
    required=[],
)


RUN_SYSTEM_DOCTOR_CHECK = _tool(
    name="run_system_doctor_check",
    description=(
        "Run comprehensive system doctor diagnostic check verifying directories, API keys, MT5 terminal bridge, database tables, and scrapers."
    ),
    properties={
        "live_probes": {
            "type": "boolean",
            "description": "Whether to perform live network/broker probes (APIs, MT5, Redis). Default: false (offline diagnostic).",
        }
    },
    required=[],
)


EXPORT_HISTORICAL_DATA_CSV = _tool(
    name="export_historical_data_csv",
    description=(
        "Export historical OHLCV candle data to a CSV file on disk for external backtesting and quant research."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading pair symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "timeframe": {"type": "string", "description": "Candle timeframe ('M15', 'H1', 'H4', 'D1'). Default: 'H1'."},
        "days_back": {"type": "integer", "description": "Number of days of historical data to export (default: 30)."},
        "output_filename": {"type": "string", "description": "Optional custom filename for the CSV."},
    },
    required=["symbol"],
)


TRIGGER_MARKET_SCAN = _tool(
    name="trigger_market_scan",
    description=(
        "Trigger ad-hoc market opportunity scan across symbols and return top ranked trade recommendations based on current market regime and macro conditions."
    ),
    properties={
        "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of symbols to scan. Defaults to active asset universe.",
        },
        "force": {"type": "boolean", "description": "Force fresh scan even if cached brief exists."},
    },
    required=[],
)


RUN_STRATEGY_BACKTEST = _tool(
    name="run_strategy_backtest",
    description=(
        "Run isolated point-in-time strategy backtest on historical OHLCV data. "
        "Returns: total trades, win rate %, profit factor, Sharpe ratio, Sortino ratio, max drawdown %, and sample trade list."
    ),
    properties={
        "symbol": {"type": "string", "description": "Symbol to test (e.g. 'EURUSD', 'XAUUSD', 'BTCUSD')."},
        "timeframe": {"type": "string", "description": "Timeframe ('H1', 'H4', 'M15'). Default: 'H1'."},
        "strategy": {
            "type": "string",
            "description": "Strategy name (e.g. 'smc_fvg', 'btc_donchian_breakout', 'gap_fade', 'xau_trend', 'tsm_momentum', 'tri_convergent').",
        },
        "days_back": {"type": "integer", "description": "Lookback historical window in days (default: 90)."},
    },
    required=["symbol"],
)


GET_PNL_SUMMARY = _tool(
    name="get_pnl_summary",
    description=(
        "Retrieve aggregated profit/loss summary for real and paper trades across horizons: "
        "today, this week (Monday to now), this month, and all-time. "
        "Includes total PnL ($), trade counts, win rate %, and win/loss breakdown."
    ),
    properties={
        "horizons": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of horizons to query (e.g. ['today', 'this_week', 'this_month']). Defaults to all.",
        },
    },
    required=[],
)


RUN_ADHOC_SYMBOL_DEBATE = _tool(
    name="run_adhoc_symbol_debate",
    description=(
        "Trigger an ad-hoc Multi-Agent Debate session (Bull Specialist vs Bear Specialist vs Investment Judge) "
        "for a specific symbol to evaluate conflicting structural, fundamental, and quantitative evidence."
    ),
    properties={
        "symbol": {"type": "string", "description": "The asset symbol to debate (e.g. 'XAUUSD', 'EURUSD', 'BTCUSD')."},
    },
    required=["symbol"],
)


RUN_HOSTILE_STRESS_TEST = _tool(
    name="run_hostile_stress_test",
    description=(
        "Run Hostile Market Feed Wire Probes and RiskGate adversarial stress testing battery "
        "(flash crashes, spread blowouts, crossed book, stale feeds, zero-liquidity) to verify fail-closed protection."
    ),
    properties={
        "symbol": {"type": "string", "description": "Trading asset symbol to probe (default: 'EURUSD')."},
    },
    required=[],
)


RUN_ANALYTICAL_QUERY = _tool(
    name="run_analytical_query",
    description=(
        "Execute safe, parameterized analytical aggregation query on historical trade performance, "
        "regime expectancy, holding times, session win-rates, MAE/MFE distribution, and slippage. "
        "Use this for post-mortems, institutional performance auditing, and statistical breakdowns."
    ),
    properties={
        "metric": {
            "type": "string",
            "enum": [
                "win_rate",
                "profit_factor",
                "sharpe_ratio",
                "expectancy_usd",
                "mae_mfe_distribution",
                "holding_time",
                "rejection_summary",
                "slippage_summary",
                "overview",
            ],
            "description": "Metric to calculate (default: 'overview').",
        },
        "group_by": {
            "type": "string",
            "enum": [
                "session",
                "market_regime",
                "symbol",
                "decision_source",
                "risk_reward_bucket",
                "hour",
                "hour_wib",
                "hour_utc",
                "none",
            ],
            "description": "Grouping dimension (e.g. 'session', 'market_regime', 'hour', 'hour_wib').",
        },
        "days_back": {
            "type": "integer",
            "description": "Lookback window in days (default: 90).",
        },
        "symbol": {
            "type": "string",
            "description": "Optional symbol filter (e.g. 'XAUUSD', 'EURUSD').",
        },
        "min_rr": {
            "type": "number",
            "description": "Optional minimum risk-to-reward ratio filter (e.g. 2.0, 2.5).",
        },
    },
    required=["metric"],
)


EXPORT_TRADES_TO_EXCEL = _tool(
    name="export_trades_to_excel",
    description="Export completed trade history, holding durations, commissions, and PnL to formatted Excel (.xlsx) file.",
    properties={
        "limit": {"type": "integer", "description": "Maximum number of recent trades to export (default: 200)."},
        "filename": {
            "type": "string",
            "description": "Optional output Excel filename (default: trades_export_<timestamp>.xlsx).",
        },
    },
    required=[],
)


GENERATE_DOCX_REPORT = _tool(
    name="generate_docx_report",
    description="Generate institutional Word (.docx) performance report with quantitative tables, risk metrics, and LLM narrative.",
    properties={
        "title": {"type": "string", "description": "Report title header."},
        "narrative": {"type": "string", "description": "Comprehensive LLM executive narrative synthesis."},
        "filename": {"type": "string", "description": "Optional output filename."},
    },
    required=[],
)


GENERATE_PPTX_DECK = _tool(
    name="generate_pptx_deck",
    description="Generate PowerPoint (.pptx) presentation pitch deck covering multi-agent trading performance and architecture.",
    properties={
        "title": {"type": "string", "description": "Title of presentation deck."},
        "subtitle": {"type": "string", "description": "Subtitle on title slide."},
        "filename": {"type": "string", "description": "Optional output filename."},
    },
    required=[],
)


GENERATE_TEARSHEET_REPORT = _tool(
    name="generate_tearsheet_report",
    description="Generate institutional HTML / PDF performance tearsheet from trading record database.",
    properties={
        "format": {"type": "string", "enum": ["html", "pdf"], "description": "Output format ('html' or 'pdf')."},
        "title": {"type": "string", "description": "Title header for tearsheet."},
    },
    required=[],
)


EXPORT_DATASET_FILE = _tool(
    name="export_dataset_file",
    description="Export database records (paper_trades, asset_analyses, chronicle) to CSV or Apache Parquet file for quantitative analysis.",
    properties={
        "table_name": {
            "type": "string",
            "enum": ["paper_trades", "asset_analyses", "chronicle"],
            "description": "Target database table.",
        },
        "format": {"type": "string", "enum": ["csv", "parquet"], "description": "File format ('csv' or 'parquet')."},
    },
    required=["table_name"],
)


RUN_WALK_FORWARD_ANALYSIS = _tool(
    name="run_walk_forward_analysis",
    description="Run Walk-Forward Analysis (WFA) on trading strategy to evaluate out-of-sample statistical robustness.",
    properties={
        "symbol": {"type": "string", "description": "Trading asset symbol (e.g. 'EURUSD', 'BTCUSD')."},
        "strategy": {"type": "string", "description": "Strategy name to backtest."},
        "n_folds": {"type": "integer", "description": "Number of walk-forward rolling folds (default: 4)."},
    },
    required=["symbol"],
)


RUN_PARAMETER_PLATEAU_OPTIMIZATION = _tool(
    name="run_parameter_plateau_optimization",
    description="Run Parameter Flat Plateau Optimization to find robust, curve-fitting-resistant parameter regions.",
    properties={
        "symbol": {"type": "string", "description": "Trading asset symbol (e.g. 'EURUSD')."},
        "n_trials": {"type": "integer", "description": "Number of optimization trials (default: 25)."},
    },
    required=["symbol"],
)


GET_GRADUATION_STATUS_TOOL = _tool(
    name="get_graduation_status",
    description="Evaluate trader's paper trading graduation progress toward live qualification (trades count, win rate, profit factor, max drawdown).",
    properties={},
    required=[],
)


READ_SYSTEM_LOGS_TOOL = _tool(
    name="read_system_logs",
    description="Safely read recent system activity logs from monika.log with optional line count and query filter.",
    properties={
        "file_name": {"type": "string", "description": "Log file name (default 'monika.log')."},
        "lines": {"type": "integer", "description": "Number of lines to read (default 50, max 200)."},
        "filter_query": {"type": "string", "description": "Optional search term to filter log lines."},
    },
    required=[],
)


RESTART_MT5_SERVICE_TOOL = _tool(
    name="restart_mt5_service",
    description="Safely cycle and restart the MT5 connection/service bridge to recover from hangs or timeouts.",
    properties={
        "force": {
            "type": "boolean",
            "description": "Force reconnect even if currently reported as connected. Default: true.",
        },
        "reason": {"type": "string", "description": "Reason for restarting MT5 connection (for audit logs)."},
    },
    required=[],
)


UPDATE_CONFIG_PARAMETER_TOOL = _tool(
    name="update_config_parameter",
    description="Safely update a configuration parameter in settings.yaml using atomic writes (e.g. 'trading.risk.risk_per_trade_pct').",
    properties={
        "key": {
            "type": "string",
            "description": "Dot-separated configuration key path (e.g. 'trading.risk.risk_per_trade_pct' or 'paper_trading.enabled').",
        },
        "value": {"type": "string", "description": "New value to set (will be auto-cast to number, bool, or string)."},
        "reason": {"type": "string", "description": "Reason for the configuration change (for audit logs)."},
    },
    required=["key", "value"],
)


QUERY_DATABASE_SQL = _tool(
    name="query_database_sql",
    description="Execute read-only SELECT query directly on PostgreSQL database with safety guardrails and 50 row limit (Admin only).",
    properties={
        "sql": {
            "type": "string",
            "description": "Read-only SELECT SQL statement (e.g. 'SELECT * FROM paper_trade_records WHERE pnl_pct > 0 ORDER BY id DESC LIMIT 10')",
        }
    },
    required=["sql"],
)


CAPTURE_TERMINAL_SCREENSHOT = _tool(
    name="capture_terminal_screenshot",
    description="Captures live terminal/desktop screenshot or renders high-fidelity visual status card delivered directly to chat.",
    properties={},
    required=[],
)


GET_SERVER_TELEMETRY = _tool(
    name="get_server_telemetry",
    description="Retrieve live server hardware telemetry (CPU, RAM, disk space, host uptime, top background process PIDs).",
    properties={},
    required=[],
)


TERMINAL_TOOL = _tool(
    name="terminal",
    description="Execute command line shell commands in workspace environment or check background processes.",
    properties={
        "command": {"type": "string", "description": "The shell command string to execute."},
        "workdir": {"type": "string", "description": "Optional working directory."},
        "timeout": {"type": "number", "description": "Timeout in seconds (default 60)."},
        "background": {"type": "boolean", "description": "Run command asynchronously in background if True."},
    },
    required=["command"],
)


COMPUTER_USE_TOOL = _tool(
    name="computer_use",
    description="Interact with desktop GUI applications (MetaTrader 5 terminal) via screenshot, mouse clicks, keystrokes, and text typing.",
    properties={
        "action": {
            "type": "string",
            "enum": ["screenshot", "mouse_move", "left_click", "right_click", "type_text", "key_press"],
            "description": "GUI action to perform.",
        },
        "coordinate": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Screen [x, y] pixel coordinates for mouse action.",
        },
        "text": {"type": "string", "description": "Text to type into active window."},
        "key": {"type": "string", "description": "Key to press (e.g. 'enter', 'tab', 'f9', 'ctrl+s')."},
    },
    required=["action"],
)


BACKUP_DATABASE_TOOL = _tool(
    name="backup_database",
    description="Trigger an on-demand compressed PostgreSQL database backup via pg_dump to the backups/ directory (Admin only).",
    properties={
        "force": {
            "type": "boolean",
            "description": "Force backup even if automated backup is disabled in settings.yaml (default: true).",
        }
    },
    required=[],
)


COMPILE_MQL5_EA_TOOL = _tool(
    name="compile_mql5_ea",
    description="Compile an MQL5 source file (.mq5) into executable binary (.ex5) using metaeditor64.exe headless compiler.",
    properties={"source_path": {"type": "string", "description": "Path to the .mq5 source file to compile."}},
    required=["source_path"],
)


GET_MT5_BROKER_LOGS_TOOL = _tool(
    name="get_mt5_broker_logs",
    description="Read recent log entries from the MetaTrader 5 broker terminal text logs in the MT5 data directory.",
    properties={
        "lines": {"type": "integer", "description": "Number of recent lines to read (default 20)."},
        "date": {"type": "string", "description": "Optional log date in YYYYMMDD format (defaults to current date)."},
    },
    required=[],
)


GET_MT5_TERMINAL_INFO_TOOL = _tool(
    name="get_mt5_terminal_info",
    description="Inspect MetaTrader 5 terminal status, trade permissions (Algo Trading button status: Hijau vs Merah), and broker connection.",
    properties={},
    required=[],
)


GET_LATENCY_BREAKDOWN = _tool(
    name="get_latency_breakdown",
    description="Inspect internal system latency telemetry: MT5 order round-trip ping, SQLite/PostgreSQL query timings, and LLM inference response times.",
    properties={},
    required=[],
)


BROWSER_TOOL = _tool(
    name="browser",
    description="Headless/interactive DrissionPage web browser automation. Overcomes Cloudflare, anti-bot protections, JavaScript-rendered dashboards, and paywalls.",
    properties={
        "action": {
            "type": "string",
            "enum": ["open", "extract", "click", "type", "screenshot", "close"],
            "description": "Browser action to execute.",
        },
        "url": {"type": "string", "description": "Target webpage URL (required for 'open')."},
        "selector": {"type": "string", "description": "CSS selector or element text for extract, click, or type."},
        "text": {"type": "string", "description": "Text to input for 'type' action."},
    },
    required=["action"],
)


SAVE_SCRIPT = _tool(
    name="save_script",
    description="Save a custom Python analysis, backtest, or quantitative script to persistent storage (data/user_scripts/) for re-execution across sessions.",
    properties={
        "script_name": {
            "type": "string",
            "description": "Unique filename for the script (e.g. 'volatility_model.py').",
        },
        "code": {"type": "string", "description": "Executable Python code containing analysis logic."},
        "description": {"type": "string", "description": "Optional brief description of what the script does."},
    },
    required=["script_name", "code"],
)


LIST_SAVED_SCRIPTS = _tool(
    name="list_saved_scripts",
    description="List all persisted custom Python quantitative and backtest scripts saved in data/user_scripts/.",
    properties={},
    required=[],
)


RUN_SAVED_SCRIPT = _tool(
    name="run_saved_script",
    description="Execute a previously saved Python script from data/user_scripts/ in the sandboxed runtime and capture output.",
    properties={
        "script_name": {"type": "string", "description": "Name of the script to execute (e.g. 'volatility_model.py')."}
    },
    required=["script_name"],
)


RUN_WALK_FORWARD_OPTIMIZATION_TOOL = _tool(
    name="run_walk_forward_optimization",
    description="Run Walk-Forward Optimization across chronological folds with purge gaps and embargo to test for overfitting (Q102).",
    properties={
        "strategy": {"type": "string", "description": "Strategy identifier (e.g. 'smc_fvg', 'liquidity_sweep')."},
        "symbol": {"type": "string", "description": "Instrument symbol (e.g. 'EURUSD', 'XAUUSD')."},
        "n_folds": {"type": "integer", "description": "Number of rolling train/test folds (default: 4)."},
    },
    required=["strategy", "symbol"],
)


OPTIMIZE_STRATEGY_PARAMETERS_TOOL = _tool(
    name="optimize_strategy_parameters",
    description="Run a parameter grid-search backtest over a specified range to find optimal Profit Factor and Sharpe (Q111).",
    properties={
        "strategy": {"type": "string", "description": "Strategy name (e.g. 'smc_fvg')."},
        "symbol": {"type": "string", "description": "Instrument symbol (e.g. 'XAUUSD')."},
        "param_name": {"type": "string", "description": "Parameter name to optimize (e.g. 'atr_period')."},
        "min_val": {"type": "number", "description": "Starting parameter value."},
        "max_val": {"type": "number", "description": "Ending parameter value."},
        "step": {"type": "number", "description": "Step increment (default: 1)."},
    },
    required=["strategy", "symbol", "param_name", "min_val", "max_val"],
)


RUN_MODEL_BENCHMARK_TOOL = _tool(
    name="run_model_benchmark",
    description="Benchmark trading LLMs head-to-head via Alpha Arena Elo tournament on decision accuracy and latency (Q112).",
    properties={
        "models": {"type": "array", "items": {"type": "string"}, "description": "List of model IDs to test."},
        "rounds": {"type": "integer", "description": "Number of benchmark rounds (default: 3)."},
    },
    required=[],
)


EVALUATE_DEBATE_EFFICACY_TOOL = _tool(
    name="evaluate_debate_efficacy",
    description="Evaluate whether Bull vs Bear dialectical debate improved trade win rates and filtered out losing setups (Q140).",
    properties={"days_back": {"type": "integer", "description": "Lookback window in days (default: 90)."}},
    required=[],
)


TODO_WRITE = _tool(
    name="todo_write",
    description=(
        "Record and update a structured task checklist to plan multi-step work and track execution progress. "
        "Provide the complete list of tasks. While work remains, keep exactly one task 'in_progress'. "
        "Mark each task 'completed' as soon as its verification proof is obtained."
    ),
    properties={
        "todos": {
            "type": "array",
            "description": "The complete list of planned tasks.",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Clear imperative action item."},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "Current status of this task.",
                    },
                },
                "required": ["content", "status"],
            },
        }
    },
    required=["todos"],
)


__all__ = [
    "TODO_WRITE",
    "GET_SYSTEM_HEALTH",
    "GET_TOKEN_USAGE_AND_COSTS",
    "INSPECT_DATABASE_SCHEMA",
    "READ_DATABASE_RECORDS",
    "EXECUTE_ANALYSIS_CODE",
    "RETRIEVE_SPILLED_CONTEXT",
    "DELEGATE_SPECIALIST_ANALYSIS",
    "SKILLS_LIST_TOOL",
    "SKILL_VIEW_TOOL",
    "CREATE_SKILL_TOOL",
    "MANAGE_CRON",
    "TRIGGER_LEARNING_CYCLE",
    "RUN_SYSTEM_DOCTOR_CHECK",
    "EXPORT_HISTORICAL_DATA_CSV",
    "TRIGGER_MARKET_SCAN",
    "RUN_STRATEGY_BACKTEST",
    "GET_PNL_SUMMARY",
    "RUN_ADHOC_SYMBOL_DEBATE",
    "RUN_HOSTILE_STRESS_TEST",
    "RUN_ANALYTICAL_QUERY",
    "EXPORT_TRADES_TO_EXCEL",
    "GENERATE_DOCX_REPORT",
    "GENERATE_PPTX_DECK",
    "GENERATE_TEARSHEET_REPORT",
    "EXPORT_DATASET_FILE",
    "RUN_WALK_FORWARD_ANALYSIS",
    "RUN_PARAMETER_PLATEAU_OPTIMIZATION",
    "GET_GRADUATION_STATUS_TOOL",
    "READ_SYSTEM_LOGS_TOOL",
    "RESTART_MT5_SERVICE_TOOL",
    "UPDATE_CONFIG_PARAMETER_TOOL",
    "QUERY_DATABASE_SQL",
    "CAPTURE_TERMINAL_SCREENSHOT",
    "GET_SERVER_TELEMETRY",
    "TERMINAL_TOOL",
    "COMPUTER_USE_TOOL",
    "BACKUP_DATABASE_TOOL",
    "COMPILE_MQL5_EA_TOOL",
    "GET_MT5_BROKER_LOGS_TOOL",
    "GET_MT5_TERMINAL_INFO_TOOL",
    "GET_LATENCY_BREAKDOWN",
    "BROWSER_TOOL",
    "SAVE_SCRIPT",
    "LIST_SAVED_SCRIPTS",
    "RUN_SAVED_SCRIPT",
    "RUN_WALK_FORWARD_OPTIMIZATION_TOOL",
    "OPTIMIZE_STRATEGY_PARAMETERS_TOOL",
    "RUN_MODEL_BENCHMARK_TOOL",
    "EVALUATE_DEBATE_EFFICACY_TOOL",
]
