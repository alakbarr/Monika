# ==============================================================================
# File: tests/execution/test_broker_plugins.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock
from execution.broker_plugin import (
    BrokerPlugin,
    TickData,
    InstrumentSpec,
    PositionData,
    AccountInfo,
)
from plugins.brokers.paper_trading.paper_plugin import PaperTradingBrokerPlugin
from plugins.brokers.mt5_local.mt5_plugin import MT5LocalBrokerPlugin
from harness.contract import PluginCategory


@pytest.mark.asyncio
async def test_paper_trading_broker_plugin():
    broker = PaperTradingBrokerPlugin(config={"initial_balance": 25000.0, "leverage": 200.0})
    assert broker.metadata.id == "paper_trading"
    assert broker.metadata.category == PluginCategory.BROKER
    assert broker.balance == 25000.0

    connected = await broker.connect()
    assert connected is True
    assert await broker.is_connected() is True

    # Test tick update & retrieval
    broker.update_tick(TickData(symbol="EURUSD", bid=1.0950, ask=1.0952, last=1.0951, spread=0.0002))
    tick = await broker.get_tick("EURUSD")
    assert tick is not None
    assert tick.bid == 1.0950

    # Test order execution
    order = MagicMock()
    order.symbol = "EURUSD"
    order.direction = "buy"
    order.volume = 0.5
    order.entry_price = 1.0952
    order.sl = 1.0900
    order.tp = 1.1050

    res = await broker.submit_order(order)
    assert res["success"] is True
    ticket = res["ticket"]

    positions = await broker.get_open_positions()
    assert len(positions) == 1
    assert positions[0].ticket == ticket
    assert positions[0].symbol == "EURUSD"
    assert positions[0].volume == 0.5

    # Modify SL/TP
    mod_ok = await broker.modify_position(ticket, sl=1.0910, tp=1.1060)
    assert mod_ok is True
    pos = (await broker.get_open_positions())[0]
    assert pos.sl == 1.0910

    # Close position
    close_res = await broker.close_position(ticket)
    assert close_res["success"] is True
    assert len(await broker.get_open_positions()) == 0


@pytest.mark.asyncio
async def test_mt5_local_broker_plugin_mocked():
    broker = MT5LocalBrokerPlugin()
    assert broker.metadata.id == "mt5_local"
    assert broker.metadata.category == PluginCategory.BROKER

    # Mock internal MT5Client
    mock_client = AsyncMock()
    mock_client.connect.return_value = True
    mock_client.is_connected.return_value = True
    mock_client.get_current_price.return_value = {"bid": 2650.0, "ask": 2650.5, "last": 2650.25}
    mock_client.get_account_info.return_value = {"balance": 50000.0, "equity": 50500.0, "margin": 1000.0, "margin_free": 49500.0, "leverage": 100.0}
    mock_client.get_open_positions.return_value = [
        {"ticket": 12345, "symbol": "XAUUSD", "type": 0, "volume": 0.2, "price_open": 2640.0, "sl": 2630.0, "tp": 2660.0, "profit": 200.0}
    ]

    broker.mt5_client = mock_client

    assert await broker.connect() is True
    assert await broker.is_connected() is True

    tick = await broker.get_tick("XAUUSD")
    assert tick is not None
    assert tick.bid == 2650.0

    acc = await broker.get_account_info()
    assert acc.balance == 50000.0
    assert acc.equity == 50500.0

    positions = await broker.get_open_positions()
    assert len(positions) == 1
    assert positions[0].ticket == 12345
    assert positions[0].symbol == "XAUUSD"
    assert positions[0].pnl == 200.0
