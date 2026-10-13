# ==============================================================================
# File: interfaces/cli/commands/parser.py
# ==============================================================================

"""
CLI Argument Parser and Subcommand Registration for Monika.
Provides fuzzy command suggestions and root argument configuration.
"""

import argparse
import difflib
import logging
import os
import re
import sys
from typing import List, NoReturn, Optional

logger = logging.getLogger("TradingAgent.CLI")

DEFAULT_API_URL = (
    os.environ.get("MONIKA_API_URL")
    or os.environ.get("TRADEAGENT_API_URL")
    or os.environ.get("DASHBOARD_URL")
    or "http://127.0.0.1:8000"
)


class MonikaArgumentParser(argparse.ArgumentParser):
    """Custom argument parser providing fuzzy suggestions for command typos."""

    def error(self, message: str) -> NoReturn:
        m = re.search(r"invalid choice:\s*'([^']+)'\s*\(choose from (.*?)\)", message)
        if m:
            typo = m.group(1)
            choices = [c.strip().strip("'") for c in m.group(2).split(",")]
            matches = difflib.get_close_matches(typo, choices, n=2, cutoff=0.5)
            suggestion = f"\nDid you mean: {', '.join(matches)}?" if matches else ""
            sys.stderr.write(
                f"monika: error: '{typo}' is not a valid command.{suggestion}\nRun 'python -m monika.interfaces.cli.main --help' to view all commands.\n"
            )
            sys.exit(2)
        super().error(message)


def parse_args(args_list: Optional[List[str]] = None) -> argparse.Namespace:
    parser = MonikaArgumentParser(description="AI Trading Agent CLI Interface")
    parser.add_argument(
        "-p",
        "--profile",
        type=str,
        default=None,
        help="Target isolated environment profile (e.g. paper, live, propfirm)",
    )
    parser.add_argument(
        "--no-daemon", action="store_true", default=False, help="Disable auto-spawning trading daemon if not running"
    )
    subparsers = parser.add_subparsers(dest="command", help="Administrative subcommands")

    # Command: run (default)
    run_parser = subparsers.add_parser("run", help="Start the trading agent daemon")
    run_parser.add_argument(
        "--mode", type=str, choices=["live", "paper"], default="paper", help="Trading execution mode"
    )
    run_parser.add_argument(
        "--confirm-live", action="store_true", default=False, help="Explicit acknowledgement for live trading mode"
    )
    run_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    # Command: status
    status_parser = subparsers.add_parser("status", help="Show system status, flags, and open positions")
    status_parser.add_argument(
        "--no-daemon", action="store_true", default=False, help="Disable auto-spawning trading daemon if not running"
    )

    # Command: pause
    subparsers.add_parser("pause", help="Pause all new trading proposals")

    # Command: resume
    resume_parser = subparsers.add_parser("resume", help="Resume trading (clears pause flags)")
    resume_parser.add_argument("-y", "--yes", action="store_true", help="Skip interactive confirmation")

    # Command: kill
    kill_parser = subparsers.add_parser("kill", help="Trigger emergency kill switch")
    kill_parser.add_argument("-y", "--yes", action="store_true", help="Skip interactive confirmation")

    # Command: stop
    stop_parser = subparsers.add_parser("stop", help="Stop the background trading daemon gracefully")
    stop_parser.add_argument(
        "-f", "--force", action="store_true", default=False, help="Force terminate daemon immediately"
    )
    stop_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")

    # Command: positions
    positions_parser = subparsers.add_parser("positions", help="List all open positions (real & paper)")
    positions_parser.add_argument(
        "--no-daemon", action="store_true", default=False, help="Disable auto-spawning trading daemon if not running"
    )

    # Command: unsuspend
    unsuspend_parser = subparsers.add_parser("unsuspend", help="Unsuspend symbols blocked by streak losses")
    unsuspend_parser.add_argument("--symbol", type=str, default=None, help="Specific symbol to unsuspend (e.g. EURUSD)")
    unsuspend_parser.add_argument("--all", action="store_true", default=False, help="Unsuspend all symbols")

    # Command: tui
    tui_parser = subparsers.add_parser("tui", help="Launch rich Textual terminal dashboard")
    tui_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    tui_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")
    tui_parser.add_argument("--refresh", type=int, default=5, help="Refresh interval in seconds")
    tui_parser.add_argument(
        "--theme",
        type=str,
        default=None,
        choices=["retro_vintage", "modern_dark", "high_contrast", "daylight"],
        help="TUI color theme",
    )
    tui_parser.add_argument(
        "--no-daemon", action="store_true", default=False, help="Disable auto-spawning trading daemon if not running"
    )

    # Command: chat
    chat_parser = subparsers.add_parser("chat", help="Interactive REPL chat with agent")
    chat_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    chat_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")
    chat_parser.add_argument("--session-id", type=str, default=None, help="Conversation session ID")
    chat_parser.add_argument(
        "--offline", action="store_true", default=False, help="Force direct local engine (bypasses API server)"
    )
    chat_parser.add_argument(
        "--model",
        type=str,
        default="auto",
        choices=["auto", "fast", "medium", "analyze", "research"],
        help="Model routing preference",
    )
    chat_parser.add_argument(
        "--no-daemon", action="store_true", default=False, help="Disable auto-spawning trading daemon if not running"
    )

    # Command: config
    config_parser = subparsers.add_parser("config", help="Inspect and update system configuration")
    config_sub = config_parser.add_subparsers(dest="config_action", help="Config actions: show, set")

    show_parser = config_sub.add_parser("show", help="Show current configuration or a specific section")
    show_parser.add_argument("section", nargs="?", default=None, help="Specific section path (e.g. trading.risk)")
    show_parser.add_argument("--json", action="store_true", default=False, help="Output in JSON format")
    show_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    show_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")
    show_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    set_parser = config_sub.add_parser(
        "set", help="Update configuration parameter (e.g. trading.risk.max_daily_drawdown_percent=4.0)"
    )
    set_parser.add_argument("assignments", nargs="+", help="One or more key=value assignments")
    set_parser.add_argument("--reason", type=str, default="Updated via CLI", help="Audit reason for config change")
    set_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    set_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")
    set_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    get_parser = config_sub.add_parser("get", help="Retrieve specific configuration parameter")
    get_parser.add_argument("key", type=str, help="Parameter key path (e.g. trading.risk.risk_percent_per_trade)")
    get_parser.add_argument("--raw", action="store_true", default=False, help="Show raw unmasked value")
    get_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    unset_parser = config_sub.add_parser("unset", help="Unset a configuration parameter")
    unset_parser.add_argument("key", type=str, help="Parameter key path to remove")
    unset_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    edit_parser = config_sub.add_parser(
        "edit", help="Open settings.yaml or plugin config in default editor and validate upon exit"
    )
    edit_parser.add_argument(
        "plugin_id",
        nargs="?",
        default=None,
        help="Optional plugin ID or name to edit specific plugin config (e.g. discord_alert)",
    )
    edit_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    # Command: onboarding
    subparsers.add_parser("onboarding", help="Launch trader personalization and risk style onboarding interview")

    # Command: sessions
    sessions_parser = subparsers.add_parser("sessions", help="List conversation sessions with metadata")
    sessions_parser.add_argument(
        "--source",
        type=str,
        choices=["all", "telegram", "dashboard", "cli"],
        default="all",
        help="Filter by conversation source",
    )
    sessions_parser.add_argument("--limit", type=int, default=20, help="Max sessions to display")
    sessions_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    sessions_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")

    # Command: logs
    logs_parser = subparsers.add_parser("logs", help="Stream activity logs (tail -f style)")
    logs_parser.add_argument("-n", "--lines", type=int, default=20, help="Initial number of log lines to show")
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", default=False, help="Follow log output in real time"
    )
    logs_parser.add_argument(
        "--category", type=str, default=None, help="Filter by category (e.g. trading, risk, system, analysis)"
    )
    logs_parser.add_argument(
        "--level", "--severity", dest="severity", type=str, default=None, help="Filter by severity"
    )
    logs_parser.add_argument("--url", type=str, default=DEFAULT_API_URL, help="Dashboard API base URL")
    logs_parser.add_argument("--token", type=str, default=None, help="Dashboard API key")

    # Command: doctor
    doctor_parser = subparsers.add_parser("doctor", help="Run comprehensive system diagnostics with optional auto-fix")
    doctor_parser.add_argument(
        "--fix", action="store_true", default=False, help="Attempt to auto-fix recoverable issues"
    )
    doctor_parser.add_argument(
        "--offline", action="store_true", default=False, help="Skip live database and model connection probes"
    )
    doctor_parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Perform deep realtime probes including WAL integrity and API latency benchmark",
    )
    doctor_parser.add_argument(
        "-v", "--verbose", action="store_true", default=False, help="Show verbose diagnostic details"
    )

    # Command: setup
    setup_parser = subparsers.add_parser("setup", help="Launch interactive onboarding setup wizard")
    setup_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")
    setup_parser.add_argument(
        "--section",
        type=str,
        choices=["all", "mt5", "db", "llm", "risk"],
        default="all",
        help="Configure specific section only",
    )
    setup_parser.add_argument("--quick", action="store_true", default=False, help="Quick setup with sensible defaults")

    # Command: profile
    profile_parser = subparsers.add_parser("profile", help="Manage isolated trading environments and profiles")
    prof_sub = profile_parser.add_subparsers(
        dest="profile_action", help="Profile actions: list, use, create, delete, export, import"
    )
    prof_sub.add_parser("list", help="List all trading profiles")
    use_p = prof_sub.add_parser("use", help="Switch active profile")
    use_p.add_argument("name", type=str, help="Name of the profile to activate")
    create_p = prof_sub.add_parser("create", help="Create new isolated profile")
    create_p.add_argument("name", type=str, help="Name of the new profile")
    create_p.add_argument("--clone", type=str, default=None, help="Optional source profile to clone configuration from")
    del_p = prof_sub.add_parser("delete", help="Delete an isolated profile")
    del_p.add_argument("name", type=str, help="Name of the profile to delete")
    exp_p = prof_sub.add_parser("export", help="Export profile to zip archive")
    exp_p.add_argument("name", type=str, help="Name of the profile to export")
    exp_p.add_argument("zip_path", type=str, help="Output path for zip archive")
    imp_p = prof_sub.add_parser("import", help="Import profile from zip archive")
    imp_p.add_argument("zip_path", type=str, help="Path to zip archive")
    imp_p.add_argument("--name", type=str, default=None, help="Optional new profile name")

    # Command: ask (one-shot question to agent)
    ask_parser = subparsers.add_parser("ask", help="Send a single question or command to Monika chat agent")
    ask_parser.add_argument("question", nargs="*", type=str, help="Question or instruction for Monika")
    ask_parser.add_argument(
        "-r", "--raw", action="store_true", default=False, help="Print raw response without Rich styling or stamps"
    )
    ask_parser.add_argument(
        "--output-json", type=str, default=None, help="Save query result and proposal metadata to JSON file"
    )

    # Command: analyze (one-shot ad-hoc analysis for symbol)
    analyze_parser = subparsers.add_parser("analyze", help="Trigger ad-hoc multi-timeframe analysis for a symbol")
    analyze_parser.add_argument("symbol", type=str, help="Symbol to analyze (e.g. EURUSD, XAUUSD)")
    analyze_parser.add_argument("--context", type=str, default="", help="Optional custom analytical context")

    # Command: backtest (historical simulation and walk-forward analysis)
    backtest_parser = subparsers.add_parser("backtest", help="Run historical backtest or walk-forward analysis")
    backtest_parser.add_argument("--days", type=int, default=30, help="Lookback days from today (default: 30)")
    backtest_parser.add_argument("--start", type=str, default=None, help="Start date (YYYY-MM-DD)")
    backtest_parser.add_argument("--end", type=str, default=None, help="End date (YYYY-MM-DD)")
    backtest_parser.add_argument(
        "--mode",
        type=str,
        choices=["full", "replay", "walk_forward", "langgraph_parity"],
        default="full",
        help="Simulation mode",
    )
    backtest_parser.add_argument("--equity", type=float, default=10000.0, help="Initial account equity in USD")
    backtest_parser.add_argument(
        "--is-days", dest="is_days", type=int, default=90, help="Walk-forward In-Sample window days"
    )
    backtest_parser.add_argument(
        "--oos-days", dest="oos_days", type=int, default=30, help="Walk-forward Out-of-Sample window days"
    )
    backtest_parser.add_argument(
        "--symbol", type=str, default=None, help="Filter simulation to a specific symbol (e.g. XAUUSD)"
    )
    backtest_parser.add_argument(
        "--strategy", type=str, default=None, help="Filter simulation to a specific strategy (e.g. xau_trend_engine)"
    )

    # Command: mcp-serve (Launch Model Context Protocol server)
    mcp_parser = subparsers.add_parser(
        "mcp-serve", help="Launch Monika as a Model Context Protocol (MCP) server over stdio"
    )
    mcp_parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    # Command: plugin (Manage Monika plugins)
    plugin_parser = subparsers.add_parser("plugin", help="Manage plugins: list, install, uninstall, info")
    plugin_sub = plugin_parser.add_subparsers(
        dest="plugin_action", help="Plugin actions: list, install, uninstall, info"
    )
    plugin_sub.add_parser("list", help="List all detected plugins")
    inst_p = plugin_sub.add_parser("install", help="Install plugin package via pip")
    inst_p.add_argument(
        "package_name", type=str, help="Package name to install (e.g. discord or monika-plugin-discord)"
    )
    uninst_p = plugin_sub.add_parser("uninstall", help="Uninstall plugin package via pip")
    uninst_p.add_argument("package_name", type=str, help="Package name to uninstall")
    info_p = plugin_sub.add_parser("info", help="Show plugin metadata and configuration")
    info_p.add_argument("package_name", type=str, help="Plugin ID")
    enable_p = plugin_sub.add_parser("enable", help="Enable a plugin by ID")
    enable_p.add_argument("plugin_name", type=str, help="Plugin identifier to enable")
    disable_p = plugin_sub.add_parser("disable", help="Disable a plugin by ID")
    disable_p.add_argument("plugin_name", type=str, help="Plugin identifier to disable")

    # Command: benchmark (LLM Model Evaluation and Leaderboards)
    bench_parser = subparsers.add_parser("benchmark", help="Evaluate LLM models, test tiers, and inspect leaderboards")
    bench_sub = bench_parser.add_subparsers(
        dest="bench_action", help="Benchmark actions: run, leaderboard, history, tasks, models"
    )

    brun_p = bench_sub.add_parser("run", help="Execute benchmark evaluation across models and tasks")
    brun_p.add_argument("--tasks", nargs="*", default=None, help="Subset task IDs")
    brun_p.add_argument("--models", nargs="*", default=None, help="Subset model IDs")
    brun_p.add_argument(
        "--tier",
        choices=["system_one", "cheap_efficient", "cheap_smart", "high_intelligence"],
        default=None,
        help="Model tier filter",
    )
    brun_p.add_argument(
        "--mode",
        choices=["standard", "arena"],
        default="standard",
        help="Benchmark execution mode: standard or arena (Alpha Arena Tournament)",
    )
    brun_p.add_argument(
        "--use-fixtures", action="store_true", default=False, help="Use synthetic Sept 2026 market fixtures"
    )
    brun_p.add_argument(
        "--compare-routers", action="store_true", default=False, help="Compare direct provider vs OpenRouter vs 9router"
    )
    brun_p.add_argument("--symbols", nargs="*", default=None, help="Symbols for per-asset analysis")
    brun_p.add_argument("--judge-model", default=None, help="Judge model name")
    brun_p.add_argument("--reference-model", default=None, help="Reference model name")
    brun_p.add_argument("--concurrency", type=int, default=4, help="Async concurrency")
    brun_p.add_argument("--output", default="benchmark_report.md", help="Output report markdown path")

    blead_p = bench_sub.add_parser("leaderboard", help="Show aggregated model leaderboard")
    blead_p.add_argument("--run-id", type=int, default=None, help="Specific benchmark run ID (default: latest)")

    bhist_p = bench_sub.add_parser("history", help="Show historical benchmark runs")
    bhist_p.add_argument("--limit", type=int, default=15, help="Number of past runs to display")

    bench_sub.add_parser("tasks", help="List all 45 evaluation tasks and categories")
    bench_sub.add_parser("models", help="List candidate models, tiers, and router matrix")

    # Command: stress-test
    stress_parser = subparsers.add_parser(
        "stress-test",
        aliases=["stresstest"],
        help="Run adversarial hostile market probe battery to test fail-closed risk invariants",
    )
    stress_parser.add_argument("--symbol", type=str, default="EURUSD", help="Symbol to probe (default: EURUSD)")
    stress_parser.add_argument("--price", type=float, default=1.0850, help="Baseline reference price (default: 1.0850)")

    # Command: backup
    backup_parser = subparsers.add_parser("backup", help="Create database backup snapshot")
    backup_parser.add_argument("--dest", type=str, default=None, help="Custom destination folder")
    backup_parser.add_argument(
        "--force", action="store_true", default=False, help="Force backup even if disabled in config"
    )

    # Modular subcommands registry
    try:
        from monika.interfaces.cli.subcommands import AVAILABLE_SUBCOMMANDS

        for sc in AVAILABLE_SUBCOMMANDS:
            if sc.name and sc.name not in subparsers.choices:
                sc.register_subparser(subparsers)
    except Exception as e:
        logger.debug(f"Subcommands registration error: {e}")

    # Backward compatibility and top-level headless query flag
    parser.add_argument(
        "-q", "--query", type=str, default=None, help="Execute single one-shot query to Monika and exit"
    )
    parser.add_argument("-r", "--raw", action="store_true", default=False, help="Print raw response without formatting")
    parser.add_argument("--output-json", type=str, default=None, help="Save one-shot query result to JSON file")
    parser.add_argument("--mode", type=str, choices=["live", "paper"], default="paper", help="Trading execution mode")
    parser.add_argument(
        "--confirm-live", action="store_true", default=False, help="Explicit acknowledgement for live trading mode"
    )
    parser.add_argument("--config", type=str, default=None, help="Optional custom path to settings.yaml")

    parsed = parser.parse_args(args_list)

    # Intercept root-level -q / --query flag and redirect to 'ask' command
    if getattr(parsed, "query", None):
        parsed.command = "ask"
        parsed.question = [parsed.query]

    if getattr(parsed, "profile", None):
        from monika.interfaces.cli.profile_manager import ProfileManager

        pm = ProfileManager()
        pm.set_active_profile(parsed.profile)
        p_cfg = pm.get_settings_path_for_active()
        if p_cfg and not getattr(parsed, "config", None):
            parsed.config = p_cfg
        # Isolate MT5 common files directory per profile
        if os.environ.get("MT5_COMMON_FILES_PATH"):
            os.environ["MT5_COMMON_FILES_PATH"] = os.path.join(
                os.environ["MT5_COMMON_FILES_PATH"], "profiles", parsed.profile
            )

    if not parsed.command:
        parsed.command = "status"
    return parsed
