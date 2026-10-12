"""
Unit tests for QuantTearsheetGenerator (PyFolio / QuantStats Institutional Grade).
"""

from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional
import pytest

from logging_observability.reporting.tearsheet_generator import (
    QuantTearsheetGenerator,
    TearsheetResult,
)


@dataclass
class MockTrade:
    symbol: str
    pnl: float
    pnl_pct: float
    closed_at: datetime
    pnl_usd: Optional[float] = None


def test_tearsheet_empty_trades():
    """Verify tearsheet handles empty trade list cleanly without ZeroDivisionError."""
    result = QuantTearsheetGenerator.generate_from_trades([], initial_equity=10000.0)
    assert isinstance(result, TearsheetResult)
    assert result.total_trades == 0
    assert result.initial_equity == 10000.0
    assert result.final_equity == 10000.0
    assert result.total_net_pnl == 0.0
    assert result.win_rate_pct == 0.0
    assert result.profit_factor == 0.0
    assert result.annualized_sharpe == 0.0
    assert result.annualized_sortino == 0.0
    assert result.max_drawdown_pct == 0.0

    # Ensure formatters work without errors
    md = result.to_markdown()
    assert "# Executive Quant Tearsheet" in md
    assert "$10,000.00" in md

    html = result.to_telegram_html()
    assert "Executive Quant Tearsheet" in html
    assert "<code>$10,000.00</code>" in html

    d = result.to_dict()
    assert d["total_trades"] == 0
    assert d["initial_equity"] == 10000.0


def test_tearsheet_standard_trades():
    """Verify comprehensive tearsheet analytics on a representative trade history."""
    base_time = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    trades = [
        # Day 1: +$200, -$100 -> Day PnL +$100 (+1%)
        MockTrade("EURUSD", 200.0, 2.0, base_time),
        MockTrade("GBPUSD", -100.0, -1.0, base_time + timedelta(hours=3)),
        # Day 2: +$300 -> Day PnL +$300 (+3%)
        MockTrade("EURUSD", 300.0, 3.0, base_time + timedelta(days=1)),
        # Day 3: -$200 -> Day PnL -$200 (-2%)
        MockTrade("XAUUSD", -200.0, -2.0, base_time + timedelta(days=2)),
        # Day 4: +$400 -> Day PnL +$400 (+4%)
        MockTrade("BTCUSD", 400.0, 4.0, base_time + timedelta(days=3)),
    ]

    result = QuantTearsheetGenerator.generate_from_trades(trades, initial_equity=10000.0)

    assert result.total_trades == 5
    assert result.winning_trades == 3
    assert result.losing_trades == 2
    assert result.win_rate_pct == 60.0
    assert result.total_net_pnl == 600.0
    assert result.final_equity == 10600.0
    assert result.total_return_pct == 6.0

    # Gross profit: 200 + 300 + 400 = 900
    # Gross loss: 100 + 200 = 300
    # Profit factor: 900 / 300 = 3.0
    assert result.profit_factor == 3.0

    # Average win: 900 / 3 = 300
    # Average loss: 300 / 2 = 150
    # Payoff ratio: 300 / 150 = 2.0
    assert result.payoff_ratio == 2.0

    # Expectancy (R): (0.60 * 2.0) - 0.40 = 1.20 - 0.40 = 0.80 R
    assert result.expectancy_r == 0.80
    # Expectancy ($): 600 / 5 = 120.00
    assert result.expectancy_usd == 120.00

    # Drawdown verification:
    # Equity progression: 10000 -> 10200 -> 10100 (DD: 0.98%) -> 10400 -> 10200 (DD: 1.92%) -> 10600 (DD: 0%)
    assert result.max_drawdown_pct > 0.0
    assert result.current_drawdown_pct == 0.0  # finished at peak

    # Risk-adjusted ratios & tail risk
    assert result.annualized_sharpe > 0.0
    assert result.annualized_sortino > 0.0
    assert result.calmar_ratio > 0.0
    assert result.gain_to_pain_ratio > 0.0
    assert result.cagr_pct > 0.0
    assert result.var_95_pct >= 0.0
    assert result.cvar_95_pct >= 0.0

    # Asset breakdown
    assert "EURUSD" in result.by_symbol
    assert result.by_symbol["EURUSD"]["trades"] == 2
    assert result.by_symbol["EURUSD"]["wins"] == 2
    assert result.by_symbol["EURUSD"]["net_pnl"] == 500.0
    assert result.by_symbol["EURUSD"]["win_rate_pct"] == 100.0

    assert "XAUUSD" in result.by_symbol
    assert result.by_symbol["XAUUSD"]["net_pnl"] == -200.0
    assert result.by_symbol["XAUUSD"]["win_rate_pct"] == 0.0


def test_tearsheet_all_winning_trades():
    """Verify tearsheet behavior when all trades are profitable."""
    t0 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    trades = [
        {"symbol": "EURUSD", "pnl": 150.0, "pnl_pct": 1.5, "closed_at": t0.isoformat()},
        {"symbol": "GBPUSD", "pnl": 250.0, "pnl_pct": 2.5, "closed_at": (t0 + timedelta(days=1)).isoformat()},
    ]
    result = QuantTearsheetGenerator.generate_from_trades(trades, initial_equity=10000.0)

    assert result.total_trades == 2
    assert result.winning_trades == 2
    assert result.losing_trades == 0
    assert result.win_rate_pct == 100.0
    assert result.profit_factor == 99.0  # Cap when no losses
    assert result.annualized_sortino == 99.0  # Cap when no downside
    assert result.max_drawdown_pct == 0.0
    assert result.gain_to_pain_ratio == 99.0
    assert result.var_95_pct == 0.0
    assert result.cvar_95_pct == 0.0


def test_tearsheet_all_losing_trades():
    """Verify tearsheet behavior when all trades are losses."""
    t0 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    trades = [
        {"symbol": "EURUSD", "pnl": -100.0, "pnl_pct": -1.0, "closed_at": t0},
        {"symbol": "USDJPY", "pnl": -200.0, "pnl_pct": -2.0, "closed_at": t0 + timedelta(days=1)},
    ]
    result = QuantTearsheetGenerator.generate_from_trades(trades, initial_equity=10000.0)

    assert result.total_trades == 2
    assert result.winning_trades == 0
    assert result.losing_trades == 2
    assert result.win_rate_pct == 0.0
    assert result.profit_factor == 0.0
    assert result.total_net_pnl == -300.0
    assert result.final_equity == 9700.0
    assert result.max_drawdown_pct > 0.0
    assert result.var_95_pct > 0.0
    assert result.cvar_95_pct >= result.var_95_pct


def test_tearsheet_rendering_formats():
    """Verify Markdown and Telegram HTML renderings contain required quantitative fields."""
    base_time = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    trades = [
        {"symbol": "EURUSD", "pnl_usd": 120.0, "pnl_pct": 1.2, "closed_at": base_time},
        {"symbol": "EURUSD", "pnl_usd": -60.0, "pnl_pct": -0.6, "closed_at": base_time + timedelta(hours=4)},
    ]
    result = QuantTearsheetGenerator.generate_from_trades(trades, initial_equity=5000.0)

    md = result.to_markdown()
    assert "# Executive Quant Tearsheet" in md
    assert "Annualized Sharpe" in md
    assert "CAGR" in md
    assert "Value-at-Risk (VaR 95%)" in md
    assert "Tail Risk (CVaR 95%)" in md
    assert "Trade Expectancy (R)" in md
    assert "Max Peak-to-Valley DD" in md
    assert "Asset Performance Breakdown" in md
    assert "EURUSD" in md

    html = result.to_telegram_html()
    assert "Executive Quant Tearsheet" in html
    assert "<b>Sharpe:</b>" in html
    assert "CAGR:" in html
    assert "VaR (95%):" in html
    assert "CVaR (95%):" in html
    assert "<b>Max Drawdown:</b>" in html
    assert "<b>Trades:</b> 2" in html
    assert "<b>Win Rate:</b>" in html
    assert "EURUSD" in html
