# ==============================================================================
# File: tests/execution/test_two_phase_execution.py
# ==============================================================================

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest

from database.models import Order, OrderStatus, OrderEvent, AssetAnalysis
from execution.effect_gate import EffectGate, AbortRequested
from execution.execution_service import ExecutionService


def test_order_model_two_phase_fields_and_transitions():
    order = Order(
        symbol="EURUSD",
        order_type="MARKET",
        direction="BUY",
        requested_price=1.0850,
        requested_volume=0.1,
    )
    assert order.replay_policy == "never"
    assert order.status == OrderStatus.PENDING_SUBMIT
    assert order.intent_committed_at is None
    assert order.settlement_committed_at is None

    # Transition to INTENT_COMMITTED
    evt_intent = order.transition_to(OrderStatus.INTENT_COMMITTED, reason="Intent committed")
    assert order.status == OrderStatus.INTENT_COMMITTED
    assert order.intent_committed_at is not None
    assert evt_intent.to_status == "intent_committed"

    # Transition to SUBMITTED
    evt_submit = order.transition_to(OrderStatus.SUBMITTED, reason="Sent to broker")
    assert order.status == OrderStatus.SUBMITTED

    # Transition to FILLED
    evt_fill = order.transition_to(OrderStatus.FILLED, reason="Broker filled", ticket=12345, executed_price=1.0852)
    assert order.status == OrderStatus.FILLED
    assert order.mt5_ticket == 12345
    assert order.executed_price == 1.0852
    assert order.settlement_committed_at is not None
    assert order.is_terminal is True


def test_order_transition_to_abort_requested_is_terminal():
    order = Order(
        symbol="XAUUSD",
        order_type="MARKET",
        direction="BUY",
        requested_price=2000.0,
        requested_volume=0.05,
    )
    order.transition_to(OrderStatus.INTENT_COMMITTED)
    order.transition_to(OrderStatus.ABORT_REQUESTED, reason="Kill switch won race")
    assert order.status == OrderStatus.ABORT_REQUESTED
    assert order.is_terminal is True


def test_order_transition_to_interrupted_is_terminal():
    order = Order(
        symbol="GBPUSD",
        order_type="MARKET",
        direction="SELL",
        requested_price=1.2500,
        requested_volume=0.1,
    )
    order.transition_to(OrderStatus.INTENT_COMMITTED)
    order.transition_to(OrderStatus.SUBMITTED)
    order.transition_to(OrderStatus.INTERRUPTED, reason="Crash recovery detected unconfirmed order")
    assert order.status == OrderStatus.INTERRUPTED
    assert order.is_terminal is True


@pytest.mark.asyncio
async def test_execution_service_blocks_when_effect_gate_aborted():
    from unittest.mock import patch
    from execution.execution_service import _EXECUTED_ANALYSIS_IDS
    _EXECUTED_ANALYSIS_IDS.clear()

    mock_mt5 = AsyncMock()
    mock_mt5.get_account_info.return_value = {"equity": 10000}
    mock_mt5.get_current_price.return_value = {"ask": 2000.0, "bid": 1999.0}

    settings = {
        "trading": {
            "min_paper_trades_before_live": 0,
            "risk": {
                "max_concurrent_positions": 5,
                "confluence_verifier_enabled": False,
                "min_verifiable_confluence": 0
            }
        },
        "execution": {"max_spread_multiplier": {"XAUUSD": 5.0}}
    }
    svc = ExecutionService(settings=settings, mt5_client=mock_mt5, dry_run=True)
    # Trip the effect gate before execution
    svc.effect_gate.request_abort("Emergency operator halt")

    mock_sizer = MagicMock()
    mock_sizer.calculate_with_session = AsyncMock(return_value=MagicMock(recommended_lots=0.1, entry_price=2000.0, is_valid=True))
    svc.sizer = mock_sizer

    mock_gate = AsyncMock()
    mock_gate.check.return_value = MagicMock(approved=True, checks_passed=['all'], checks_failed=[], rejection_reasons=[])
    svc.gate = mock_gate

    session = AsyncMock()
    session.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.first.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    analysis = AssetAnalysis(
        id=999,
        symbol="XAUUSD",
        decision="buy",
        stop_loss=1980,
        take_profit=2020,
        invalidation_price=1980,
        invalidation_direction="below",
        rationale="Test rationale"
    )

    svc.broker_adapter.submit_order = AsyncMock()

    with patch('analysis.validators.adversarial_check.run_adversarial_check', new_callable=AsyncMock) as mock_adv:
        mock_adv.return_value = {'approve': True, 'hard_block': False}
        res = await svc.execute_analysis(session, analysis)

    assert res.executed is False
    assert res.risk_approved is False
    assert "effect_gate_aborted" in res.risk_checks_failed
    # Broker submit was blocked by EffectGate
    svc.broker_adapter.submit_order.assert_not_called()
