"""
Unit Tests for ReportGenerator Daily-Resampled Sharpe & Sortino Calculations.
"""
import pytest
from datetime import datetime, timezone, timedelta
from database.models import BacktestRun, BacktestTrade
from backtest.report_generator import ReportGenerator


def test_report_generator_daily_sharpe_and_sortino():
    """Verify ReportGenerator calculates Daily Sharpe and Sortino using daily return series."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 10, tzinfo=timezone.utc)
    
    run = BacktestRun(
        mode="full",
        start_date=start,
        end_date=end,
        initial_equity=10000.0,
    )

    trades = [
        BacktestTrade(symbol="EURUSD", direction="buy", entry_time=start + timedelta(days=1), pnl_pct=2.0),
        BacktestTrade(symbol="EURUSD", direction="buy", entry_time=start + timedelta(days=2), pnl_pct=-1.0),
        BacktestTrade(symbol="EURUSD", direction="buy", entry_time=start + timedelta(days=4), pnl_pct=3.0),
        BacktestTrade(symbol="EURUSD", direction="buy", entry_time=start + timedelta(days=6), pnl_pct=-0.5),
    ]

    equity_curve = [
        {"timestamp": start, "equity": 10000.0},
        {"timestamp": start + timedelta(days=1), "equity": 10200.0},
        {"timestamp": start + timedelta(days=2), "equity": 10100.0},
        {"timestamp": start + timedelta(days=4), "equity": 10400.0},
        {"timestamp": start + timedelta(days=6), "equity": 10350.0},
        {"timestamp": end, "equity": 10350.0},
    ]

    generator = ReportGenerator(
        run=run,
        trades=trades,
        equity_curve=equity_curve,
        start_date=start,
        end_date=end
    )
    generator.calculate_metrics()

    assert run.total_trades == 4
    assert run.win_rate == 50.0
    assert run.profit_factor > 1.0
    assert run.sharpe_ratio is not None and run.sharpe_ratio > 0.0
    assert generator.sortino_ratio > 0.0
    assert generator.expectancy_r > 0.0
    assert run.max_drawdown_pct > 0.0


def test_report_generator_crypto_annualization_365():
    """Verify ReportGenerator uses 365 days annualization factor for crypto-only backtests."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 10, tzinfo=timezone.utc)
    
    run = BacktestRun(mode="full", start_date=start, end_date=end, initial_equity=10000.0)
    trades = [
        BacktestTrade(symbol="BTCUSD", direction="buy", entry_time=start + timedelta(days=1), pnl_pct=5.0),
        BacktestTrade(symbol="BTCUSD", direction="buy", entry_time=start + timedelta(days=3), pnl_pct=-2.0),
    ]

    equity_curve = [
        {"timestamp": start, "equity": 10000.0},
        {"timestamp": start + timedelta(days=1), "equity": 10500.0},
        {"timestamp": start + timedelta(days=3), "equity": 10300.0},
        {"timestamp": end, "equity": 10300.0},
    ]

    gen = ReportGenerator(run=run, trades=trades, equity_curve=equity_curve, start_date=start, end_date=end)
    gen.calculate_metrics()

    daily_rets = gen._resample_daily_returns(10000.0)
    import numpy as np
    mean_ret = float(np.mean(daily_rets))
    std_ret = float(np.std(daily_rets, ddof=1))
    expected_sharpe_365 = round(float((mean_ret / std_ret) * np.sqrt(365)), 2)

    assert run.sharpe_ratio is not None
    assert abs(run.sharpe_ratio - expected_sharpe_365) < 1e-2
    assert gen.sortino_ratio > 0.0
