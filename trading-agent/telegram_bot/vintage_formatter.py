# ==============================================================================
# File: telegram_bot/vintage_formatter.py
# Description: Retro-Vintage Teletype / Telegraph Slip Formatter for Telegram
# ==============================================================================

"""
Vintage Teletype Slip Formatters for Telegram Bot.

Converts trading agent outputs into clean monospace banking ledgers / dispatch slips:
- Fixed-width ASCII telegraph borders
- Monospace wrapping (``` ... ```)
- Telegraph stamps ([ OK ], [ GAGAL ], [ EKSEKUSI ], [ SIAGA ])
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
        f"WAKTU          : {now_str}",
        "-" * width,
        "PORTOFOLIO:",
        f"  Posisi Open  : {pos_count} LOT",
        f"  Daily P&L    : {daily_pnl}",
        f"  Drawdown     : {drawdown}",
        "-" * width,
        f"Analisis Terakhir : {last_analysis}",
        make_footer(width),
        "```",
    ]
    return "\n".join(lines)


def format_positions_slip(positions: Sequence[Any], width: int = 46) -> str:
    """Format open positions as fixed-width ledger."""
    if not positions:
        return "```\n" + make_header("OPEN POSITIONS", width) + "\n[ NIHIL ] Tidak ada posisi terbuka saat ini.\n" + make_footer(width) + "\n```"

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
        lines.append(f"ALASAN       : {reason}")
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
        return "```\n" + make_header("PERFORMANCE STATS", width) + "\n[ NIHIL ] Belum ada data trading tercatat.\n" + make_footer(width) + "\n```"

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
        exp_badge = "POSITIF" if exp > 0 else ("UNCERTAIN" if exp > -0.1 else "NEGATIF")
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


def format_alert_slip(title: str, detail: str, severity: str = "PERINGATAN", width: int = 46) -> str:
    """Format system dispatch alert."""
    lines = [
        "```",
        make_header(f"ALERT // {severity.upper()}", width),
        f"SUBJEK : {title.upper()}",
        "-" * width,
        detail,
        make_footer(width),
        "```",
    ]
    return "\n".join(lines)


def format_help_slip(commands: Dict[str, str], width: int = 46) -> str:
    """Format bot command index."""
    lines = [
        "```",
        make_header("COMMAND INDEX", width),
    ]
    for cmd, desc in commands.items():
        prefix = f"/{cmd}".ljust(14)
        # Clean desc of brackets
        clean_desc = desc
        if clean_desc.startswith("[") and "]" in clean_desc:
            clean_desc = clean_desc.split("]", 1)[1].strip()
        lines.append(f"{prefix}: {clean_desc}")
    lines.extend([
        "-" * width,
        "Monika AI Trading Agent // Terminal Dispatch",
        make_footer(width),
        "```",
    ])
    return "\n".join(lines)
