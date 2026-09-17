"""
Unit Tests for Telegram Vintage Formatter (telegram_bot/vintage_formatter.py).
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from telegram_bot.vintage_formatter import (
    make_header,
    make_footer,
    format_status_slip,
    format_positions_slip,
    format_risk_slip,
    format_stats_slip,
    format_alert_slip,
    format_help_slip,
)


def test_make_header_and_footer():
    hdr = make_header("TEST TITLE", width=40)
    assert "MONIKA DISPATCH // TEST TITLE" in hdr
    assert "=" * 40 in hdr

    ftr = make_footer(width=40)
    assert ftr == "=" * 40


def test_format_status_slip():
    slip = format_status_slip(
        status_text="AKTIF",
        pos_count=2,
        daily_pnl="+$12.50",
        drawdown="$0.00",
        last_analysis="2026-09-15 01:00 UTC",
        now_str="2026-09-15 02:00 UTC",
    )
    assert "SYSTEM STATUS" in slip
    assert "[ AKTIF ]" in slip
    assert "Posisi Open  : 2 LOT" in slip
    assert "Daily P&L    : +$12.50" in slip
    assert "```" in slip


def test_format_positions_slip_empty():
    slip = format_positions_slip([])
    assert "[ NIHIL ]" in slip
    assert "OPEN POSITIONS" in slip


def test_format_positions_slip_with_items():
    pos = MagicMock()
    pos.direction = "buy"
    pos.symbol = "EURUSD"
    pos.volume = 0.5
    pos.entry_price = 1.0850
    pos.sl = 1.0800
    pos.tp = 1.0950
    pos.opened_at = datetime(2026, 9, 15, 1, 30, tzinfo=timezone.utc)
    pos.pnl = 25.0
    pos.mt5_ticket = 12345

    slip = format_positions_slip([pos])
    assert "[BUY] #12345 EURUSD | 0.5 LOT" in slip
    assert "Open : 1.085" in slip
    assert "PnL: +25.00" in slip


def test_format_risk_slip():
    slip = format_risk_slip(
        status_text="AKTIF",
        mode="PAPER",
        streak_policy="warn_and_scale",
        suspended_symbols=["GBPUSD"],
        daily_pnl="+$50.00",
        drawdown="$10.00",
    )
    assert "RISK STATE LEDGER" in slip
    assert "[ AKTIF ]" in slip
    assert "[ PAPER ]" in slip
    assert "GBPUSD" in slip
    assert "DAILY P&L    : +$50.00" in slip


def test_format_stats_slip():
    stats = {
        "total_trades": 20,
        "win_rate_pct": 65.0,
        "avg_pnl_pct": 0.45,
        "total_pnl_pct": 9.0,
        "expectancy_per_trade_R": 0.35,
    }
    curve = {
        "starting_equity": 10000.0,
        "final_equity": 10900.0,
        "total_return_pct": 9.0,
        "max_drawdown_pct": 1.5,
    }
    slip = format_stats_slip(stats, equity_curve=curve)
    assert "PERFORMANCE LEDGER" in slip
    assert "WIN RATE     : 65.0%" in slip
    assert "[POSITIF] +0.35R" in slip
    assert "SIMULATED EQUITY" in slip


def test_format_alert_slip():
    slip = format_alert_slip("KILL SWITCH TRIGGERED", "Emergency stop invoked by operator", severity="DARURAT")
    assert "ALERT // DARURAT" in slip
    assert "SUBJEK : KILL SWITCH TRIGGERED" in slip
    assert "Emergency stop invoked by operator" in slip


def test_format_help_slip():
    cmds = {"status": "[Status] Show status", "kill": "[Kill] Emergency stop"}
    slip = format_help_slip(cmds)
    assert "COMMAND INDEX" in slip
    assert "/status" in slip
    assert "Show status" in slip
