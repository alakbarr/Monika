# ==============================================================================
# File: telegram_bot/vintage_formatter.py
# Description: Retro-Vintage Teletype / Telegraph Slip Formatter for Telegram
# ==============================================================================

"""
Vintage Teletype Slip Formatters for Telegram Bot.

Converts trading agent outputs into clean monospace banking ledgers / dispatch slips:
- Fixed-width ASCII telegraph borders
- Monospace wrapping (``` ... ```)
- Telegraph stamps ([ OK ], [ FAILED ], [ EXECUTION ], [ STANDBY ])
- Zero emoji clutter or AI-slop gradients
"""

from typing import Any, Dict, List, Optional, Sequence
from datetime import datetime, timezone


def make_header(title: str, width: int = 46) -> str:
    """Create a telegraph dispatch slip header."""
    bar = "=" * width
    title_line = f"MONIKA DISPATCH // {title.upper()}"
    if len(title_line) < width:
        title_line = title_line.center(width)
    return f"{bar}\n{title_line}\n{bar}"


def make_footer(width: int = 46) -> str:
    return "=" * width


def format_status_slip(
    status_text: str,
    pos_count: int,
    daily_pnl: str,
    drawdown: str,
    last_analysis: str,
    now_str: Optional[str] = None,
    width: int = 46,
) -> str:
    """Format agent status as teletype slip."""
    if not now_str:
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    stamp = f"[ {status_text.upper()} ]"
    lines = [
        "```",
        make_header("SYSTEM STATUS", width),
        f"STATUS         : {stamp}",
        f"TIME           : {now_str}",
        "-" * width,
        "PORTFOLIO:",
        f"  Open Positions : {pos_count} LOT",
        f"  Daily P&L      : {daily_pnl}",
        f"  Drawdown       : {drawdown}",
        "-" * width,
        f"Last Analysis  : {last_analysis}",
        make_footer(width),
        "```",
    ]
    return "\n".join(lines)


def format_positions_slip(positions: Sequence[Any], width: int = 46) -> str:
    """Format open positions as fixed-width ledger."""
    if not positions:
        return "```\n" + make_header("OPEN POSITIONS", width) + "\n[ NONE ] No open positions at this time.\n" + make_footer(width) + "\n```"

    lines = [
        "```",
        make_header(f"OPEN POSITIONS ({len(positions)})", width),
    ]
    for p in positions:
        side = p.direction.upper()
        opened = p.opened_at.strftime("%d/%m %H:%M") if p.opened_at else "-"
        pnl = f"{p.pnl:+.2f}" if p.pnl is not None else "-"
        ticket = getattr(p, "mt5_ticket", getattr(p, "ticket", "N/A"))
        lines.extend([
            f"[{side}] #{ticket} {p.symbol} | {p.volume} LOT",
            f"  Open : {p.entry_price} | SL: {p.sl or '-'} | TP: {p.tp or '-'}",
            f"  Time : {opened} | PnL: {pnl}",
            "-" * width,
        ])
    lines.append(make_footer(width))
    lines.append("```")
    return "\n".join(lines)


def format_risk_slip(
    status_text: str,
    mode: str,
    streak_policy: str,
    suspended_symbols: List[str],
    daily_pnl: Optional[str] = None,
    drawdown: Optional[str] = None,
    reason: Optional[str] = None,
    width: int = 46,
) -> str:
    """Format risk state as teletype slip."""
    susp_str = ", ".join(suspended_symbols) if suspended_symbols else "NONE"
    lines = [
        "```",
        make_header("RISK STATE LEDGER", width),
        f"STATUS       : [ {status_text.upper()} ]",
        f"MODE         : [ {mode.upper()} ]",
        f"STREAK POL.  : {streak_policy.upper()}",
        f"SUSPENDED    : {susp_str}",
    ]
    if reason:
        lines.append(f"REASON       : {reason}")
    lines.append("-" * width)
    if daily_pnl is not None:
        lines.append(f"DAILY P&L    : {daily_pnl}")
    if drawdown is not None:
        lines.append(f"DRAWDOWN     : {drawdown}")
    lines.extend([
        make_footer(width),
        "```",
    ])
    return "\n".join(lines)


def format_stats_slip(stats: Dict[str, Any], equity_curve: Optional[Dict[str, Any]] = None, width: int = 46) -> str:
    """Format paper trading performance as telegraph slip."""
    if not stats or stats.get("total_trades", 0) == 0:
        return "```\n" + make_header("PERFORMANCE STATS", width) + "\n[ NONE ] No trading records found.\n" + make_footer(width) + "\n```"

    lines = [
        "```",
        make_header("PERFORMANCE LEDGER", width),
        f"TOTAL TRADES : {stats.get('total_trades', 0)}",
        f"WIN RATE     : {stats.get('win_rate_pct', 0.0):.1f}%",
        f"AVG P&L/TRD  : {stats.get('avg_pnl_pct', 0.0):.3f}%",
        f"TOTAL P&L    : {stats.get('total_pnl_pct', 0.0):.3f}%",
        "-" * width,
    ]
    exp = stats.get("expectancy_per_trade_R")
    if exp is not None:
        exp_badge = "POSITIVE" if exp > 0 else ("UNCERTAIN" if exp > -0.1 else "NEGATIVE")
        lines.append(f"EDGE EXPECT. : [{exp_badge}] {exp:+.2f}R")

    if equity_curve:
        lines.extend([
            "-" * width,
            "SIMULATED EQUITY (RISK 1.5%):",
            f"  Start  : ${equity_curve.get('starting_equity', 0):.2f}",
            f"  Final  : ${equity_curve.get('final_equity', 0):.2f}",
            f"  Return : {equity_curve.get('total_return_pct', 0):.2f}%",
            f"  Max DD : {equity_curve.get('max_drawdown_pct', 0):.2f}%",
        ])

    lines.extend([
        make_footer(width),
        "```",
    ])
    return "\n".join(lines)


def format_alert_slip(title: str, detail: str, severity: str = "WARNING", width: int = 46) -> str:
    """Format system dispatch alert."""
    lines = [
        "```",
        make_header(f"ALERT // {severity.upper()}", width),
        f"SUBJECT : {title.upper()}",
        "-" * width,
        detail,
        make_footer(width),
        "```",
    ]
    return "\n".join(lines)


def format_help_slip(commands: Dict[str, str], width: int = 46) -> str:
    """Format bot command index with logical section grouping."""
    lines = [
        "```",
        make_header("COMMAND INDEX", width),
    ]

    categories = [
        ("TRADING & OPS", [
            "status", "positions", "close", "closeall", "trailing", "reconcile", "approvals", "approve", "reject",
        ]),
        ("INTEL & MACRO", [
            "pipeline", "brief", "analysis", "steer", "intel", "research", "archive_intel", "calendar", "fedwatch", "yields", "fear_greed", "cot",
        ]),
        ("RISK & SAFETY", [
            "risk", "risk_deep", "override", "vix", "edge", "unsuspend", "emergency", "pause", "resume", "kill", "interrupt", "resume_proposals",
        ]),
        ("PLUGINS & HARNESS", [
            "plugins", "plugin_catalog", "plugin_install", "plugin_uninstall", "plugin_toggle", "skills", "playbooks", "rollback", "crystallized", "strategies", "memory",
        ]),
        ("METRICS & REPORTS", [
            "report", "tearsheet", "stats", "cost", "tokens", "credits", "calibration", "history", "audit", "run", "backtest",
        ]),
    ]

    def _format_item(cmd: str, desc: str) -> str:
        prefix = f"/{cmd}".ljust(14) if not cmd.startswith("(") else f"{cmd}".ljust(14)
        clean_desc = desc
        if clean_desc.startswith("[") and "]" in clean_desc:
            clean_desc = clean_desc.split("]", 1)[1].strip()
        return f"{prefix}: {clean_desc}"

    # Group if commands dict contains full set (> 5 commands)
    has_categorized = any(cmd in commands for _, group in categories for cmd in group)
    if len(commands) > 5 and has_categorized:
        seen = set()
        for cat_name, cmd_list in categories:
            cat_cmds = [c for c in cmd_list if c in commands]
            if cat_cmds:
                lines.append(f"-- {cat_name} --")
                for c in cat_cmds:
                    lines.append(_format_item(c, commands[c]))
                    seen.add(c)
        remaining = [c for c in commands if c not in seen]
        if remaining:
            lines.append("-- GENERAL & CHAT --")
            for c in remaining:
                lines.append(_format_item(c, commands[c]))
    else:
        for cmd, desc in commands.items():
            lines.append(_format_item(cmd, desc))

    lines.extend([
        "-" * width,
        "Monika AI Trading Agent // Terminal Dispatch",
        make_footer(width),
        "```",
    ])
    return "\n".join(lines)



def format_risk_deep_slip(
    scorecard: Any,
    edge_summary: Optional[Dict[str, Any]] = None,
    token_budget: Optional[Dict[str, Any]] = None,
    width: int = 46,
) -> str:
    """Format 22-point deterministic risk scorecard as teletype slip."""
    items: List[Dict[str, Any]] = []
    if isinstance(scorecard, dict):
        raw_checks = scorecard.get("checks", {})
        for name, data in raw_checks.items():
            if isinstance(data, dict):
                items.append({
                    "name": name,
                    "passed": data.get("passed", False),
                    "current_value": data.get("current_value", "OK" if data.get("passed") else "BREACH"),
                    "limit_value": data.get("limit_value", data.get("reason", "-")),
                })
            else:
                items.append({
                    "name": name,
                    "passed": bool(data),
                    "current_value": "OK" if data else "FAIL",
                    "limit_value": "-",
                })
    elif isinstance(scorecard, (list, tuple)):
        items = list(scorecard)

    passed_count = sum(1 for c in items if c.get("passed", False))
    total_count = len(items)
    status_label = "ALL PASSED" if passed_count == total_count and total_count > 0 else f"{total_count - passed_count} BREACHES"

    lines = [
        "```",
        make_header("DETERMINISTIC RISK SCORECARD", width),
        f"GATE EVALUATION: [ {status_label} ({passed_count}/{total_count}) ]",
        "-" * width,
    ]

    for item in items:
        pass_tag = "[PASS]" if item.get("passed", False) else "[FAIL]"
        name = item.get("name", "check")[:20].ljust(20)
        curr = str(item.get("current_value", "-"))[:8]
        limit = str(item.get("limit_value", "-"))[:8]
        lines.append(f"{pass_tag} {name}: {curr} / {limit}")

    if edge_summary:
        lines.extend([
            "-" * width,
            "STATISTICAL EDGE:",
            f"  Exp: {edge_summary.get('expectancy', '-')} | WR: {edge_summary.get('win_rate', '-')}",
        ])

    if token_budget:
        tier = token_budget.get("tier", "TIER 1 (FULL)")
        capacity = token_budget.get("capacity_pct", 100)
        lines.extend([
            "-" * width,
            f"TOKEN BUDGET : [{tier}] {capacity}% CAP",
        ])

    lines.extend([
        make_footer(width),
        "```",
    ])
    return "\n".join(lines)


def format_approvals_slip(open_requests: List[Dict[str, Any]], width: int = 46) -> str:
    """Format open approval requests as teletype slip."""
    if not open_requests:
        return "```\n" + make_header("APPROVAL QUEUE", width) + "\n[ NONE ] No proposals pending approval.\n" + make_footer(width) + "\n```"

    lines = [
        "```",
        make_header(f"PENDING APPROVALS ({len(open_requests)})", width),
    ]
    for req in open_requests:
        action_id = req.get("id", req.get("action_id", "N/A"))
        symbol = req.get("symbol", "N/A")
        action = req.get("action", req.get("direction", "TRADE")).upper()
        lots = req.get("volume", req.get("lots", "-"))
        conf = req.get("confidence", "-")
        reason = req.get("reason", req.get("rationale", "-"))[:36]
        lines.extend([
            f"[{action}] #{action_id} {symbol} | {lots} LOT",
            f"  Confidence : {conf}",
            f"  Rationale  : {reason}",
            f"  Command    : /approve {action_id} | /reject {action_id}",
            "-" * width,
        ])
    lines.append(make_footer(width))
    lines.append("```")
    return "\n".join(lines)


def format_trailing_slip(positions: List[Dict[str, Any]], width: int = 46) -> str:
    """Format trailing stop positions as teletype slip."""
    if not positions:
        return "```\n" + make_header("TRAILING STOP STATUS", width) + "\n[ NONE ] No positions with active trailing stop.\n" + make_footer(width) + "\n```"

    lines = [
        "```",
        make_header(f"TRAILING STOP POSITIONS ({len(positions)})", width),
    ]
    for p in positions:
        ticket = p.get("ticket", "N/A")
        symbol = p.get("symbol", "N/A")
        side = p.get("direction", "BUY").upper()
        be_hit = "[BE TRIGGERED]" if p.get("be_triggered") else "[TRACKING]"
        entry = p.get("entry_price", "-")
        curr_sl = p.get("current_sl", "-")
        dist = p.get("atr_distance", "-")
        lines.extend([
            f"[{side}] #{ticket} {symbol} | {be_hit}",
            f"  Entry: {entry} | Curr SL: {curr_sl} | ATR Dist: {dist}",
            "-" * width,
        ])
    lines.append(make_footer(width))
    lines.append("```")
    return "\n".join(lines)


def format_reconcile_slip(stats: Dict[str, Any], width: int = 46) -> str:
    """Format MT5 vs DB reconciliation report as teletype slip."""
    lines = [
        "```",
        make_header("MT5 // DB RECONCILIATION REPORT", width),
        f"TIMESTAMP      : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "-" * width,
        "ORDERS RECONCILED   :",
        f"  Total Checked : {stats.get('orders_checked', stats.get('orders_evaluated', 0))}",
        f"  Updated/Filled: {stats.get('orders_updated', 0)}",
        f"  Orphaned/Ccl  : {stats.get('orders_cancelled', 0)}",
        "-" * width,
        "POSITIONS RECONCILED:",
        f"  Total Checked : {stats.get('positions_checked', stats.get('positions_evaluated', 0))}",
        f"  In-Sync Match : {stats.get('positions_synced', 0)}",
        f"  Adopted MT5   : {stats.get('positions_adopted', 0)}",
        f"  Closed Extern : {stats.get('positions_closed_externally', 0)}",
        "-" * width,
        f"OVERALL STATUS : [ {stats.get('status', 'COMPLETED').upper()} ]",
        make_footer(width),
        "```",
    ]
    return "\n".join(lines)


def format_fedwatch_slip(data: Dict[str, Any], width: int = 46) -> str:
    """Format CME FedWatch outlook as teletype slip."""
    lines = [
        "```",
        make_header("CME FEDWATCH RATE OUTLOOK", width),
        f"TIMESTAMP      : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "-" * width,
    ]
    fw_list = data.get("fedwatch", [])
    if fw_list:
        first = fw_list[0]
        lines.append(f"NEXT FOMC DATE : {first.get('meeting_date', 'N/A')}")
        probs = first.get("probabilities", {})
        if isinstance(probs, dict):
            for k, v in probs.items():
                v_str = f"{v:.1f}%" if isinstance(v, (int, float)) else str(v)
                lines.append(f"  {k.replace('_', ' ').upper():<16}: {v_str}")
        lines.append("-" * width)

    cb_list = data.get("central_banks", [])
    if cb_list:
        lines.append("CENTRAL BANK POLICY RATES:")
        for cb in cb_list[:5]:
            bank = cb.get("bank", "CB")
            rate = cb.get("current_rate", 0.0)
            cut = cb.get("prob_cut", 0.0)
            lines.append(f"  {bank:<6} Rate: {rate:.2f}% | Prob Cut: {cut:.0f}%")
        lines.append("-" * width)

    lines.append(make_footer(width))
    lines.append("```")
    return "\n".join(lines)


def format_yields_slip(data: Dict[str, Any], width: int = 46) -> str:
    """Format US Treasury Yield Curve and 2s10s spread as teletype slip."""
    spread = data.get("spread_2s10s")
    inverted = data.get("is_inverted", False)
    spread_str = f"{spread:+.2f}%" if spread is not None else "N/A"
    status_stamp = "[ INVERTED (RECESSION) ]" if inverted else "[ NORMAL CURVE ]"

    lines = [
        "```",
        make_header("US TREASURY YIELDS & 2S10S", width),
        f"TIMESTAMP      : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"2S10S SPREAD   : {spread_str} {status_stamp}",
        "-" * width,
        "US TREASURY BENCHMARKS:",
    ]
    for y in data.get("treasury_yields", [])[:6]:
        tenor = y.get("tenor", "-")
        y_val = y.get("yield_percent", 0.0)
        lines.append(f"  {tenor:<6}: {y_val:.2f}%")

    gb = data.get("global_bonds", [])
    if gb:
        lines.append("-" * width)
        lines.append("SOVEREIGN 10Y BENCHMARKS:")
        for b in gb[:4]:
            lines.append(f"  {b.get('country_tenor', '-'):<10}: {b.get('yield_percent', 0.0):.2f}%")

    lines.append(make_footer(width))
    lines.append("```")
    return "\n".join(lines)


def format_fear_greed_slip(data: Dict[str, Any], width: int = 46) -> str:
    """Format Fear & Greed sentiment index as teletype slip."""
    val = data.get("current_value", 50)
    classification = str(data.get("classification", "Neutral")).upper()
    wow = data.get("wow_change")
    wow_str = f"{wow:+d} WoW" if wow is not None else "0 WoW"

    lines = [
        "```",
        make_header("FEAR & GREED SENTIMENT INDEX", width),
        f"TIMESTAMP      : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"SCORE          : {val} / 100 [ {classification} ]",
        f"WOW CHANGE     : {wow_str}",
        "-" * width,
        "SIGNAL INTERPRETATION:",
        f"  {data.get('interpretation', 'Balanced sentiment')}",
        make_footer(width),
        "```",
    ]
    return "\n".join(lines)


def format_cot_slip(data: List[Dict[str, Any]], width: int = 46) -> str:
    """Format CFTC COT institutional positioning as teletype slip."""
    lines = [
        "```",
        make_header("CFTC COT POSITIONING", width),
        f"TIMESTAMP      : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "-" * width,
    ]
    if not data:
        lines.append("  No recent COT positioning records found.")
    else:
        for r in data[:5]:
            m = r.get("market_code", "N/A")
            net = r.get("net_position", 0)
            sign = "+" if net >= 0 else ""
            lines.append(f"MARKET {m:<10} Net: {sign}{net:,} contracts")
            lines.append(f"  AssetMgr Long: {r.get('asset_mgr_long', 0):,} | Short: {r.get('asset_mgr_short', 0):,}")
            lines.append(f"  Leveraged Long: {r.get('leveraged_long', 0):,} | Short: {r.get('leveraged_short', 0):,}")
            lines.append("-" * width)
    lines.append(make_footer(width))
    lines.append("```")
    return "\n".join(lines)


def format_playbooks_slip(playbooks: List[Dict[str, Any]], width: int = 46) -> str:
    """Format trading playbooks and FSM lifecycle status as teletype slip."""
    lines = [
        "```",
        make_header("TRADING PLAYBOOKS LIFECYCLE", width),
        f"TIMESTAMP      : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"TOTAL COUNT    : {len(playbooks)}",
        "-" * width,
    ]
    if not playbooks:
        lines.append("  No active or candidate playbooks registered.")
    else:
        for p in playbooks[:6]:
            name = p.get("name", "Unknown")[:20]
            st = p.get("status", "ACTIVE").upper()
            wr = p.get("win_rate", 0.0)
            trades = p.get("total_trades", 0)
            lines.append(f"{name:<20} [{st}]")
            lines.append(f"  Win Rate: {wr:.1%} ({trades} trades)")
            if p.get("cooldown_until"):
                lines.append(f"  Cooldown: {p.get('cooldown_until')}")
            lines.append("-" * width)
    lines.append(make_footer(width))
    lines.append("```")
    return "\n".join(lines)


def format_crystallized_slip(skills: List[Dict[str, Any]], width: int = 46) -> str:
    """Format autonomously crystallized procedural skills as teletype slip."""
    lines = [
        "```",
        make_header("CRYSTALLIZED SKILLS LEDGER", width),
        f"TIMESTAMP      : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"TOTAL SKILLS   : {len(skills)}",
        "-" * width,
    ]
    if not skills:
        lines.append("  No crystallized procedural skills found.")
    else:
        for s in skills[:6]:
            name = s.get("name", "Unknown")[:22]
            sym = s.get("symbol", "-")
            st = "DEP" if s.get("is_deprecated") or s.get("status") == "deprecated" else "ACT"
            wr = s.get("win_rate", 0.0)
            pnl = s.get("total_pnl_usd", 0.0)
            lines.append(f"{name:<22} ({sym}) [{st}]")
            lines.append(f"  WinRate: {wr:.1%} | PnL: ${pnl:+,.2f}")
            lines.append("-" * width)
    lines.append(make_footer(width))
    lines.append("```")
    return "\n".join(lines)


def format_rollback_slip(result: Dict[str, Any], width: int = 46) -> str:
    """Format playbook rollback result as teletype slip."""
    st = result.get("status", "UNKNOWN").upper()
    name = result.get("name", "Unknown")
    msg = result.get("message", "-")
    lines = [
        "```",
        make_header("PLAYBOOK ROLLBACK RECEIPT", width),
        f"TIMESTAMP      : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"TARGET         : {name}",
        f"STATUS         : [ {st} ]",
        "-" * width,
        f"DETAIL: {msg}",
        make_footer(width),
        "```",
    ]
    return "\n".join(lines)


def format_pipeline_slip(data: Dict[str, Any], width: int = 46) -> str:
    """Format LangGraph Analysis Pipeline DAG execution flow as teletype slip."""
    status = data.get("status", "IDLE").upper()
    stage = data.get("current_stage", "STAGE 1").upper()
    last_cycle = data.get("last_cycle", "N/A")
    duration = data.get("duration", "-")
    active_nodes = data.get("active_nodes", "5/5")
    health = data.get("health", "OPTIMAL").upper()

    lines = [
        "```",
        make_header("LANGGRAPH PIPELINE DAG", width),
        f"STATUS         : [ {status} ]",
        f"CURRENT STAGE  : {stage}",
        f"LAST CYCLE     : {last_cycle}",
        f"CYCLE DURATION : {duration}",
        "-" * width,
        "ANALYSIS PIPELINE DAG FLOW:",
        "  [●] Stage 1: Macro & Fundamental Ingestion",
        "       │ (Econ Calendar, News, FedWatch, Yields)",
        "       ▼",
        "  [●] Stage 2: Multi-Asset Technical & Quant",
        "       │ (TimesFM, MT5 Price Action, Indicators)",
        "       ▼",
        "  [●] Stage 2b: Multi-Agent Debate Node",
        "       │ (Bull vs Bear vs Risk Arbitrator)",
        "       ▼",
        "  [●] Stage 3: Deterministic Risk Gate (22 Rules)",
        "       │ (Drawdown, Exposure, VPIN, Volatility)",
        "       ▼",
        "  [●] Stage 4: Order Execution / Paper Trading",
        "       │ (MT5 Client, Slippage & Spread Guard)",
        "-" * width,
        f"NODES STATUS   : {active_nodes} Active / Evaluated",
        f"PIPELINE HEALTH: [ {health} ]",
        make_footer(width),
        "```",
    ]
    return "\n".join(lines)




