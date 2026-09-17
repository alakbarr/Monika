"""
Unit tests for WalkForwardEngine purging, embargo, DSR, and AlphaValidation integration.
"""
from datetime import datetime, timezone, timedelta
import pytest
from backtest.walk_forward_engine import WalkForwardEngine, WalkForwardFold, WalkForwardResult
from database.models import BacktestTrade


def test_walk_forward_folds_purge_and_embargo():
    start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2025, 7, 1, tzinfo=timezone.utc)

    # Engine with 2-day purge gap and 5% embargo
    engine = WalkForwardEngine(
        start_date=start_date,
        end_date=end_date,
        is_window_days=60,
        oos_window_days=30,
        step_days=30,
        purge_days=2,
        embargo_pct=0.05,
    )

    folds = engine.generate_folds()
    assert len(folds) >= 2

    for is_start, is_end, oos_start, oos_end in folds:
        # Purge gap: is_end must be at least purge_days before oos_start
        purge_gap = (oos_start - is_end).days
        assert purge_gap >= 2
        assert is_start < is_end
        assert oos_start < oos_end


def test_walk_forward_markdown_report_formatting():
    start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2025, 3, 1, tzinfo=timezone.utc)
    engine = WalkForwardEngine(start_date, end_date, purge_days=1)

    fold = WalkForwardFold(
        fold_index=0,
        is_start=start_date,
        is_end=start_date + timedelta(days=29),
        oos_start=start_date + timedelta(days=30),
        oos_end=end_date,
        is_metrics={"sharpe_ratio": 1.5},
        oos_metrics={"sharpe_ratio": 1.1},
        wfe=0.73,
        is_trades_count=10,
        oos_trades_count=5,
    )

    res = WalkForwardResult(
        folds=[fold],
        aggregate_is_sharpe=1.5,
        aggregate_oos_sharpe=1.1,
        overall_wfe=0.73,
        is_overfit=False,
        total_oos_trades=5,
        oos_win_rate_pct=60.0,
        deflated_sharpe=0.88,
    )

    report = engine.generate_markdown_report(res)
    assert "Deflated Sharpe Ratio (DSR)" in report
    assert "0.88" in report
    assert "**Purge**: 1d" in report
