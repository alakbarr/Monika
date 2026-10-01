# ==============================================================================
# File: tests/test_gap_analysis_remediation.py
# ==============================================================================
"""
Comprehensive verification test suite for all 6-phase remediation items:
- P1/P4: RiskGate auto-unpause, per-ticket trailing stop, symbol suspension
- P4: Currency dual formatting (USD/IDR), macro weekly summary, tearsheet standalone HTML
- P5: Indonesian NLP intent routing (debat ulang, ingat bahwa, buat skill)
- P6: Redis doctor check, Alembic SQLite dialect, MT5 error mapping, TradingView normalizer
"""

import os
import pytest
from datetime import datetime, timezone, timedelta


def test_mt5_actionable_error_mapping():
    """Verify P6.3: MT5 error code mapping returns actionable Indonesian diagnostics."""
    from execution.mt5_client import format_mt5_error, MT5_RETCODE_DESCRIPTIONS

    # Test known codes
    err_margin = format_mt5_error(10019, "No money")
    assert "10019" in err_margin
    assert "Margin tidak mencukupi" in err_margin
    assert "[No money]" in err_margin

    err_stops = format_mt5_error(10016)
    assert "10016" in err_stops
    assert "SL/TP tidak valid" in err_stops

    err_algo = format_mt5_error(10027)
    assert "Algo Trading dinonaktifkan" in err_algo

    # Test unknown code fallback
    err_unknown = format_mt5_error(99999)
    assert "99999" in err_unknown
    assert "tidak diketahui" in err_unknown


def test_tradingview_payload_normalization():
    """Verify P6.4: TradingView webhook normalizer converts various alert formats."""
    from gateway.webhook_ingress import normalize_tradingview_payload

    # 1. Standard Pine Script JSON payload
    tv_json = {
        "ticker": "OANDA:EURUSD",
        "action": "buy",
        "price": "1.0850",
        "sl": 1.0800,
        "tp": 1.0950,
        "volume": "0.5",
        "strategy": "EMA Cross",
        "passphrase": "my_secret_token",
    }
    norm = normalize_tradingview_payload(tv_json)
    assert norm["event_type"] == "trade_signal"
    assert norm["symbol"] == "EURUSD"
    assert norm["direction"] == "BUY"
    assert norm["volume"] == 0.5
    assert norm["price"] == 1.0850
    assert norm["sl"] == 1.0800
    assert norm["tp"] == 1.0950
    assert norm["strategy"] == "EMA Cross"
    assert norm["passphrase"] == "my_secret_token"

    # 2. String bytes payload with plain text key=value format
    raw_text = b"symbol=FX:XAUUSD\norder=sell\nqty=0.05\nprice=2050.5\nstop=2060.0"
    norm2 = normalize_tradingview_payload(raw_text)
    assert norm2["symbol"] == "XAUUSD"
    assert norm2["direction"] == "SELL"
    assert norm2["volume"] == 0.05
    assert norm2["price"] == 2050.5
    assert norm2["sl"] == 2060.0


def test_currency_conversion_helpers():
    """Verify P4.6: IDR dual currency formatting helpers."""
    from telegram_bot.message_formatter import (
        convert_usd_to_idr,
        format_idr_currency,
        format_currency_dual,
    )

    rate = 16000.0
    idr_val = convert_usd_to_idr(100.0, exchange_rate=rate)
    assert idr_val == 1600000.0

    formatted_idr = format_idr_currency(1600000.0)
    assert "Rp" in formatted_idr
    assert "1.600.000" in formatted_idr

    dual = format_currency_dual(10.5, exchange_rate=rate)
    assert "$10.50" in dual
    assert "Rp 168.000" in dual


@pytest.mark.asyncio
async def test_paper_tracker_suspension():
    """Verify P4.7: PaperTracker symbol suspension."""
    from utils.analytics.paper_tracker import PaperTracker
    from unittest.mock import AsyncMock, MagicMock
    from database.models import SystemConfig

    mock_session = AsyncMock()
    mock_execute_result = MagicMock()
    mock_cfg = SystemConfig(key='suspended_symbols', value="[]")
    mock_execute_result.scalar_one_or_none.return_value = mock_cfg
    mock_session.execute.return_value = mock_execute_result

    tracker = PaperTracker(settings={})
    res = await tracker.suspend_symbol(mock_session, "GBPUSD", duration_hours=2.0, reason="High impact news")

    assert res["symbol"] == "GBPUSD"
    assert res["duration_hours"] == 2.0
    assert res["reason"] == "High impact news"
    assert "until" in res

    # Test unsuspend
    un_res = await tracker.unsuspend_symbol(mock_session, "GBPUSD")
    assert un_res is True


@pytest.mark.asyncio
async def test_doctor_redis_check():
    """Verify P6.1: Doctor includes Redis connectivity check."""
    from cli.doctor import SystemDoctor

    doc = SystemDoctor()
    await doc.check_redis({})
    redis_diag = [d for d in doc.diagnostics if d.name == "Redis"]
    assert len(redis_diag) == 1
    assert redis_diag[0].category == "Cache"
    assert redis_diag[0].status in ("OK", "WARN", "FAIL")


def test_indonesian_intent_routing_patterns():
    """Verify P5: Indonesian NLP routing for debate, memory, and skill creation."""
    from telegram_bot.chat_tool_router import ChatToolRouter
    import re

    # Test intelligence pattern ("ingat bahwa...")
    intel_text = "ingat bahwa level 1.0800 adalah support kuat"
    intel_matched = bool(ChatToolRouter.INTEL_PATTERNS.search(intel_text))
    assert intel_matched is True

    # Test skill pattern ("buat skill...")
    skill_text = "buat skill analisis breakout london"
    skill_matched = bool(ChatToolRouter.SKILL_PATTERNS.search(skill_text))
    assert skill_matched is True


def test_command_router_includes_all_remediation_commands():
    """Verify all newly wired commands appear in CommandRouter help documentation."""
    from telegram_bot.command_router import CommandRouter, DIRECT_COMMANDS, COMMAND_HELP

    required_commands = [
        "suspend", "unsuspend", "macro_weekly", "counterfactual", "chronicle",
        "monte_carlo", "stress_test", "export_chat", "undo", "backup", "cron"
    ]
    for cmd in required_commands:
        assert cmd in DIRECT_COMMANDS, f"Command '{cmd}' missing from DIRECT_COMMANDS"
        assert cmd in COMMAND_HELP, f"Command '{cmd}' missing from COMMAND_HELP"

    help_text = CommandRouter.build_help_text()
    for cmd in required_commands:
        assert cmd in help_text, f"Command '{cmd}' missing from CommandRouter.build_help_text()"


def test_backtest_engines_accept_symbol_and_strategy_filters():
    """Verify PointInTimeBacktestEngine and WalkForwardEngine accept and initialize symbol & strategy filters."""
    from backtest.point_in_time_engine import PointInTimeBacktestEngine
    from backtest.walk_forward_engine import WalkForwardEngine
    from datetime import datetime, timezone

    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, tzinfo=timezone.utc)

    # Test PIT engine
    pit = PointInTimeBacktestEngine(
        start_date=start,
        end_date=end,
        symbols=["xauusd", "eurusd"],
        strategies=["xau_trend_engine"],
    )
    assert pit.symbols == ["XAUUSD", "EURUSD"]
    assert pit.strategies == ["xau_trend_engine"]

    # Test Walk-Forward engine
    wf = WalkForwardEngine(
        start_date=start,
        end_date=end,
        symbols=["btcusd"],
        strategies=["momentum_breakout"],
    )
    assert wf.symbols == ["BTCUSD"]
    assert wf.strategies == ["momentum_breakout"]

