"""
Comprehensive Unit Tests for Round 1 Phase 2 Remediation:
- P2-1 (BT-09): Dynamic Broker Spread & Session Friction Calibration in OutcomeEvaluator
- P2-2 (BT-10): Walk-Forward Optimization (WFO) Engine & WFE Overfitting Guard
- P2-3 (AX6-04): Bayesian Thompson Sampling Multi-Armed Bandit in PromptABTest
- P2-4 (AX1-03 & AX6-02): Dynamic Empirical Concordant Risk Multiplier & Structured Causal Tag Matching
"""
import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from database.models import BacktestTrade, PaperTradeRecord, CandidateLesson, SystemConfig
from backtest.outcome_evaluator import OutcomeEvaluator
from backtest.walk_forward_engine import WalkForwardEngine, WalkForwardFold, WalkForwardResult
from utils.llm.prompt_ab_test import PromptABTest
from analysis.arbitration.signal_arbitrator import SignalArbitrator, ArbitrationResult
from utils.analytics.performance_reviewer import evaluate_candidate_lessons


# ============================================================================
# P2-1 (BT-09): Dynamic Friction & Spread Calibration in OutcomeEvaluator
# ============================================================================

@pytest.mark.asyncio
async def test_outcome_evaluator_custom_friction_and_db_calibration():
    """Verify OutcomeEvaluator accepts custom broker friction and calibrates from DB logs."""
    custom_profile = {
        "EURUSD": {"spread_pips": 2.5, "slippage_pips": 1.0}
    }
    evaluator = OutcomeEvaluator(custom_friction_profile=custom_profile)
    assert evaluator.friction_profile["EURUSD"]["spread_pips"] == 2.5
    assert evaluator.friction_profile["EURUSD"]["slippage_pips"] == 1.0

    start = datetime(2026, 8, 1, 14, 0, 0, tzinfo=timezone.utc)
    trade = BacktestTrade(
        symbol="EURUSD",
        direction="buy",
        entry_time=start,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
    )
    trade.executed_lots = 1.0

    outcome = evaluator._calculate_outcome(trade, start + timedelta(hours=2), 1.1100, "tp_hit", apply_costs=True)
    assert outcome["exit_reason"] == "tp_hit"
    assert outcome["friction_pips"] >= 3.5  # 2.5 spread + 1.0 slippage

    # Test calibrate_from_db
    mock_session = AsyncMock()
    mock_trade1 = MagicMock(symbol="EURUSD", slippage_applied=1.2, closed_at=start)
    mock_trade2 = MagicMock(symbol="EURUSD", slippage_applied=1.8, closed_at=start)
    mock_trade3 = MagicMock(symbol="EURUSD", slippage_applied=1.5, closed_at=start)
    mock_trade4 = MagicMock(symbol="EURUSD", slippage_applied=1.1, closed_at=start)
    mock_trade5 = MagicMock(symbol="EURUSD", slippage_applied=1.4, closed_at=start)

    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = [mock_trade1, mock_trade2, mock_trade3, mock_trade4, mock_trade5]
    mock_session.execute.return_value = mock_exec

    updated_prof = await evaluator.calibrate_from_db(mock_session, lookback_days=14)
    assert updated_prof["EURUSD"]["slippage_pips"] == 1.4  # Average of 1.2, 1.8, 1.5, 1.1, 1.4


# ============================================================================
# P2-2 (BT-10): Walk-Forward Optimization (WFO) Engine
# ============================================================================

def test_walk_forward_engine_fold_generation():
    """Verify WalkForwardEngine generates rolling chronological folds without lookahead overlap."""
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)  # 181 days

    engine = WalkForwardEngine(
        start_date=start,
        end_date=end,
        is_window_days=90,
        oos_window_days=30,
        step_days=30,
        purge_days=0,
    )

    folds = engine.generate_folds()
    assert len(folds) >= 3

    for is_s, is_e, oos_s, oos_e in folds:
        # Strict chronological gating
        assert is_s < is_e
        assert is_e == oos_s
        assert oos_s < oos_e
        assert oos_e <= end
        assert (is_e - is_s).days == 90
        assert (oos_e - oos_s).days in (30, (end - oos_s).days)


@pytest.mark.asyncio
async def test_walk_forward_engine_run_and_wfe_calculation():
    """Verify WalkForwardEngine executes simulations, calculates WFE, and stitches OOS equity curve."""
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)

    engine = WalkForwardEngine(
        start_date=start,
        end_date=end,
        is_window_days=60,
        oos_window_days=30,
        step_days=30,
    )

    mock_trade_is = BacktestTrade(symbol="EURUSD", direction="buy", entry_time=start, entry_price=1.10, exit_price=1.12, pnl_pct=2.0, exit_reason="tp_hit")
    mock_trade_oos = BacktestTrade(symbol="EURUSD", direction="buy", entry_time=start + timedelta(days=60), entry_price=1.12, exit_price=1.14, pnl_pct=1.5, exit_reason="tp_hit")

    with patch("backtest.walk_forward_engine.PointInTimeBacktestEngine") as MockPITE:
        mock_inst = AsyncMock()
        # Returns simulated trades for IS and OOS
        mock_inst.run_simulation.side_effect = [
            [mock_trade_is, mock_trade_is], [mock_trade_oos],  # Fold 1 IS, OOS
            [mock_trade_is], [mock_trade_oos],                # Fold 2 IS, OOS
            [mock_trade_is], [mock_trade_oos],                # Fold 3 IS, OOS
        ]
        MockPITE.return_value = mock_inst

        result = await engine.run()
        assert isinstance(result, WalkForwardResult)
        assert len(result.folds) >= 2
        assert result.total_oos_trades >= 2
        assert result.overall_wfe > 0.0
        assert result.oos_win_rate_pct == 100.0
        assert result.is_overfit is False

        md_rep = engine.generate_markdown_report(result)
        assert "# Walk-Forward Optimization (WFO) Report" in md_rep
        assert "Overall Walk-Forward Efficiency (WFE)" in md_rep


# ============================================================================
# P2-3 (AX6-04): Bayesian Thompson Sampling Multi-Armed Bandit
# ============================================================================

@pytest.mark.asyncio
async def test_prompt_ab_test_thompson_sampling_bandit():
    """Verify PromptABTest dynamically updates Beta posteriors and samples optimal variant via Thompson Sampling."""
    test = PromptABTest(test_name="system_prompt_v2", min_warmup_samples=5)
    mock_session = AsyncMock()

    # 1. Warmup behavior (samples < 5) -> fallback heuristic
    mock_exec_none = MagicMock()
    mock_exec_none.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_exec_none

    var = await test.get_variant_bandit(mock_session)
    assert var in ('A', 'B')

    # 2. Record multiple wins for variant B, and losses for variant A
    stored_mab_state = {
        "A": {"alpha": 1.0, "beta": 1.0, "count": 0, "total_pnl": 0.0},
        "B": {"alpha": 1.0, "beta": 1.0, "count": 0, "total_pnl": 0.0}
    }

    def mock_exec_side_effect(stmt):
        m = MagicMock()
        params = list(getattr(stmt.compile(), 'params', {}).values())
        if any("mab_bandit" in str(p) for p in params):
            m.scalar_one_or_none.return_value = SystemConfig(key="mab_bandit_system_prompt_v2", value=json.dumps(stored_mab_state))
        else:
            m.scalar_one_or_none.return_value = None
        return m

    mock_session.execute.side_effect = mock_exec_side_effect

    # Record 8 wins for B (pnl +1.5%)
    for _ in range(8):
        await test.record_outcome(mock_session, variant="B", outcome="win", pnl_pct=1.5)
        # Manually emulate DB persistence
        stored_mab_state["B"]["alpha"] += 1.0
        stored_mab_state["B"]["count"] += 1
        stored_mab_state["B"]["total_pnl"] += 1.5

    # Record 8 losses for A (pnl -1.0%)
    for _ in range(8):
        await test.record_outcome(mock_session, variant="A", outcome="loss", pnl_pct=-1.0)
        stored_mab_state["A"]["beta"] += 1.0
        stored_mab_state["A"]["count"] += 1
        stored_mab_state["A"]["total_pnl"] -= 1.0

    state = await test.get_bandit_state(mock_session)
    assert state["B"]["expected_win_rate"] > state["A"]["expected_win_rate"]

    # Thompson Sampling should now predominantly sample 'B' due to high Beta(9, 1) vs Beta(1, 9)
    samples = [await test.get_variant_bandit(mock_session) for _ in range(20)]
    assert samples.count("B") >= 18


# ============================================================================
# P2-4 (AX1-03 & AX6-02): Dynamic Concordant Multiplier & Structured Causal Tags
# ============================================================================

@pytest.mark.asyncio
async def test_signal_arbitrator_dynamic_concordant_multiplier():
    """Verify SignalArbitrator dynamically scales concordant risk multiplier based on historical win rate."""
    arbitrator = SignalArbitrator(arbitration_cfg={"dynamic_concordant_multiplier": True})
    mock_session = AsyncMock()

    # Case 1: High empirical win rate (70% win rate across 20 trades) -> Scales to 1.25x
    winning_trades = [
        MagicMock(status="closed", decision_source="concordant", exit_reason="tp_hit" if i < 14 else "sl_hit", pnl_pct=1.0 if i < 14 else -1.0, was_profitable=i < 14)
        for i in range(20)
    ]
    mock_exec1 = MagicMock()
    mock_exec1.scalars.return_value.all.return_value = winning_trades
    mock_session.execute.return_value = mock_exec1

    mult = await arbitrator._get_empirical_concordant_multiplier(mock_session, default_mult=1.15, max_mult=1.25)
    assert mult == 1.25

    # Case 2: Poor empirical win rate (30% win rate across 20 trades) -> Dampens to 1.00x
    losing_trades = [
        MagicMock(status="closed", decision_source="concordant", exit_reason="tp_hit" if i < 6 else "sl_hit", pnl_pct=1.0 if i < 6 else -1.0, was_profitable=i < 6)
        for i in range(20)
    ]
    mock_exec2 = MagicMock()
    mock_exec2.scalars.return_value.all.return_value = losing_trades
    mock_session.execute.return_value = mock_exec2

    mult_low = await arbitrator._get_empirical_concordant_multiplier(mock_session, default_mult=1.15, max_mult=1.25)
    assert mult_low == 1.00


@pytest.mark.asyncio
async def test_performance_reviewer_structured_confluence_tag_matching():
    """Verify evaluate_candidate_lessons accurately matches structured confluence_factors_json tags."""
    mock_session = AsyncMock()
    proposed_time = datetime.now(timezone.utc) - timedelta(days=10)

    candidate = CandidateLesson(
        id=10,
        symbol="EURUSD",
        lesson_text="- Buy on H4 OrderBlock mitigation",
        status="shadow",
        proposed_at=proposed_time,
        evaluated_trades_count=0
    )
    # Target tag matches order_block
    candidate.condition_tags = json.dumps(["order_block"])

    # 16 post trades containing order_block in confluence_factors_json (meets min_required=15)
    post_trades = [
        MagicMock(
            symbol="EURUSD",
            status="closed",
            exit_reason="tp_hit" if i < 14 else "sl_hit",
            closed_at=proposed_time + timedelta(hours=i),
            pnl_pct=1.0 if i < 14 else -1.0,
            confluence_factors_json=json.dumps(["order_block", "fvg"]) if i < 16 else json.dumps(["trend"]),
            detection_method="standard",
            decision_source="concordant"
        )
        for i in range(20)
    ]

    # Baseline pre trades
    pre_trades = [
        MagicMock(
            symbol="EURUSD",
            status="closed",
            exit_reason="tp_hit" if i < 8 else "sl_hit",
            closed_at=proposed_time - timedelta(hours=i),
            pnl_pct=1.0 if i < 8 else -1.0,
            confluence_factors_json=json.dumps(["order_block"]),
            detection_method="standard",
            decision_source="concordant"
        )
        for i in range(20)
    ]

    mock_exec1 = MagicMock()
    mock_exec1.scalars.return_value.all.return_value = [candidate]

    mock_exec2 = MagicMock()
    mock_exec2.scalars.return_value.all.return_value = post_trades

    mock_exec3 = MagicMock()
    mock_exec3.scalars.return_value.all.return_value = pre_trades

    mock_session.execute.side_effect = [mock_exec1, mock_exec2, mock_exec3]

    with patch("analysis.memory.lesson_consolidator.promote_lesson_to_playbook", new_callable=AsyncMock) as mock_promote:
        summary = await evaluate_candidate_lessons(mock_session)
        assert summary["promoted"] == 1
        assert candidate.status == "promoted"
        assert mock_promote.called
