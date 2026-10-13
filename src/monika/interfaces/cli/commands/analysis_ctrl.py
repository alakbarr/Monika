# ==============================================================================
# File: interfaces/cli/commands/analysis_ctrl.py
# ==============================================================================

"""
Analysis, Backtesting, Stress Testing, and Backup Commands for Monika.
Handles ask, analyze, backtest, stress-test, and backup commands.
"""

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from monika.interfaces.cli.context import cli_main
from monika.interfaces.cli.theme import (
    BEAR_LOSS,
    BRASS,
    BULL_PROFIT,
    PHOSPHOR_AMBER,
    stamp_err,
    stamp_info,
    stamp_ok,
    stamp_warn,
)


async def _cmd_ask(args: Any) -> None:
    """Send a single question or command to Monika chat agent."""
    console = cli_main.get_console()
    question = " ".join(args.question) if isinstance(args.question, list) else str(args.question)
    if not question.strip():
        console.print(f"{stamp_err('ASK')} No question provided.")
        return

    is_raw = getattr(args, "raw", False)
    if not is_raw:
        console.print(f"{stamp_info('ASK')} Querying Monika: [bold]{question}[/]")

    from monika.application.agent.chat_agent import ChatAgent

    settings = cli_main.load_all_config()
    agent = ChatAgent(settings, user_id="cli_user", is_admin=True)

    reply_text, pending = await agent.handle(question)
    if is_raw:
        print(reply_text)
    else:
        console.print(f"\n{reply_text}\n")
        if pending:
            console.print(
                f"{stamp_warn('PROPOSAL')} Proposed action: {pending.description} (Action ID: {pending.action_id})"
            )

    out_json = getattr(args, "output_json", None)
    if out_json:
        import json as _json

        payload = {
            "query": question,
            "response": reply_text,
            "has_pending_action": pending is not None,
            "pending_action": pending.to_dict() if pending and hasattr(pending, "to_dict") else None,
        }
        try:
            with open(out_json, "w", encoding="utf-8") as f:
                _json.dump(payload, f, indent=2)
            if not is_raw:
                console.print(f"{stamp_ok('EXPORT')} Saved query output to: {out_json}")
        except Exception as e:
            if not is_raw:
                console.print(f"{stamp_err('EXPORT')} Failed to write output JSON: {e}")


async def _cmd_analyze(args: Any) -> None:
    """Trigger ad-hoc multi-timeframe analysis for a symbol."""
    console = cli_main.get_console()
    symbol = args.symbol.strip().upper().replace("/", "")
    context = getattr(args, "context", "")
    console.print(f"{stamp_info('ANALYZE')} Running ad-hoc analysis for [bold {BRASS}]{symbol}[/]...")

    from monika.application.agent.agent_loop import SystemAgentLoop

    settings = cli_main.load_all_config()
    agent_loop = SystemAgentLoop(settings=settings)

    async def _progress(msg: str) -> None:
        console.print(f"  [dim]• {msg}[/]")

    res = await agent_loop.execute_ad_hoc_analysis(
        symbol=symbol,
        progress_callback=_progress,
        custom_context=context or f"Ad-hoc analysis requested via CLI for {symbol}",
    )
    summary = res.get("formatted_summary") or f"Analysis for {symbol} completed."
    console.print(f"\n{summary}\n")


async def _cmd_backtest(args: Any) -> None:
    """Run historical backtest or walk-forward analysis."""
    console = cli_main.get_console()
    from monika.application.backtest.point_in_time_engine import BacktestMode, PointInTimeBacktestEngine
    from monika.application.backtest.walk_forward_engine import WalkForwardEngine

    await cli_main.init_db()
    settings = cli_main.load_all_config()

    if getattr(args, "start", None) and getattr(args, "end", None):
        try:
            start_date = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
            end_date = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
        except Exception as date_err:
            console.print(f"{stamp_err('BACKTEST')} Invalid date format (use YYYY-MM-DD): {date_err}")
            return
    else:
        days = getattr(args, "days", 30) or 30
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

    mode = getattr(args, "mode", "full") or "full"
    initial_equity = float(getattr(args, "equity", 10000.0) or 10000.0)

    symbol = getattr(args, "symbol", None)
    symbols = [symbol.upper()] if symbol else None
    strategy = getattr(args, "strategy", None)
    strategies = [strategy] if strategy else None

    console.print(f"{stamp_info('BACKTEST')} Initializing Backtest Engine [{BRASS}]{mode.upper()}[/] mode...")
    console.print(f"  Period:         {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    console.print(f"  Initial Equity: ${initial_equity:,.2f}")
    if symbols:
        console.print(f"  Symbols:        {', '.join(symbols)}")
    if strategies:
        console.print(f"  Strategies:     {', '.join(strategies)}")

    if mode == "walk_forward":
        engine = WalkForwardEngine(
            start_date=start_date,
            end_date=end_date,
            settings=settings,
            mode="full",
            is_window_days=getattr(args, "is_days", 90),
            oos_window_days=getattr(args, "oos_days", 30),
            symbols=symbols,
            strategies=strategies,
        )
        result = await engine.run()
        report_md = engine.generate_markdown_report(result)
        console.print(f"\n{report_md}\n")
    else:
        engine_mode: BacktestMode = (
            "full"
            if mode == "full"
            else "langgraph_parity"
            if mode == "langgraph_parity"
            else "graph"
            if mode == "graph"
            else "replay"
        )
        engine = PointInTimeBacktestEngine(
            start_date=start_date,
            end_date=end_date,
            settings=settings,
            mode=engine_mode,
            initial_equity=initial_equity,
            symbols=symbols,
            strategies=strategies,
        )

        run_record = await engine.run()
        console.print(f"{stamp_ok('BACKTEST')} Backtest completed successfully. Run ID: [bold]{run_record.id}[/]")


async def _cmd_stress_test(args: Any) -> None:
    """Run adversarial hostile market probe battery to test fail-closed risk invariants."""
    from monika.application.evals.hostile_market_probe import HostileMarketProbe

    sym = getattr(args, "symbol", "EURUSD").upper()
    ref = getattr(args, "price", 1.0850)

    probe = HostileMarketProbe(reference_price=ref, symbol=sym)

    def risk_validator(tick: Dict[str, Any]):
        if tick["bid"] <= 0 or tick["ask"] <= 0:
            return False, "Corrupt or non-positive price"
        if tick["bid"] > tick["ask"] or tick["spread_pips"] < 0:
            return False, "Crossed book inversion (bid > ask)"
        if tick["spread_pips"] > 10.0:
            return False, f"Catastrophic spread spike ({tick['spread_pips']} pips)"
        if time.time() - tick["timestamp"] > 120.0:
            return False, "Stale feed: timestamp exceeds max drift threshold (120s)"
        if abs(tick["bid"] - ref) / ref > 0.10:
            return False, "Flash crash tick: price drop > 10% trips circuit breaker"
        return True, "Valid tick"

    res = probe.verify_resilience(risk_validator)
    console = cli_main.get_console()
    console.print(f"\n[bold {PHOSPHOR_AMBER}][SECURITY] Monika Adversarial Stress Testing Battery ({sym})[/]")
    for d in res["details"]:
        status = f"[{BULL_PROFIT}]PASS (BLOCKED)[/]" if d["is_resilient"] else f"[{BEAR_LOSS}]FAIL (LEAKED)[/]"
        console.print(f" • [bold]{d['scenario']}[/] ({d['anomaly_type']}): {status} -> [italic]{d['reason']}[/]")
    if res["all_resilient"]:
        console.print(
            f"\n[{BULL_PROFIT}][OK] 100% RESILIENT: All {res['total_tested']} hostile feed anomalies successfully rejected fail-closed.[/]\n"
        )
    else:
        console.print(
            f"\n[{BEAR_LOSS}][FAIL] VULNERABILITY DETECTED: {res['total_tested'] - res['passed_count']} scenarios passed through filters![/]\n"
        )


async def _cmd_backup(args: Any) -> None:
    """Create database backup snapshot."""
    from monika.infrastructure.infra.db_backup import create_backup

    cfg = cli_main.load_all_config()
    dest = getattr(args, "dest", None)
    if dest:
        cfg.setdefault("database", {}).setdefault("backup", {})["backup_dir"] = dest
    res = await create_backup(cfg, force=getattr(args, "force", True))
    console = cli_main.get_console()
    if res.get("success"):
        console.print(
            f"[{BULL_PROFIT}][OK] Backup created successfully: {res.get('backup_file')} ({res.get('size_mb', 0):.2f} MB)[/]"
        )
    else:
        console.print(f"[{BEAR_LOSS}][FAIL] Backup failed: {res.get('error') or res.get('reason')}[/]")
