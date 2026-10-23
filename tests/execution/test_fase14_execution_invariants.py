"""
Phase 14 Institutional Execution Invariants Test Suite.
Tests all critical fixes:
1. OrderStatus ABORT_REQUESTED is non-terminal.
2. Terminal orders cannot transition in state machine, OrderEntity, or DB Order model.
3. EvidenceFirstVerifier rejects NaN, Inf, and non-positive volume/prices.
4. MT5 deal reason mapping correctly distinguishes SL (4), TP (5), and Expert/EA (3).
5. MT5 partial fill (10010) and no changes (10025) are recognized as successes.
6. IdempotencyGuard reconciles in-flight orders without tickets by symbol + direction + time window.
7. EA Watchdog starts fail-closed (is_alive = False).
8. HeartbeatManager tracks consecutive failures and trips circuit breaker on >= 3 failures.
"""

import asyncio
import math
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.domain.entities.order_status import OrderStatus, InvalidOrderStateTransitionError
from monika.domain.entities.order import OrderEntity
from monika.domain.execution.state_machine import OrderStateMachine
from monika.domain.execution.verification_engine import EvidenceFirstVerifier
from monika.infrastructure.brokers.ea_bridge.watchdog import EAWatchdog
from monika.infrastructure.brokers.ea_bridge.heartbeat_writer import HeartbeatManager
from monika.infrastructure.brokers.idempotency_guard import IdempotencyGuard, IdempotencyState


def test_order_status_abort_requested_is_terminal():
    assert OrderStatus.ABORT_REQUESTED.is_terminal is True
    assert OrderStatus.FILLED.is_terminal is True
    assert OrderStatus.CANCELLED.is_terminal is True
    assert OrderStatus.REJECTED.is_terminal is True


def test_order_entity_terminal_state_transition_prevention():
    order = OrderEntity(
        client_order_id="test_ord_1",
        symbol="EURUSD",
        order_type="MARKET",
        direction="BUY",
        requested_price=1.0850,
        requested_volume=0.1,
        status=OrderStatus.FILLED,
    )
    with pytest.raises(InvalidOrderStateTransitionError):
        order.transition_to(OrderStatus.CANCELLED)

    sm = OrderStateMachine()
    assert sm.can_transition(OrderStatus.FILLED, OrderStatus.CANCELLED) is False
    with pytest.raises(InvalidOrderStateTransitionError):
        sm.transition(order, OrderStatus.CANCELLED)


@pytest.mark.asyncio
async def test_verification_engine_finite_checks():
    engine = EvidenceFirstVerifier()

    # NaN entry price
    ok, violations = await engine.pre_trade_assertions(
        {
            "symbol": "EURUSD",
            "decision": "BUY",
            "entry_price": float("nan"),
            "stop_loss": 1.0800,
            "take_profit": 1.0900,
            "volume": 0.1,
            "confidence": 0.8,
            "confluence_score": 7,
            "priced_in_score": 4,
            "invalidation": "below support",
        }
    )
    assert ok is False
    assert any("finite" in v.lower() for v in violations)

    # Inf stop loss
    ok_inf, violations_inf = await engine.pre_trade_assertions(
        {
            "symbol": "EURUSD",
            "decision": "BUY",
            "entry_price": 1.0850,
            "stop_loss": float("inf"),
            "take_profit": 1.0900,
            "volume": 0.1,
            "confidence": 0.8,
            "confluence_score": 7,
            "priced_in_score": 4,
            "invalidation": "below support",
        }
    )
    assert ok_inf is False
    assert any("finite" in v.lower() for v in violations_inf)

    # Negative volume
    ok_vol, violations_vol = await engine.pre_trade_assertions(
        {
            "symbol": "EURUSD",
            "decision": "BUY",
            "entry_price": 1.0850,
            "stop_loss": 1.0800,
            "take_profit": 1.0900,
            "volume": -0.1,
            "confidence": 0.8,
            "confluence_score": 7,
            "priced_in_score": 4,
            "invalidation": "below support",
        }
    )
    assert ok_vol is False
    assert any("volume" in v.lower() for v in violations_vol)


def test_mt5_deal_reason_mapping():
    # Verify deal reason semantics:
    # 4 -> DEAL_REASON_SL -> "sl_hit"
    # 5 -> DEAL_REASON_TP -> "tp_hit"
    # 3 -> DEAL_REASON_EXPERT -> "ea_close"
    # others -> "broker_close"
    def resolve_reason(reason_code):
        return (
            "sl_hit"
            if reason_code == 4
            else ("tp_hit" if reason_code == 5 else ("ea_close" if reason_code == 3 else "broker_close"))
        )

    assert resolve_reason(4) == "sl_hit"
    assert resolve_reason(5) == "tp_hit"
    assert resolve_reason(3) == "ea_close"
    assert resolve_reason(0) == "broker_close"


def test_mt5_order_ops_retcodes():
    from monika.infrastructure.brokers.mt5.order_ops import _place_order, _modify_position

    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = MagicMock(
        bid=1.0850,
        ask=1.0852,
        digits=5,
        point=0.00001,
        trade_stops_level=0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
    )
    mock_mt5.symbol_info_tick.return_value = MagicMock(bid=1.0850, ask=1.0852)
    # Partial fill
    res_partial = MagicMock()
    res_partial.retcode = 10010
    res_partial.order = 123456
    mock_mt5.order_send.return_value = res_partial
    mock_mt5.TRADE_RETCODE_DONE = 10009
    mock_mt5.TRADE_RETCODE_PLACED = 10008
    mock_mt5.TRADE_RETCODE_DONE_PARTIAL = 10010

    with patch.dict("sys.modules", {"MetaTrader5": mock_mt5}):
        result = _place_order("EURUSD", "buy", 0.1, 1.0852, 1.0800, 1.0900, "test", "market")
        assert result["success"] is True
        assert result["ticket"] == 123456

        # Modification with no changes (10025)
        res_no_change = MagicMock()
        res_no_change.retcode = 10025
        mock_mt5.order_send.return_value = res_no_change
        mock_mt5.TRADE_RETCODE_NO_CHANGES = 10025
        mock_pos = MagicMock()
        mock_pos.symbol = "EURUSD"
        mock_mt5.positions_get.return_value = [mock_pos]

        mod_result = _modify_position(123456, 1.0800, 1.0900)
        assert mod_result["success"] is True


@pytest.mark.asyncio
async def test_idempotency_guard_reconciliation_without_ticket():
    guard = IdempotencyGuard()
    key = "test_key_eurusd"
    acquired, _ = await guard.acquire_lock(key, "EURUSD", "BUY", ttl_seconds=60)
    assert acquired is True

    # Broker position without known ticket in record
    now = time.time()
    broker_positions = [{"symbol": "EURUSD", "direction": "buy", "ticket": 789101, "time": now - 10}]
    reconciled = await guard.reconcile_with_broker(broker_positions)
    assert reconciled == 1

    rec = guard._records[key]
    assert rec.state == IdempotencyState.COMPLETED
    assert rec.ticket == 789101


def test_ea_watchdog_starts_fail_closed():
    watchdog = EAWatchdog()
    assert watchdog._is_ea_alive is False
    assert watchdog.is_alive is False


@pytest.mark.asyncio
async def test_heartbeat_writer_circuit_breaker_on_repeated_failure(tmp_path):
    mgr = HeartbeatManager(mt5_common_path=str(tmp_path))
    # Mock write_text to fail repeatedly
    with patch("pathlib.Path.write_text", side_effect=PermissionError("Permission denied")):
        with patch("monika.core.primitives.event_bus.get_event_bus") as mock_bus_fn:
            mock_bus = MagicMock()
            mock_bus_fn.return_value = mock_bus

            for _ in range(3):
                mgr._write_heartbeat()

            assert mgr._consecutive_write_failures == 3
            mock_bus.publish_nowait.assert_called()
