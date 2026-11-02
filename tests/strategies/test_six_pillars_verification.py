import math
from datetime import datetime, timezone
import numpy as np
import pytest
from unittest.mock import AsyncMock

from monika.application.analysis.strategies.base_strategy import EdgeSignal
from monika.application.analysis.strategies.evidence_store import (
    EvidenceStatus,
    RegimeEvidence,
    StrategyEvidence,
    StrategyEvidenceStore,
)
from monika.application.analysis.strategies.pretrade_gate import (
    evaluate_pretrade_gate,
    _get_estimated_round_trip_cost,
)
from monika.domain.execution.bracket_optimizer import BracketOptimizer
from monika.domain.execution.order_emulator import ClientOrderEmulator, TrackedPosition
from monika.domain.risk.correlation_matrix import DynamicCorrelationMatrix
from monika.domain.risk.portfolio_optimizer import PortfolioOptimizer
from monika.domain.risk.risk_gate import RiskGate
from monika.domain.risk.position_sizing import SizingResult


def test_evidence_store_composite_symbol_lookup(tmp_path):
    store_file = tmp_path / "test_evidence.json"
    store = StrategyEvidenceStore(file_path=store_file)

    # 1. Record evidence for EURUSD (positive) and AUDUSD (negative)
    store.record_evidence(
        strategy_id="test_strat",
        symbol="EURUSD",
        timeframe="H1",
        data_window_end=datetime.now(timezone.utc),
        gross_return=0.15,
        total_trades=20,
    )
    store.record_evidence(
        strategy_id="test_strat",
        symbol="AUDUSD",
        timeframe="H1",
        data_window_end=datetime.now(timezone.utc),
        gross_return=-0.08,
        total_trades=15,
    )

    # 2. Check composite lookup
    ev_eur = store.get_evidence("test_strat", "EURUSD")
    assert ev_eur is not None
    assert ev_eur.symbol == "EURUSD"
    assert ev_eur.gross_return == 0.15

    ev_aud = store.get_evidence("test_strat", "AUDUSD")
    assert ev_aud is not None
    assert ev_aud.symbol == "AUDUSD"
    assert ev_aud.gross_return == -0.08

    # 3. Eligibility check: EURUSD approved, AUDUSD rejected due to negative gross return
    ok_eur, reason_eur = store.is_strategy_eligible_to_trade("test_strat", symbol="EURUSD")
    assert ok_eur is True

    ok_aud, reason_aud = store.is_strategy_eligible_to_trade("test_strat", symbol="AUDUSD")
    assert ok_aud is False
    assert "negative gross return" in reason_aud

    # 4. Regime underperformance rejection
    store.record_evidence(
        strategy_id="regime_strat",
        symbol="XAUUSD",
        timeframe="H1",
        data_window_end=datetime.now(timezone.utc),
        gross_return=0.20,
        total_trades=30,
        regime_metrics={
            "VOLATILE_CHOP": {
                "sharpe": -1.5,
                "win_rate": 0.20,
                "profit_factor": 0.65,
                "trades": 10,
            }
        },
    )
    val_ok, val_reason = store.validate_strategy_for_trade("regime_strat", regime="VOLATILE_CHOP", symbol="XAUUSD")
    assert val_ok is False
    assert "underperforms in regime VOLATILE_CHOP" in val_reason


@pytest.mark.asyncio
async def test_pretrade_gate_microstructure_and_toxic_elimination():
    mock_session = AsyncMock()
    settings = {"trading": {"risk": {"rollover_protection_enabled": False}}}

    # 1. Toxic strategy rejection
    toxic_sig = EdgeSignal(
        strategy_id="liquidity_sweep",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
    )
    allowed, reason = await evaluate_pretrade_gate(mock_session, "EURUSD", settings, signal=toxic_sig)
    assert not allowed
    assert "toxic_strategy_eliminated" in reason

    # 2. Toxic pair rejection (asian_range_fade on EURUSD)
    toxic_pair_sig = EdgeSignal(
        strategy_id="asian_range_fade",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
    )
    allowed, reason = await evaluate_pretrade_gate(mock_session, "EURUSD", settings, signal=toxic_pair_sig)
    assert not allowed
    assert "toxic_pair_eliminated" in reason

    # 3. Spread-survival floor breach (stop loss is microscopic compared to round-trip cost)
    # EURUSD round-trip is 0.00012. If SL distance is 0.00020, cost is 60% of SL (> 20% limit)
    micro_sl_sig = EdgeSignal(
        strategy_id="test_strat",
        symbol="EURUSD",
        direction="buy",
        valid=True,
        confidence=0.8,
        entry_price=1.0850,
        stop_loss=1.0848,
        take_profit=1.0950,
    )
    allowed, reason = await evaluate_pretrade_gate(mock_session, "EURUSD", settings, signal=micro_sl_sig)
    assert not allowed
    assert "spread_survival_floor_breached" in reason


@pytest.mark.asyncio
async def test_order_emulator_near_tp_profit_lock():
    emulator = ClientOrderEmulator(settings={})
    pos = TrackedPosition(
        ticket=101,
        symbol="EURUSD",
        direction="buy",
        entry_price=1.0800,
        current_sl=1.0750,
        current_tp=1.0900,  # TP distance = 0.0100 (100 pips)
        atr=0.0050,
    )

    # 1. At 1.0850 (50% TP), Near-TP lock should not trigger yet
    pos.high_watermark = 1.0850
    adj = await emulator._evaluate_tick_for_position(pos, bid=1.0850, ask=1.0851, last=1.0850)
    assert pos.current_sl == 1.0750 or (adj and adj["reason"] != "near_tp_lock")

    # 2. At 1.0891 (91% of TP reached), Near-TP lock ratchets SL to entry + 0.45 * TP_dist = 1.0845
    pos.high_watermark = 1.0891
    adj = await emulator._evaluate_tick_for_position(pos, bid=1.0891, ask=1.0892, last=1.0891)
    assert adj is not None
    assert "near_tp_lock" in adj["reason"]
    assert adj["new_sl"] == pytest.approx(1.0800 + 0.45 * 0.0100, abs=1e-5)


def test_portfolio_optimizer_position_return_space():
    cov = np.array(
        [
            [0.04, -0.02],
            [-0.02, 0.04],
        ]
    )
    # Long asset 0 (+1), Short asset 1 (-1)
    # Signed covariance: D * Sigma * D
    # Expected off-diagonal: (-1) * (-0.02) = +0.02 (positive position-space correlation)
    cov_pos = PortfolioOptimizer.compute_position_return_covariance(cov, [1, -1])
    assert cov_pos[0, 1] == pytest.approx(0.02, abs=1e-6)
    assert cov_pos[1, 0] == pytest.approx(0.02, abs=1e-6)
    assert cov_pos[0, 0] == pytest.approx(0.04, abs=1e-6)
    assert cov_pos[1, 1] == pytest.approx(0.04, abs=1e-6)


def test_correlation_matrix_schmitt_trigger_fused():
    matrix = DynamicCorrelationMatrix(rolling_days=30, correlation_threshold=0.60)
    positions = [
        {"symbol": "EURUSD", "direction": "BUY", "volume": 1.0},
        {"symbol": "GBPUSD", "direction": "BUY", "volume": 1.0},
        {"symbol": "AUDUSD", "direction": "BUY", "volume": 1.0},
    ]
    # Synthetic correlation where all pairs have 0.80 correlation (edge density = 1.0 >= 0.32)
    corr_map = {
        "EURUSD": {"GBPUSD": 0.80, "AUDUSD": 0.80},
        "GBPUSD": {"EURUSD": 0.80, "AUDUSD": 0.80},
        "AUDUSD": {"EURUSD": 0.80, "GBPUSD": 0.80},
    }
    heat_fused = matrix.calculate_portfolio_heat(positions, corr_map)
    assert heat_fused["is_fused"] is True
    assert heat_fused["status"] == "fused"
    assert heat_fused["edge_density"] == 1.0

    # Low correlation: edge density = 0.0 <= 0.18 -> exits fused state
    low_corr_map = {
        "EURUSD": {"GBPUSD": 0.10, "AUDUSD": 0.10},
        "GBPUSD": {"EURUSD": 0.10, "AUDUSD": 0.10},
        "AUDUSD": {"EURUSD": 0.10, "GBPUSD": 0.10},
    }
    heat_safe = matrix.calculate_portfolio_heat(positions, low_corr_map)
    assert heat_safe["is_fused"] is False
    assert heat_safe["status"] == "normal"


@pytest.mark.asyncio
async def test_risk_gate_asymmetric_exit_pass_through():
    gate = RiskGate(settings={"paper_trading": {"enabled": True}})
    session = AsyncMock()
    sizing = SizingResult(
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=10.0,
        sl_distance_pips=1000.0,
        pip_value_per_lot=1.0,
        raw_lots=0.5,
        recommended_lots=0.5,
        rr_ratio=2.0,
        is_valid=True,
    )
    # Evaluating a "close" action must pass immediately via asymmetric exit pass-through
    verdict = await gate.evaluate(
        session=session,
        symbol="XAUUSD",
        direction="close",
        sizing=sizing,
        account_equity=10000.0,
    )
    assert verdict.approved is True
    assert "asymmetric_exit_pass_through" in verdict.checks_passed


def test_bracket_coherence_validation():
    # 1. Valid BUY bracket
    ok, reason = BracketOptimizer.validate_bracket_coherence(
        symbol="EURUSD", direction="buy", entry_price=1.0800, stop_loss=1.0750, take_profit=1.0900, min_rr=1.5
    )
    assert ok is True
    assert reason == "coherent"

    # 2. Inverted BUY bracket (SL above entry)
    ok_inv, reason_inv = BracketOptimizer.validate_bracket_coherence(
        symbol="EURUSD", direction="buy", entry_price=1.0800, stop_loss=1.0850, take_profit=1.0900
    )
    assert ok_inv is False
    assert "incoherent_buy_geometry" in reason_inv

    # 3. Sub-minimum R:R
    ok_rr, reason_rr = BracketOptimizer.validate_bracket_coherence(
        symbol="EURUSD", direction="buy", entry_price=1.0800, stop_loss=1.0700, take_profit=1.0850, min_rr=1.5
    )
    assert ok_rr is False
    assert "sub_minimum_rr" in reason_rr
