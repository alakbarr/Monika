# ==============================================================================
# File: tests/analysis/test_hypothesis_and_evidence.py
# Monika Hypothesis Registry & Evidence Store Test Suite
# ==============================================================================

from datetime import datetime, timezone, timedelta
import pytest

from analysis.strategies.hypothesis_registry import (
    HypothesisRegistry,
    HypothesisStatus,
)
from analysis.strategies.evidence_store import (
    StrategyEvidenceStore,
    EvidenceStatus,
    compute_sizing_corrected_breakeven_bps,
)


@pytest.fixture
def hyp_registry(tmp_path):
    storage_file = tmp_path / "hypotheses.json"
    return HypothesisRegistry(storage_path=storage_file)


@pytest.fixture
def ev_store(tmp_path):
    storage_file = tmp_path / "evidence.json"
    return StrategyEvidenceStore(file_path=storage_file)


def test_hypothesis_registration_and_update(hyp_registry):
    hyp = hyp_registry.register(
        thesis="Asian liquidity sweep into London trend expansion",
        signal_definition="Sweep high of Asian session + 5-min order block rejection",
        target_universe=["GBPUSD", "EURUSD"],
    )
    assert hyp.status == HypothesisStatus.EXPLORING
    assert hyp.hypothesis_id is not None

    # Transition to TESTING then VALIDATED
    updated = hyp_registry.update_status(hyp.hypothesis_id, HypothesisStatus.VALIDATED, metrics={"sharpe": 1.85})
    assert updated.status == HypothesisStatus.VALIDATED
    assert updated.metrics["sharpe"] == 1.85


def test_hypothesis_deduplication_of_rejected_ideas(hyp_registry):
    hyp = hyp_registry.register(
        thesis="RSI oversold crossover in extreme downtrend",
        signal_definition="RSI(14) < 20 and SMA(50) falling",
        target_universe=["XAUUSD"],
    )
    # Reject it with note
    hyp_registry.update_status(
        hyp.hypothesis_id,
        HypothesisStatus.REJECTED,
        invalidation_notes="Severe drawdown catching falling knives",
    )

    # Check new similar proposal
    is_dup, reason = hyp_registry.is_duplicate_or_rejected(
        "RSI oversold crossover in extreme downtrend with falling moving average",
        similarity_threshold=0.60,
    )
    assert is_dup is True
    assert "Matches rejected hypothesis" in reason


def test_hypothesis_paper_incubation_promotion(hyp_registry):
    hyp = hyp_registry.register(
        thesis="NY breakout momentum",
        signal_definition="Donchian breakout",
        target_universe=["BTCUSD"],
    )
    hyp_registry.update_status(hyp.hypothesis_id, HypothesisStatus.INCUBATING)

    # Record 15 paper trades (10 wins, 5 losses -> 66.7% win rate)
    for _ in range(10):
        hyp_registry.record_paper_trade(hyp.hypothesis_id, is_win=True)
    for _ in range(4):
        hyp_registry.record_paper_trade(hyp.hypothesis_id, is_win=False)

    # 14 trades: still incubating
    curr = hyp_registry._hypotheses[hyp.hypothesis_id]
    assert curr.status == HypothesisStatus.INCUBATING

    # 15th trade is win -> should promote to ACTIVE
    promoted = hyp_registry.record_paper_trade(hyp.hypothesis_id, is_win=True)
    assert promoted.status == HypothesisStatus.ACTIVE


def test_compute_sizing_corrected_breakeven_bps():
    # 20% return over 100 trades with size 1.0 -> ln(1.20) / (2 * 100) * 10000 = 0.1823 / 200 * 10000 = 9.11 bps
    bps = compute_sizing_corrected_breakeven_bps(gross_return=0.20, total_trades=100, avg_position_size=1.0)
    assert bps == pytest.approx(9.12, abs=0.1)

    # Concurrency penalty test (max_concurrent_positions = 2 applies 0.75 factor)
    bps_conc = compute_sizing_corrected_breakeven_bps(
        gross_return=0.20, total_trades=100, avg_position_size=1.0, max_concurrent_positions=2
    )
    assert bps_conc < bps
    assert bps_conc == pytest.approx(bps * 0.75, abs=0.1)


def test_evidence_store_decay_and_gate(ev_store):
    now = datetime.now(timezone.utc)

    # Fresh evidence (30 days ago)
    ev_fresh = ev_store.record_evidence(
        strategy_id="strat_fresh",
        symbol="EURUSD",
        timeframe="H1",
        data_window_end=now - timedelta(days=30),
        gross_return=0.25,
        total_trades=80,
    )
    assert ev_fresh.status == EvidenceStatus.FRESH
    ok, _ = ev_store.is_strategy_eligible_to_trade("strat_fresh")
    assert ok is True

    # Stale evidence (200 days ago)
    ev_stale = ev_store.record_evidence(
        strategy_id="strat_stale",
        symbol="XAUUSD",
        timeframe="H4",
        data_window_end=now - timedelta(days=200),
        gross_return=0.30,
        total_trades=50,
    )
    assert ev_stale.status == EvidenceStatus.STALE
    ok_stale, reason = ev_store.is_strategy_eligible_to_trade("strat_stale")
    assert ok_stale is False
    assert "STALE" in reason
