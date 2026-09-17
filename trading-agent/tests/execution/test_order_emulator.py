# ==============================================================================
# File: tests/execution/test_order_emulator.py
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from execution.order_emulator import ClientOrderEmulator, TrackedPosition
from utils.protocol.event_bus import EventBus, TickPriceEvent


@pytest.mark.asyncio
async def test_order_emulator_registration():
    emulator = ClientOrderEmulator()
    pos = await emulator.register_position(
        ticket=12345,
        symbol="XAUUSD",
        direction="buy",
        entry_price=2000.0,
        current_sl=1980.0,
        atr=15.0,
        current_tp=2050.0,
    )
    assert pos.ticket == 12345
    assert pos.symbol == "XAUUSD"
    assert pos.high_watermark == 2000.0
    assert pos.low_watermark == 2000.0
    assert emulator.get_tracked_position(12345) is not None

    unreg = await emulator.unregister_position(12345)
    assert unreg.ticket == 12345
    assert emulator.get_tracked_position(12345) is None


@pytest.mark.asyncio
async def test_order_emulator_breakeven_buy():
    mock_adjust = AsyncMock(return_value={"success": True})
    emulator = ClientOrderEmulator(
        on_sl_adjustment=mock_adjust,
        settings={"trading": {"trailing_stop": {"breakeven_atr_multiple": 1.0, "spread_buffer_atr": 0.1}}},
    )
    # Entry 2000.0, ATR 10.0, SL 1980.0
    await emulator.register_position(
        ticket=101, symbol="XAUUSD", direction="buy",
        entry_price=2000.0, current_sl=1980.0, atr=10.0
    )

    # Tick with price 2005 (profit 5 < 1.0 ATR) -> no adjustment
    tick1 = TickPriceEvent(symbol="XAUUSD", bid=2005.0, ask=2005.2, last=2005.0)
    res1 = await emulator.on_tick(tick1)
    assert len(res1) == 0
    assert not mock_adjust.called

    # Tick with price 2011 (profit 11 >= 1.0 ATR) -> BE triggered!
    # Expected BE SL = entry + 0.1 * ATR = 2000 + 1 = 2001.0
    tick2 = TickPriceEvent(symbol="XAUUSD", bid=2011.0, ask=2011.2, last=2011.0)
    res2 = await emulator.on_tick(tick2)
    assert len(res2) == 1
    assert res2[0]["ticket"] == 101
    assert res2[0]["new_sl"] == 2001.0
    assert "be_triggered" in res2[0]["reason"]
    mock_adjust.assert_called_once()


@pytest.mark.asyncio
async def test_order_emulator_trailing_buy():
    mock_adjust = AsyncMock(return_value={"success": True})
    emulator = ClientOrderEmulator(
        on_sl_adjustment=mock_adjust,
        settings={"trading": {"trailing_stop": {
            "breakeven_atr_multiple": 1.0,
            "trail_atr_multiple": 1.5,
            "spread_buffer_atr": 0.1
        }}},
    )
    # Entry 2000.0, ATR 10.0, SL 2001.0 (already at BE)
    await emulator.register_position(
        ticket=102, symbol="XAUUSD", direction="buy",
        entry_price=2000.0, current_sl=2001.0, atr=10.0
    )

    # Tick price 2025.0 (profit 25 >= 2.0 * ATR = 20.0) -> Trailing triggered!
    # Trailing SL = 2025 - (1.5 * 10) = 2010.0 (> current 2001.0)
    tick = TickPriceEvent(symbol="XAUUSD", bid=2025.0, ask=2025.2, last=2025.0)
    res = await emulator.on_tick(tick)
    assert len(res) == 1
    assert res[0]["ticket"] == 102
    assert res[0]["new_sl"] == 2010.0
    assert "trailing_stop" in res[0]["reason"]


@pytest.mark.asyncio
async def test_order_emulator_breakeven_and_trailing_sell():
    mock_adjust = AsyncMock(return_value={"success": True})
    emulator = ClientOrderEmulator(
        on_sl_adjustment=mock_adjust,
        settings={"trading": {"trailing_stop": {
            "breakeven_atr_multiple": 1.0,
            "trail_atr_multiple": 1.5,
            "spread_buffer_atr": 0.1
        }}},
    )
    # SELL: Entry 1.1000, ATR 0.0050, SL 1.1100
    await emulator.register_position(
        ticket=201, symbol="EURUSD", direction="sell",
        entry_price=1.1000, current_sl=1.1100, atr=0.0050
    )

    # 1. BE check: price drops to 1.0945 (profit = 1.1000 - 1.0945 = 0.0055 >= 1.0 * ATR 0.0050)
    # BE SL = 1.1000 - (0.1 * 0.0050) = 1.0995 (< 1.1100)
    tick_be = TickPriceEvent(symbol="EURUSD", bid=1.0944, ask=1.0945, last=1.0945)
    res_be = await emulator.on_tick(tick_be)
    assert len(res_be) == 1
    assert res_be[0]["new_sl"] == 1.0995

    # 2. Trailing check: price drops to 1.0850 (profit = 0.0150 >= 2.0 * ATR 0.0100)
    # Trailing SL = 1.0850 + (1.5 * 0.0050) = 1.0925 (< 1.0995)
    tick_trail = TickPriceEvent(symbol="EURUSD", bid=1.0849, ask=1.0850, last=1.0850)
    res_trail = await emulator.on_tick(tick_trail)
    assert len(res_trail) == 1
    assert res_trail[0]["new_sl"] == 1.0925


@pytest.mark.asyncio
async def test_order_emulator_event_bus_integration():
    bus = EventBus()
    mock_adjust = AsyncMock(return_value={"success": True})
    emulator = ClientOrderEmulator(
        event_bus=bus,
        on_sl_adjustment=mock_adjust,
        settings={"trading": {"trailing_stop": {"breakeven_atr_multiple": 1.0, "spread_buffer_atr": 0.1}}},
    )

    await emulator.register_position(
        ticket=301, symbol="BTCUSD", direction="buy",
        entry_price=50000.0, current_sl=48000.0, atr=1000.0
    )

    # Publish tick on EventBus
    tick = TickPriceEvent(symbol="BTCUSD", bid=51200.0, ask=51205.0, last=51200.0)
    await bus.publish(tick)

    # Allow event queue dispatch
    await asyncio.sleep(0.05)
    mock_adjust.assert_called_once()
    args, kwargs = mock_adjust.call_args
    assert args[0] == 301
    assert args[1] == 50100.0  # 50000 + 0.1 * 1000


@pytest.mark.asyncio
async def test_order_emulator_sync_positions():
    emulator = ClientOrderEmulator()
    await emulator.register_position(ticket=1, symbol="EURUSD", direction="buy", entry_price=1.1, current_sl=1.09, atr=0.01)
    await emulator.register_position(ticket=2, symbol="GBPUSD", direction="buy", entry_price=1.3, current_sl=1.29, atr=0.01)

    class DummyPos:
        def __init__(self, ticket, symbol, direction, entry, sl):
            self.mt5_ticket = ticket
            self.symbol = symbol
            self.direction = direction
            self.entry_price = entry
            self.sl = sl

    # Sync with only ticket 2 and new ticket 3 (ticket 1 closed)
    active = [
        DummyPos(2, "GBPUSD", "buy", 1.3, 1.29),
        DummyPos(3, "USDJPY", "buy", 150.0, 149.0),
    ]

    await emulator.sync_positions(active, atr_lookup={"USDJPY": 0.5})

    assert emulator.get_tracked_position(1) is None
    assert emulator.get_tracked_position(2) is not None
    assert emulator.get_tracked_position(3) is not None
    assert emulator.get_tracked_position(3).atr == 0.5


@pytest.mark.asyncio
async def test_order_emulator_dispatch_failure_retains_sl():
    mock_adjust = AsyncMock(return_value={"success": False, "error": "Broker rejected"})
    emulator = ClientOrderEmulator(
        on_sl_adjustment=mock_adjust,
        settings={"trading": {"trailing_stop": {"breakeven_atr_multiple": 1.0, "spread_buffer_atr": 0.1}}},
    )
    pos = await emulator.register_position(
        ticket=999, symbol="XAUUSD", direction="buy",
        entry_price=2000.0, current_sl=1980.0, atr=10.0
    )

    tick = TickPriceEvent(symbol="XAUUSD", bid=2015.0, ask=2015.2, last=2015.0)
    res = await emulator.on_tick(tick)

    assert len(res) == 1
    assert res[0]["success"] is False
    # Verified: current_sl should NOT have mutated to new_sl on failure
    assert pos.current_sl == 1980.0
    assert pos.breakeven_activated is False


@pytest.mark.asyncio
async def test_order_emulator_concurrent_ticks_guard():
    """Verify is_modifying prevents concurrent duplicate dispatch on rapid ticks."""
    dispatch_event = asyncio.Event()

    async def slow_dispatch(*args, **kwargs):
        await dispatch_event.wait()
        return {"success": True}

    emulator = ClientOrderEmulator(
        on_sl_adjustment=slow_dispatch,
        settings={"trading": {"trailing_stop": {"breakeven_atr_multiple": 1.0, "spread_buffer_atr": 0.1}}},
    )
    pos = await emulator.register_position(
        ticket=777, symbol="XAUUSD", direction="buy",
        entry_price=2000.0, current_sl=1980.0, atr=10.0
    )

    tick = TickPriceEvent(symbol="XAUUSD", bid=2015.0, ask=2015.2, last=2015.0)

    # Launch tick 1 in background
    task1 = asyncio.create_task(emulator.on_tick(tick))
    await asyncio.sleep(0.01)  # Ensure task1 reaches in-flight dispatch

    assert pos.is_modifying is True

    # Tick 2 arrives while tick 1 is still dispatching
    res2 = await emulator.on_tick(tick)
    # Must be safely skipped (empty adjustments) without firing another dispatch
    assert len(res2) == 0

    # Let tick 1 finish
    dispatch_event.set()
    res1 = await task1
    assert len(res1) == 1
    assert res1[0]["success"] is True
    assert pos.is_modifying is False


@pytest.mark.asyncio
async def test_order_emulator_atr_zero_and_preservation():
    """Verify atr=0.0 is not clamped to dummy 0.00001, and existing ATR is preserved."""
    emulator = ClientOrderEmulator()

    # 1. Fresh position with atr=0.0 should have atr=0.0 (not 0.00001)
    pos = await emulator.register_position(
        ticket=555, symbol="EURUSD", direction="buy",
        entry_price=1.1000, current_sl=1.0900, atr=0.0
    )
    assert pos.atr == 0.0

    # Tick evaluation safely ignores position with atr=0.0
    tick = TickPriceEvent(symbol="EURUSD", bid=1.1100, ask=1.1102, last=1.1100)
    res = await emulator.on_tick(tick)
    assert len(res) == 0

    # 2. Re-register with valid ATR
    pos = await emulator.register_position(
        ticket=555, symbol="EURUSD", direction="buy",
        entry_price=1.1000, current_sl=1.0900, atr=0.0050
    )
    assert pos.atr == 0.0050

    # 3. Subsequent register with atr=0.0 preserves existing 0.0050
    pos = await emulator.register_position(
        ticket=555, symbol="EURUSD", direction="buy",
        entry_price=1.1000, current_sl=1.0900, atr=0.0
    )
    assert pos.atr == 0.0050


@pytest.mark.asyncio
async def test_order_emulator_trailing_activates_breakeven():
    """Verify pos.breakeven_activated is set to True when trailing stop is activated."""
    mock_adjust = AsyncMock(return_value={"success": True})
    emulator = ClientOrderEmulator(
        on_sl_adjustment=mock_adjust,
        settings={"trading": {"trailing_stop": {"breakeven_atr_multiple": 1.0, "trail_atr_multiple": 1.5}}},
    )
    pos = await emulator.register_position(
        ticket=888, symbol="XAUUSD", direction="buy",
        entry_price=2000.0, current_sl=1980.0, atr=10.0
    )
    # Direct jump to trailing stop territory (> 2.0x ATR)
    tick = TickPriceEvent(symbol="XAUUSD", bid=2030.0, ask=2030.2, last=2030.0)
    res = await emulator.on_tick(tick)
    assert len(res) == 1
    assert "trailing_stop" in res[0]["reason"]
    assert pos.trailing_activated is True
    assert pos.breakeven_activated is True
