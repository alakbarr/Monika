# ==============================================================================
# File: tests/execution/test_broker_registry.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock
from execution.broker_plugin import OrderRequest, normalize_order_request, InstrumentSpec, TickData
from execution.broker_registry import BrokerAdapterRegistry
from execution.broker_adapter import SimulatedBrokerAdapter, MT5LiveAdapter


def test_order_request_and_normalization():
    # Direct DTO
    req = OrderRequest(symbol="EURUSD", direction="buy", volume=0.1, price=1.0850)
    assert req.requested_volume == 0.1
    assert req.requested_price == 1.0850
    assert normalize_order_request(req) is req

    # Dict representation
    data = {"symbol": "GBPUSD", "direction": "sell", "volume": 0.2, "price": 1.2500}
    norm_dict = normalize_order_request(data)
    assert isinstance(norm_dict, OrderRequest)
    assert norm_dict.symbol == "GBPUSD"
    assert norm_dict.direction == "sell"
    assert norm_dict.volume == 0.2

    # Mock ORM Order representation
    class MockOrder:
        symbol = "XAUUSD"
        direction = "buy"
        requested_volume = 0.5
        requested_price = 2350.0
        order_type = "LIMIT"
        stop_loss = 2340.0
        take_profit = 2370.0
        comment = "TestORM"
        client_order_id = "test-123"
        magic = 1001

    norm_orm = normalize_order_request(MockOrder())
    assert isinstance(norm_orm, OrderRequest)
    assert norm_orm.symbol == "XAUUSD"
    assert norm_orm.volume == 0.5
    assert norm_orm.price == 2350.0
    assert norm_orm.sl == 2340.0
    assert norm_orm.tp == 2370.0


def test_broker_adapter_registry():
    registered = BrokerAdapterRegistry.list_registered()
    assert "mt5_live" in registered
    assert "simulated" in registered

    BrokerAdapterRegistry.set_active("simulated")
    active = BrokerAdapterRegistry.get_active()
    assert isinstance(active, SimulatedBrokerAdapter)

    # Custom registration
    mock_adapter = MagicMock()
    BrokerAdapterRegistry.register("custom_broker", mock_adapter)
    assert BrokerAdapterRegistry.get("custom_broker") is mock_adapter


@pytest.mark.asyncio
async def test_simulated_broker_accepts_order_request():
    adapter = SimulatedBrokerAdapter(initial_balance=10000.0)
    adapter.get_tick = AsyncMock(return_value={
        "symbol": "EURUSD", "bid": 1.0850, "ask": 1.0852, "last": 1.0852, "spread": 0.0002
    })

    req = OrderRequest(symbol="EURUSD", direction="buy", volume=0.1, price=1.0852, client_order_id="req-1")
    result = await adapter.submit_order(req)
    assert result["success"] is True
    assert result["executed_volume"] == 0.1
    assert result["ticket"] is not None


@pytest.mark.asyncio
async def test_mt5_live_adapter_dry_run_accepts_order_request():
    adapter = MT5LiveAdapter(dry_run=True)
    req = OrderRequest(symbol="EURUSD", direction="buy", volume=0.1, price=1.0850, client_order_id="req-2")
    result = await adapter.submit_order(req)
    assert result["success"] is True
    assert result["executed_volume"] == 0.1
    assert result["ticket"] is not None
