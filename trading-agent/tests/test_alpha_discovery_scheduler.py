"""
Unit tests for Autonomous Alpha Discovery Scheduler.
Verifies hypothesis generation, Walk-Forward validation vetting,
WFE threshold filtering (>0.60), and proposal persistence.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from scheduler.alpha_discovery_scheduler import (
    AlphaDiscoveryScheduler,
    AlphaHypothesis,
    CandidateAlphaProposal,
)
from backtest.walk_forward_engine import WalkForwardResult, WalkForwardFold


@pytest.fixture
def mock_settings():
    return {
        "trading": {
            "asset_universe": ["XAUUSD", "EURUSD"],
            "edge_strategy": {
                "xau_trend_engine": {"ema_fast": 20, "ema_slow": 50},
                "trend_trailing": {"sl_atr_multiplier": 1.5, "tp_sl_multiplier": 2.0},
            },
        }
    }


def test_generate_hypotheses(mock_settings):
    """Verify scheduler generates diverse parameter permutations for configured universe."""
    scheduler = AlphaDiscoveryScheduler(settings=mock_settings)
    hypotheses = scheduler.generate_hypotheses()

    assert len(hypotheses) > 0
    symbols = {h.symbol for h in hypotheses}
    assert "XAUUSD" in symbols
    assert "EURUSD" in symbols
    
    # Check diverse strategy types generated
    strat_types = {h.strategy_type for h in hypotheses}
    assert any("trend" in st or "donchian" in st for st in strat_types)
    assert any("sweep" in st for st in strat_types)


@pytest.mark.asyncio
async def test_evaluate_hypothesis_qualified(mock_settings):
    """Verify hypothesis with WFE > 0.60 and positive OOS Sharpe is qualified and persisted."""
    scheduler = AlphaDiscoveryScheduler(
        settings=mock_settings,
        min_wfe=0.60,
        min_oos_sharpe=0.50,
    )

    hypothesis = AlphaHypothesis(
        hypothesis_id="hyp_test_qualified",
        name="Test Donchian 20",
        strategy_type="btc_donchian_breakout",
        symbol="BTCUSD",
        parameters={"donchian_period": 20},
        description="Test breakout",
    )

    # Mock WalkForwardResult meeting institutional criteria
    mock_wfo_result = WalkForwardResult(
        folds=[],
        aggregate_is_sharpe=1.8,
        aggregate_oos_sharpe=1.2,
        overall_wfe=0.72,  # > 0.60
        is_overfit=False,
        total_oos_trades=15,
        oos_win_rate_pct=60.0,
    )

    with patch("scheduler.alpha_discovery_scheduler.WalkForwardEngine") as mock_engine_cls, \
         patch.object(scheduler, "_persist_proposal", new_callable=AsyncMock) as mock_persist:
        
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_wfo_result)
        mock_instance.generate_markdown_report = MagicMock(return_value="# Mock WFO Report")
        mock_engine_cls.return_value = mock_instance

        proposal = await scheduler.evaluate_hypothesis(hypothesis)

        assert proposal is not None
        assert mock_engine_cls.call_args.kwargs.get("mode") == "full"
        assert proposal.overall_wfe == 0.72
        assert proposal.aggregate_oos_sharpe == 1.2
        assert proposal.is_overfit is False
        assert proposal.status == "PROPOSED"
        assert len(scheduler.candidate_proposals) == 1
        mock_persist.assert_awaited_once_with(proposal)


@pytest.mark.asyncio
async def test_evaluate_hypothesis_rejected_low_wfe(mock_settings):
    """Verify hypothesis with WFE < 0.60 is rejected."""
    scheduler = AlphaDiscoveryScheduler(
        settings=mock_settings,
        min_wfe=0.60,
        min_oos_sharpe=0.50,
    )

    hypothesis = AlphaHypothesis(
        hypothesis_id="hyp_test_rejected",
        name="Test Degraded Strategy",
        strategy_type="trend_trailing",
        symbol="EURUSD",
        parameters={"sl_atr_multiplier": 1.0},
        description="Fails out of sample",
    )

    mock_wfo_result = WalkForwardResult(
        folds=[],
        aggregate_is_sharpe=2.1,
        aggregate_oos_sharpe=0.3,
        overall_wfe=0.41,  # < 0.60 FAIL
        is_overfit=True,
        total_oos_trades=10,
        oos_win_rate_pct=40.0,
    )

    with patch("scheduler.alpha_discovery_scheduler.WalkForwardEngine") as mock_engine_cls:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_wfo_result)
        mock_engine_cls.return_value = mock_instance

        proposal = await scheduler.evaluate_hypothesis(hypothesis)

        assert proposal is None
        assert len(scheduler.candidate_proposals) == 0


@pytest.mark.asyncio
async def test_run_discovery_cycle(mock_settings):
    """Verify run_discovery_cycle processes a batch of hypotheses without duplication."""
    scheduler = AlphaDiscoveryScheduler(settings=mock_settings)

    mock_wfo_result = WalkForwardResult(
        folds=[],
        aggregate_is_sharpe=1.5,
        aggregate_oos_sharpe=0.9,
        overall_wfe=0.68,
        is_overfit=False,
        total_oos_trades=8,
        oos_win_rate_pct=58.0,
    )

    with patch("scheduler.alpha_discovery_scheduler.WalkForwardEngine") as mock_engine_cls, \
         patch.object(scheduler, "_persist_proposal", new_callable=AsyncMock):
        
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_wfo_result)
        mock_instance.generate_markdown_report = MagicMock(return_value="# Report")
        mock_engine_cls.return_value = mock_instance

        found = await scheduler.run_discovery_cycle(max_evaluations=3)

        assert len(found) == 3
        assert len(scheduler._evaluated_hypothesis_ids) == 3


def test_alpha_discovery_config_parsing():
    """Verify AlphaDiscoveryScheduler parses settings from alpha_discovery section."""
    custom_settings = {
        "alpha_discovery": {
            "enabled": False,
            "interval_hours": 12.0,
            "lookback_days": 180,
            "is_window_days": 90,
            "oos_window_days": 30,
            "step_days": 30,
            "min_wfe": 0.70,
            "min_oos_sharpe": 0.80,
            "max_drawdown_limit": 15.0,
        }
    }
    scheduler = AlphaDiscoveryScheduler(settings=custom_settings)
    assert scheduler.enabled is False
    assert scheduler.interval_hours == 12.0
    assert scheduler.lookback_days == 180
    assert scheduler.is_window_days == 90
    assert scheduler.oos_window_days == 30
    assert scheduler.step_days == 30
    assert scheduler.min_wfe == 0.70
    assert scheduler.min_oos_sharpe == 0.80
    assert scheduler.max_drawdown_limit == 15.0


@pytest.mark.asyncio
async def test_alpha_discovery_disabled_start():
    """Verify start() exits immediately when enabled=False."""
    settings = {"alpha_discovery": {"enabled": False}}
    scheduler = AlphaDiscoveryScheduler(settings=settings)
    assert scheduler.enabled is False
    # Calling start should return immediately without blocking
    await scheduler.start()
    assert scheduler._running is False


@pytest.mark.asyncio
async def test_evaluate_hypothesis_rejected_high_drawdown(mock_settings):
    """Verify hypothesis with excellent WFE but excessive drawdown (> max_drawdown_limit) is rejected."""
    scheduler = AlphaDiscoveryScheduler(
        settings=mock_settings,
        min_wfe=0.60,
        min_oos_sharpe=0.50,
    )
    scheduler.max_drawdown_limit = 20.0

    hypothesis = AlphaHypothesis(
        hypothesis_id="hyp_test_high_dd",
        name="Test High Drawdown Strategy",
        strategy_type="btc_donchian_breakout",
        symbol="BTCUSD",
        parameters={"donchian_period": 20},
        description="High Sharpe but deep drawdown",
    )

    # Mock WalkForwardResult with high WFE/Sharpe but 28.5% max drawdown fold
    mock_fold = WalkForwardFold(
        fold_index=0,
        is_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        is_end=datetime(2026, 3, 1, tzinfo=timezone.utc),
        oos_start=datetime(2026, 3, 2, tzinfo=timezone.utc),
        oos_end=datetime(2026, 3, 22, tzinfo=timezone.utc),
        oos_metrics={"max_drawdown_pct": 28.5, "sharpe_ratio": 1.5},
    )
    mock_wfo_result = WalkForwardResult(
        folds=[mock_fold],
        aggregate_is_sharpe=2.0,
        aggregate_oos_sharpe=1.5,
        overall_wfe=0.75,  # > 0.60 PASS
        is_overfit=False,
        total_oos_trades=10,
        oos_win_rate_pct=60.0,
    )

    with patch("scheduler.alpha_discovery_scheduler.WalkForwardEngine") as mock_engine_cls:
        mock_instance = MagicMock()
        mock_instance.run = AsyncMock(return_value=mock_wfo_result)
        mock_engine_cls.return_value = mock_instance

        proposal = await scheduler.evaluate_hypothesis(hypothesis)

        assert proposal is None, "Hypothesis with MaxDD 28.5% > 20.0% limit must be rejected"
        assert len(scheduler.candidate_proposals) == 0


