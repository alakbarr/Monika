"""
Tests for PR-14: TradeProposal Schema and Financial Fortress Boundary.
Verifies strictly-typed schema validation, geometric invariants, reasoning hashing,
FortressAdmissionValidator checks, and RiskGate.evaluate_proposal integration.
"""

import pytest
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from risk.trade_proposal import TradeProposal, FortressAdmissionValidator
from risk.risk_gate import RiskGate, RiskVerdict


def test_valid_buy_proposal():
    prop = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        stop_loss=1.0820,
        take_profit=1.0910,
        lot_size=0.1,
        confluence_score=85.0,
    )
    assert prop.symbol == "EURUSD"
    assert prop.direction == "BUY"
    assert prop.entry_price == 1.0850
    assert prop.stop_loss < prop.entry_price < prop.take_profit


def test_valid_sell_proposal():
    prop = TradeProposal(
        symbol="USDJPY",
        direction="sell",
        entry_price=155.00,
        stop_loss=155.60,
        take_profit=153.80,
        lot_size=0.2,
    )
    assert prop.direction == "SELL"
    assert prop.take_profit < prop.entry_price < prop.stop_loss


def test_wait_proposal_allows_zeroes():
    prop = TradeProposal(
        symbol="GBPUSD",
        direction="WAIT",
        entry_price=0.0,
        stop_loss=0.0,
        take_profit=0.0,
        lot_size=0.0,
    )
    assert prop.direction == "WAIT"


def test_invalid_direction_raises():
    with pytest.raises(ValueError, match="Invalid direction"):
        TradeProposal(
            symbol="EURUSD",
            direction="HOLD",
            entry_price=1.0,
            stop_loss=0.9,
            take_profit=1.2,
        )


def test_buy_geometry_violation_raises():
    # SL > Entry
    with pytest.raises(ValueError, match="BUY geometry violation"):
        TradeProposal(
            symbol="EURUSD",
            direction="BUY",
            entry_price=1.0850,
            stop_loss=1.0890,
            take_profit=1.0920,
            lot_size=0.1,
        )


def test_sell_geometry_violation_raises():
    # TP > Entry
    with pytest.raises(ValueError, match="SELL geometry violation"):
        TradeProposal(
            symbol="USDJPY",
            direction="SELL",
            entry_price=155.00,
            stop_loss=156.00,
            take_profit=155.50,
            lot_size=0.1,
        )


def test_nan_or_inf_raises():
    with pytest.raises(ValueError, match="cannot be NaN or Infinite"):
        TradeProposal(
            symbol="EURUSD",
            direction="BUY",
            entry_price=float("nan"),
            stop_loss=1.0800,
            take_profit=1.0900,
        )


def test_reasoning_hash_generation():
    reason = "Bullish liquidity sweep at London open with H1 FVG confluence."
    prop = TradeProposal.from_analysis(
        symbol="XAUUSD",
        decision="BUY",
        entry_price=2350.0,
        stop_loss=2340.0,
        take_profit=2370.0,
        lot_size=0.05,
        reasoning_text=reason,
    )
    assert prop.reasoning_hash == TradeProposal.compute_reasoning_hash(reason)
    assert len(prop.reasoning_hash) == 64


def test_fortress_admission_accepts_valid():
    prop = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        stop_loss=1.0800,  # 50 pips risk
        take_profit=1.0950, # 100 pips reward (R:R = 2.0 >= 0.8)
        lot_size=0.1,
    )
    admitted, reasons = FortressAdmissionValidator.validate_proposal(prop)
    assert admitted is True
    assert len(reasons) == 0


def test_fortress_admission_rejects_stale():
    prop = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        lot_size=0.1,
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=400),
    )
    admitted, reasons = FortressAdmissionValidator.validate_proposal(prop, max_age_seconds=300.0)
    assert admitted is False
    assert any("expired" in r for r in reasons)


def test_fortress_admission_rejects_huge_lots():
    prop = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        lot_size=75.0,  # > 50 ceiling
    )
    admitted, reasons = FortressAdmissionValidator.validate_proposal(prop)
    assert admitted is False
    assert any("ceiling" in r for r in reasons)


def test_fortress_admission_rejects_terrible_rr():
    prop = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        stop_loss=1.0800,  # 50 pips risk
        take_profit=1.0870, # 20 pips reward (R:R = 0.4 < 0.8)
        lot_size=0.1,
    )
    admitted, reasons = FortressAdmissionValidator.validate_proposal(prop)
    assert admitted is False
    assert any("Risk:Reward" in r for r in reasons)


@pytest.mark.asyncio
async def test_risk_gate_evaluate_proposal_rejected_by_fortress():
    gate = RiskGate(settings={})
    stale_prop = TradeProposal(
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        stop_loss=1.0800,
        take_profit=1.0950,
        lot_size=0.1,
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=600),
    )
    mock_session = AsyncMock()
    verdict = await gate.evaluate_proposal(mock_session, stale_prop)
    assert verdict.approved is False
    assert "fortress_admission" in verdict.checks_failed
    assert any("expired" in r for r in verdict.rejection_reasons)


@pytest.mark.asyncio
async def test_risk_gate_evaluate_proposal_wait():
    gate = RiskGate(settings={})
    wait_prop = TradeProposal(
        symbol="EURUSD",
        direction="WAIT",
    )
    mock_session = AsyncMock()
    verdict = await gate.evaluate_proposal(mock_session, wait_prop)
    assert verdict.approved is True
    assert "fortress_admission" in verdict.checks_passed
