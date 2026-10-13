# ==============================================================================
# File: tests/backtest/test_fase7_lookahead_and_kelly.py
# Description: Unit tests for Phase 7 (Zero-Lookahead Execution, Realized
#              Payoff Kelly Sizing, and CI/CD Verification Utilities)
# ==============================================================================

import os
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from monika.application.execution.service.risk_evaluator import RiskEvaluatorMixin
from monika.core.analytics.paper_tracker import _group_by_symbol
from scripts.update_index_toc import generate_toc


class _DummyRiskEvaluator(RiskEvaluatorMixin):
    def __init__(self, settings):
        self.settings = settings
        self.mt5 = MagicMock()
        self.broker_adapter = MagicMock()


@pytest.mark.asyncio
async def test_paper_tracker_group_by_symbol_calculates_realized_payoff():
    """Verify _group_by_symbol calculates avg_win_pct, avg_loss_pct and payoff_ratio."""
    history = [
        {"symbol": "EURUSD", "exit_reason": "tp_hit", "pnl_pct": 2.0},
        {"symbol": "EURUSD", "exit_reason": "tp_hit", "pnl_pct": 1.0},
        {"symbol": "EURUSD", "exit_reason": "sl_hit", "pnl_pct": -1.0},
        {"symbol": "GBPUSD", "exit_reason": "sl_hit", "pnl_pct": -1.5},
    ]

    by_sym = _group_by_symbol(history)

    assert "EURUSD" in by_sym
    eur = by_sym["EURUSD"]
    assert eur["trades"] == 3
    assert eur["wins"] == 2
    assert eur["losses"] == 1
    assert eur["avg_win_pct"] == 1.5  # (2.0 + 1.0) / 2
    assert eur["avg_loss_pct"] == 1.0  # abs(-1.0) / 1
    assert eur["payoff_ratio"] == 1.5  # 1.5 / 1.0


@pytest.mark.asyncio
async def test_risk_evaluator_uses_realized_payoff_ratio():
    """Verify ExecutionRiskEvaluator calculates Kelly using realized payoff_ratio from sym_stats."""
    settings = {
        "trading": {
            "risk": {
                "dynamic_risk_scaling": True,
                "dynamic_risk_min_pct": 0.5,
                "dynamic_risk_max_pct": 2.5,
                "dynamic_risk_lookback_trades": 5,
                "min_rr_ratio": 1.2,  # Config fallback
            }
        }
    }
    evaluator = _DummyRiskEvaluator(settings=settings)

    # Mock PaperTracker statistics with 60% win rate and realized payoff ratio 2.0
    # Kelly = 0.60 - (0.40 / 2.0) = 0.60 - 0.20 = 0.40
    # Half-Kelly pct = 0.40 * 50 = 20.0 -> clamped to max_pct (2.5)
    mock_stats = {
        "by_symbol": {
            "EURUSD": {
                "trades": 10,
                "win_rate": 60.0,
                "payoff_ratio": 2.0,
            }
        }
    }

    with patch(
        "monika.core.analytics.paper_tracker.PaperTracker.get_statistics", new_callable=AsyncMock
    ) as mock_get_stats:
        mock_get_stats.return_value = mock_stats
        session = AsyncMock()

        scaled_risk = await evaluator._get_dynamic_risk_percent(session, "EURUSD", base_risk_pct=1.0)
        assert scaled_risk == 2.5


@pytest.mark.asyncio
async def test_risk_evaluator_negative_expectancy_returns_zero():
    """Verify ExecutionRiskEvaluator returns 0.0 risk for negative expectancy Kelly."""
    settings = {
        "trading": {
            "risk": {
                "dynamic_risk_scaling": True,
                "dynamic_risk_lookback_trades": 5,
                "min_rr_ratio": 1.2,
            }
        }
    }
    evaluator = _DummyRiskEvaluator(settings=settings)

    # Win rate 30%, Payoff ratio 1.0 -> Kelly = 0.30 - (0.70 / 1.0) = -0.40 <= 0
    mock_stats = {
        "by_symbol": {
            "EURUSD": {
                "trades": 10,
                "win_rate": 30.0,
                "payoff_ratio": 1.0,
            }
        }
    }

    with patch(
        "monika.core.analytics.paper_tracker.PaperTracker.get_statistics", new_callable=AsyncMock
    ) as mock_get_stats:
        mock_get_stats.return_value = mock_stats
        session = AsyncMock()

        scaled_risk = await evaluator._get_dynamic_risk_percent(session, "EURUSD", base_risk_pct=1.0)
        assert scaled_risk == 0.0


def test_update_index_toc_check_mode():
    """Verify update_index_toc check_only does not fail when INDEX.md is synced."""
    # Running check_only on clean INDEX.md should not raise SystemExit
    generate_toc(check_only=True)
