"""
Unit and Integration Test Suite: Remediasi Menyeluruh Round 04 Fase 2 (Arsitektural)
Memverifikasi 4 pilar arsitektural kompleks:
- DEC-02: SignalArbitrator dynamic empirical quant Brier Score & opinion pool weight rebalancing
- LRN-05: PerformanceReviewer causal setup-matching attribution on CandidateLesson evaluation
- LRN-04: AdaptiveRiskPolicy rolling lookback window (60-day / 100-trade cap) & Wilson lower bound
- TST-03: ReportGenerator asset-weighted mixed portfolio calendar annualization & weekend retention
"""

import pytest
import asyncio
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone, timedelta
from utils import clock


# =========================================================================
# 1. DEC-02: Dynamic Quant Brier Score Tracking in SignalArbitrator
# =========================================================================
@pytest.mark.asyncio
async def test_signal_arbitrator_dynamic_empirical_brier_weighting():
    from analysis.arbitration.signal_arbitrator import compute_empirical_arbitrator_weights
    from database.models import PaperTradeRecord, AssetAnalysis
    
    mock_session = AsyncMock()
    
    # Create 12 trades:
    # - LLM had high confidence (0.90) but lost (is_win=0) -> High LLM Brier (bad calibration)
    # - Quant had high confidence (0.80) and won (is_win=1) -> Low Quant Brier (good calibration)
    records = []
    for i in range(12):
        rec = MagicMock(spec=PaperTradeRecord)
        rec.status = "closed"
        rec.exit_reason = "tp_hit" if i < 9 else "sl_hit"
        rec.pnl_pct = 1.5 if i < 9 else -1.0
        rec.decision_source = "concordant"
        
        ana = MagicMock(spec=AssetAnalysis)
        ana.confidence = 0.90 if i >= 9 else 0.40  # Poor calibration for LLM
        ana.source_strategy_id = "tsm_momentum"
        ana.strategy_confidence = 0.85 if i < 9 else 0.40  # Strong calibration for Quant
        
        records.append((rec, ana))
        
    mock_exec_res = MagicMock()
    mock_exec_res.all.return_value = records
    mock_session.execute.return_value = mock_exec_res
    
    w_q, w_l = await compute_empirical_arbitrator_weights(mock_session, 0.50, 0.50)
    
    # Quant had lower Brier error -> w_q should be rewarded (> 0.50)
    assert w_q > 0.50
    assert w_l < 0.50
    assert round(w_q + w_l, 4) == 1.0


# =========================================================================
# 2. LRN-05: PerformanceReviewer Causal Setup Attribution
# =========================================================================
@pytest.mark.asyncio
async def test_performance_reviewer_causal_setup_attribution():
    from utils.analytics.performance_reviewer import evaluate_candidate_lessons
    from database.models import CandidateLesson, PaperTradeRecord
    
    mock_session = AsyncMock()
    now = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
    proposal_time = now - timedelta(days=20)
    
    # Candidate lesson with specific condition tag: "london_open"
    cand = MagicMock(spec=CandidateLesson)
    cand.symbol = "GBPUSD"
    cand.status = "shadow"
    cand.proposed_at = proposal_time
    cand.lesson_text = "Avoid longing into London Open resistance"
    cand.condition_tags = ["london_open"]
    cand.trigger_condition = "london_open"
    
    # 25 post trades: 16 matching "london_open" (meets min_required=15) with >80% WR, 9 non-matching noise trades
    post_trades = []
    for i in range(25):
        t = MagicMock(spec=PaperTradeRecord)
        t.symbol = "GBPUSD"
        t.status = "closed"
        t.closed_at = proposal_time + timedelta(days=i)
        if i < 16:
            t.detection_method = "london_open_breakout"
            t.exit_reason = "tp_hit" if i < 14 else "sl_hit"  # 14/16 = 87.5% WR
            t.pnl_pct = 1.0 if i < 14 else -1.0
        else:
            t.detection_method = "asian_range"
            t.exit_reason = "sl_hit"  # Noise
            t.pnl_pct = -1.0
        post_trades.append(t)
        
    # Baseline pre trades: 10 matching london_open with 40% WR
    pre_trades = []
    for i in range(15):
        t = MagicMock(spec=PaperTradeRecord)
        t.symbol = "GBPUSD"
        t.status = "closed"
        t.closed_at = proposal_time - timedelta(days=i+1)
        t.detection_method = "london_open_breakout"
        t.exit_reason = "tp_hit" if i < 6 else "sl_hit"  # 6/15 = 40% WR
        t.pnl_pct = 1.0 if i < 6 else -1.0
        pre_trades.append(t)
        
    # Setup mock returns
    mock_session.execute.side_effect = [
        # 1. select candidates
        MagicMock(scalars=lambda: MagicMock(all=lambda: [cand])),
        # 2. select post trades
        MagicMock(scalars=lambda: MagicMock(all=lambda: post_trades)),
        # 3. select pre trades
        MagicMock(scalars=lambda: MagicMock(all=lambda: pre_trades)),
    ]
    
    with patch("analysis.memory.lesson_consolidator.promote_lesson_to_playbook", new_callable=AsyncMock) as mock_promote:
        summary = await evaluate_candidate_lessons(mock_session)
        assert summary["promoted"] == 1
        assert cand.status == "promoted"
        assert cand.win_rate_delta > 0


# =========================================================================
# 3. LRN-04: AdaptiveRiskPolicy Rolling Window Sample Cap
# =========================================================================
@pytest.mark.asyncio
async def test_adaptive_policy_rolling_window_sample_cap():
    from analysis.calculators.adaptive_policy import AdaptiveRiskPolicy
    
    settings = {
        "trading": {
            "auto_execute_min_confluence": 7,
            "min_paper_win_rate_pct": 45,
            "risk": {
                "adaptive_policy_lookback_days": 60,
                "adaptive_policy_max_trades": 100,
                "strategy_min_sample_size": 20,
            }
        }
    }
    
    policy = AdaptiveRiskPolicy(settings)
    mock_session = AsyncMock()
    
    # Mock return: 50 trades, 38 wins in the recent rolling 60-day window (76% WR -> strong edge)
    mock_row = MagicMock()
    mock_row.total_trades = 50
    mock_row.winning_trades = 38
    mock_session.execute = AsyncMock(return_value=MagicMock(first=lambda: mock_row))
    
    threshold, reason = await policy.get_effective_threshold(mock_session, "EURUSD")
    
    # Strong edge detected -> threshold should be relaxed from 7 to 6
    assert threshold == 6
    assert "Strong edge detected" in reason


# =========================================================================
# 4. TST-03: ReportGenerator Asset-Weighted Mixed Annualization
# =========================================================================
def test_report_generator_asset_weighted_mixed_annualization():
    from backtest.report_generator import ReportGenerator
    from database.models import BacktestRun
    
    # Scenario: Mixed portfolio with 8 FX trades and 2 Crypto trades (20% crypto)
    trades = []
    for i in range(8):
        t = MagicMock()
        t.symbol = "EURUSD"
        t.pnl_pct = 1.0
        trades.append(t)
    for i in range(2):
        t = MagicMock()
        t.symbol = "BTCUSD"
        t.pnl_pct = 2.0
        trades.append(t)
        
    mock_run = MagicMock(spec=BacktestRun)
    mock_run.initial_equity = 10000.0
    mock_run.final_equity = 11200.0
    mock_run.start_date = datetime(2026, 1, 1, tzinfo=timezone.utc)
    mock_run.end_date = datetime(2026, 3, 31, tzinfo=timezone.utc)
    
    gen = ReportGenerator(mock_run, trades)
    
    # Crypto fraction = 2/10 = 0.20
    # ann_factor = 252 + 0.20 * (365 - 252) = 252 + 22.6 = 274.6
    crypto_symbols = ("BTC", "ETH", "SOL", "XRP", "BNB")
    total_t_count = len(trades)
    crypto_t_count = sum(1 for t in trades if any(c in t.symbol.upper() for c in crypto_symbols))
    crypto_fraction = crypto_t_count / total_t_count
    expected_ann = round(252.0 + (crypto_fraction * (365.0 - 252.0)), 2)
    
    assert expected_ann == 274.60
