# ==============================================================================
# File: tests/utils/test_analysis_tracker.py
# ==============================================================================

"""
Unit tests for Analysis Quality Tracker and Paper Tracker symbol aggregation.
Validates KeyError fixes, schema consistency, and reporting pipelines.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from utils.analytics.paper_tracker import _group_by_symbol, _group_by_symbol_direction, PaperTracker
from utils.analytics.analysis_tracker import (
    compute_analysis_quality_report,
    get_adaptive_threshold_hints,
    get_per_asset_bias_report,
    get_direction_accuracy_report,
)
from database.models import SystemConfig


def test_group_by_symbol_and_direction_schema():
    """Verify _group_by_symbol and _group_by_symbol_direction produce consistent schemas."""
    history = [
        {"symbol": "XAUUSD", "direction": "buy", "exit_reason": "tp_hit", "pnl_pct": 1.5},
        {"symbol": "XAUUSD", "direction": "sell", "exit_reason": "sl_hit", "pnl_pct": -0.8},
        {"symbol": "EURUSD", "direction": "buy", "exit_reason": "sl_hit", "pnl_pct": -0.5},
        {"symbol": "EURUSD", "direction": "buy", "exit_reason": "sl_hit", "pnl_pct": -0.5},
        {"symbol": "EURUSD", "direction": "buy", "exit_reason": "manual_close", "pnl_pct": 0.0},
    ]

    by_sym = _group_by_symbol(history)
    assert "XAUUSD" in by_sym
    assert "EURUSD" in by_sym

    # Check that all standard keys exist
    for sym, data in by_sym.items():
        assert "trades" in data
        assert "total" in data
        assert "wins" in data
        assert "losses" in data
        assert "pnl_pct" in data
        assert "total_pnl_pct" in data
        assert "win_rate" in data
        assert data["trades"] == data["total"]
        assert data["wins"] + data["losses"] == data["trades"]

    # XAUUSD: 2 market trades (1 win, 1 loss) -> 50% WR, pnl = 0.7
    assert by_sym["XAUUSD"]["trades"] == 2
    assert by_sym["XAUUSD"]["wins"] == 1
    assert by_sym["XAUUSD"]["losses"] == 1
    assert by_sym["XAUUSD"]["win_rate"] == 50.0
    assert abs(by_sym["XAUUSD"]["pnl_pct"] - 0.7) < 1e-4

    # EURUSD: 2 market trades (0 win, 2 losses), 1 manual_close ignored for market stats
    assert by_sym["EURUSD"]["trades"] == 2
    assert by_sym["EURUSD"]["wins"] == 0
    assert by_sym["EURUSD"]["losses"] == 2
    assert by_sym["EURUSD"]["win_rate"] == 0.0

    # Direction grouping
    by_sym_dir = _group_by_symbol_direction(history)
    assert "XAUUSD_buy" in by_sym_dir
    assert "XAUUSD_sell" in by_sym_dir
    assert "EURUSD_buy" in by_sym_dir

    assert by_sym_dir["EURUSD_buy"]["trades"] == 2
    assert by_sym_dir["EURUSD_buy"]["losses"] == 2
    assert by_sym_dir["EURUSD_buy"]["win_rate"] == 0.0


@pytest.mark.asyncio
async def test_compute_analysis_quality_report_no_key_error():
    """Verify compute_analysis_quality_report does not fail with KeyError: 'total'."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    # Mock SystemConfig query returning None (insert new)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    # Mock PaperTracker.get_statistics returning sample stats
    sample_stats = {
        "total_trades": 10,
        "market_trades": 10,
        "wins": 6,
        "losses": 4,
        "win_rate_pct": 60.0,
        "by_confluence": {
            "7": {"wins": 2, "total": 3},
            "8": {"wins": 4, "total": 7},
        },
        "by_priced_in": {
            "pi_2": {"score": 2, "wins": 3, "total": 4},
        },
        "by_symbol": {
            "XAUUSD": {"trades": 5, "total": 5, "wins": 4, "losses": 1, "pnl_pct": 3.2, "win_rate": 80.0},
            "EURUSD": {"trades": 5, "total": 5, "wins": 2, "losses": 3, "pnl_pct": -1.1, "win_rate": 40.0},
        },
        "by_symbol_direction": {
            "XAUUSD_buy": {"trades": 3, "total": 3, "wins": 3, "losses": 0, "win_rate": 100.0},
            "EURUSD_buy": {"trades": 5, "total": 5, "wins": 1, "losses": 4, "win_rate": 20.0},
        }
    }

    with patch("utils.analytics.paper_tracker.PaperTracker.get_statistics", new_callable=AsyncMock) as mock_get_stats:
        mock_get_stats.return_value = sample_stats

        report = await compute_analysis_quality_report(mock_session, days_back=30)

        assert report is not None
        assert report["total_outcomes"] == 10
        assert report["total_wins"] == 6
        assert report["overall_win_rate"] == 60.0

        # Ensure by_symbol is formatted properly with total and trades
        assert "XAUUSD" in report["by_symbol"]
        xau = report["by_symbol"]["XAUUSD"]
        assert xau["total"] == 5
        assert xau["trades"] == 5
        assert xau["wins"] == 4
        assert xau["losses"] == 1
        assert xau["win_rate"] == 80.0

        # Ensure by_symbol_direction is populated
        assert "EURUSD_buy" in report["by_symbol_direction"]
        eur_buy = report["by_symbol_direction"]["EURUSD_buy"]
        assert eur_buy["total"] == 5
        assert eur_buy["win_rate"] == 20.0

        # Verify SystemConfig was persisted
        assert mock_session.add.called
        assert mock_session.commit.called


@pytest.mark.asyncio
async def test_adaptive_threshold_hints_and_directional_bias():
    """Verify adaptive threshold hints and directional bias reporting parse report correctly."""
    mock_session = AsyncMock()

    saved_report = {
        "total_outcomes": 20,
        "overall_win_rate": 45.0,
        "by_symbol": {
            "XAUUSD": {"total": 20, "trades": 20, "win_rate": 70.0, "wins": 14, "losses": 6},
            "EURUSD": {"total": 20, "trades": 20, "win_rate": 25.0, "wins": 5, "losses": 15},
            "GBPUSD": {"total": 5, "trades": 5, "win_rate": 20.0, "wins": 1, "losses": 4},
        },
        "by_symbol_direction": {
            "EURUSD_buy": {"total": 10, "trades": 10, "win_rate": 10.0, "wins": 1, "losses": 9},
            "XAUUSD_buy": {"total": 12, "trades": 12, "win_rate": 75.0, "wins": 9, "losses": 3},
        }
    }

    mock_cfg = MagicMock()
    mock_cfg.value = json.dumps(saved_report)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_cfg
    mock_session.execute.return_value = mock_result

    # 1. Test adaptive threshold hints
    hints = await get_adaptive_threshold_hints(mock_session)
    assert "XAUUSD" in hints
    assert hints["XAUUSD"]["threshold_adjustment"] == 0
    assert "performing_well" in hints["XAUUSD"]["reason"]

    assert "EURUSD" in hints
    assert hints["EURUSD"]["threshold_adjustment"] == 2
    assert "below_breakeven" in hints["EURUSD"]["reason"]

    assert "GBPUSD" in hints
    assert hints["GBPUSD"]["threshold_adjustment"] == 0
    assert hints["GBPUSD"]["reason"] == "insufficient_data"

    # 2. Test directional bias report
    bias_report = await get_per_asset_bias_report(mock_session)
    flagged = bias_report.get("flagged_combinations", {})
    assert "EURUSD_buy" in flagged
    assert flagged["EURUSD_buy"]["win_rate"] == 10.0
    assert flagged["EURUSD_buy"]["trades"] == 10
    assert "AVOID BUY on EURUSD" in flagged["EURUSD_buy"]["recommendation"]
    assert "XAUUSD_buy" not in flagged


@pytest.mark.asyncio
async def test_direction_accuracy_report_alias_keys():
    """Verify get_direction_accuracy_report returns compatibility alias keys."""
    mock_session = AsyncMock()
    
    mock_analysis_1 = MagicMock()
    mock_analysis_1.symbol = "XAUUSD"
    mock_analysis_1.direction_correct_4h = True
    mock_analysis_1.direction_correct_24h = True
    mock_analysis_1.confidence = 0.8

    mock_analysis_2 = MagicMock()
    mock_analysis_2.symbol = "XAUUSD"
    mock_analysis_2.direction_correct_4h = False
    mock_analysis_2.direction_correct_24h = False
    mock_analysis_2.confidence = 0.7

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_analysis_1, mock_analysis_2]
    mock_session.execute.return_value = mock_result

    report = await get_direction_accuracy_report(mock_session, days_back=30)
    assert report["status"] == "success"
    assert report["total_evaluated_4h"] == 2
    assert report["overall_accuracy_4h_pct"] == 50.0
    # Check alias keys
    assert report["direction_accuracy_4h"] == 50.0
    assert "mean_brier_score" in report
    assert report["brier_score"] == report["mean_brier_score"]
