import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from execution.service.self_healing_executor import MT5SelfHealingExecutor


@pytest.mark.asyncio
async def test_self_healing_stops_invalid_10016():
    mock_adapter = MagicMock()
    # First submit failed with retcode 10016, second submit succeeds
    mock_adapter.submit_order = AsyncMock(return_value={"success": True, "ticket": 12345, "retcode": 10009})

    mock_order = MagicMock()
    mock_order.symbol = "EURUSD"
    mock_order.requested_volume = 0.1
    mock_order.order_type = "buy"

    mock_info = MagicMock()
    mock_info.point = 0.00001
    mock_info.digits = 5
    mock_info.trade_stops_level = 20
    mock_info.spread = 15

    mock_tick = MagicMock()
    mock_tick.ask = 1.08500
    mock_tick.bid = 1.08485

    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = mock_info
    mock_mt5.symbol_info_tick.return_value = mock_tick

    healer = MT5SelfHealingExecutor(broker_adapter=mock_adapter)

    with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
        initial_res = {"success": False, "retcode": 10016, "error": "ERR_TRADE_STOPS_INVALID"}
        # SL is at 1.08480, which is only 5 points below bid (violates 45 points buffer)
        final_res = await healer.heal_and_reexecute(
            order=mock_order,
            mt5_result=initial_res,
            sl=1.08480,
            tp=1.08600,
            comment="test_order",
            decision="buy"
        )

        assert final_res.get("success") is True
        assert final_res.get("ticket") == 12345
        # Verify submit_order was called with adjusted SL
        assert mock_adapter.submit_order.called
        call_kwargs = mock_adapter.submit_order.call_args[1]
        assert call_kwargs["sl"] < 1.08450  # Must be pushed down below bid - min_dist


@pytest.mark.asyncio
async def test_self_healing_volume_invalid_10014():
    mock_adapter = MagicMock()
    mock_adapter.submit_order = AsyncMock(return_value={"success": True, "ticket": 67890, "retcode": 10009})

    mock_order = MagicMock()
    mock_order.symbol = "BTCUSD"
    mock_order.requested_volume = 0.055  # Broker only allows step 0.01 or 0.1
    mock_order.order_type = "buy"

    mock_info = MagicMock()
    mock_info.volume_min = 0.1
    mock_info.volume_max = 10.0
    mock_info.volume_step = 0.1

    mock_mt5 = MagicMock()
    mock_mt5.symbol_info.return_value = mock_info

    healer = MT5SelfHealingExecutor(broker_adapter=mock_adapter)

    with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
        initial_res = {"success": False, "retcode": 10014, "error": "ERR_TRADE_VOLUME_INVALID"}
        final_res = await healer.heal_and_reexecute(
            order=mock_order,
            mt5_result=initial_res,
            sl=60000.0,
            tp=65000.0,
            comment="test_vol",
            decision="buy"
        )

        assert final_res.get("success") is True
        assert mock_order.requested_volume == 0.1  # Snapped to volume_min/step
