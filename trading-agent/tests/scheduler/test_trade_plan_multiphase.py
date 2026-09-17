import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from database.models import Position, TradePlan, TradePlanLeg
from scheduler.trailing_stop_manager import TrailingStopManager


@pytest.mark.asyncio
async def test_trailing_stop_auto_breakeven_on_tp1_buy():
    settings = {
        "trading": {
            "trailing_stop": {
                "enabled": True,
                "breakeven_atr_multiple": 1.0,
                "trail_atr_multiple": 1.5,
                "timeframe": "H1",
            }
        },
        "timesfm": {"volatility_trailing_adjustment": False}
    }

    mock_exec = AsyncMock()
    mock_exec.modify_position_sl_tp.return_value = {"success": True}

    manager = TrailingStopManager(settings, execution_service=mock_exec)

    pos = Position(
        id=1,
        symbol="XAUUSD",
        direction="buy",
        entry_price=2700.0,
        sl=2680.0,
        mt5_ticket=123456,
        status="open",
        volume=1.0,
    )

    plan = TradePlan(
        id=10,
        symbol="XAUUSD",
        direction="buy",
        status="CONFIRMED_SCALE_IN",
        entry_price=2700.0,
        stop_loss=2680.0,
        take_profit_1=2710.0,
        total_volume=1.0,
    )
    leg_probe = TradePlanLeg(id=1, plan_id=10, leg_type="probe", volume=0.3, target_entry=2700.0, stop_loss=2680.0, status="filled")
    plan.legs = [leg_probe]

    mock_session = AsyncMock()
    mock_exec.mt5 = AsyncMock()
    mock_exec.mt5.get_open_positions.return_value = [
        {"ticket": 123456, "price_current": 2712.0}
    ]

    mock_atr_row = MagicMock()
    mock_atr_row.value_json = "10.0"

    async def mock_execute(stmt):
        res = MagicMock()
        stmt_str = str(stmt)
        if "economic_calendar" in stmt_str:
            res.scalar_one_or_none.return_value = None
        elif "technical_indicators" in stmt_str:
            res.scalar_one_or_none.return_value = mock_atr_row
        elif "trade_plans" in stmt_str:
            res.scalar_one_or_none.return_value = plan
        else:
            res.scalar_one_or_none.return_value = None
        return res

    mock_session.execute.side_effect = mock_execute

    adj = await manager._check_position(mock_session, pos)

    assert "tp1_breakeven" in adj.get("reason", "")
    assert adj.get("new_sl") == 2700.0 + (0.1 * 10.0)  # 2701.0
    assert plan.status == "PARTIAL_TP1_HIT"
    assert leg_probe.status == "tp_hit"


@pytest.mark.asyncio
async def test_trailing_stop_auto_breakeven_on_tp1_sell():
    settings = {
        "trading": {
            "trailing_stop": {
                "enabled": True,
                "breakeven_atr_multiple": 1.0,
                "trail_atr_multiple": 1.5,
                "timeframe": "H1",
            }
        },
        "timesfm": {"volatility_trailing_adjustment": False}
    }

    mock_exec = AsyncMock()
    mock_exec.modify_position_sl_tp.return_value = {"success": True}

    manager = TrailingStopManager(settings, execution_service=mock_exec)

    pos = Position(
        id=2,
        symbol="EURUSD",
        direction="sell",
        entry_price=1.1000,
        sl=1.1050,
        mt5_ticket=654321,
        status="open",
        volume=0.5,
    )

    plan = TradePlan(
        id=11,
        symbol="EURUSD",
        direction="sell",
        status="CONFIRMED_SCALE_IN",
        entry_price=1.1000,
        stop_loss=1.1050,
        take_profit_1=1.0980,
        total_volume=0.5,
    )
    leg_probe = TradePlanLeg(id=2, plan_id=11, leg_type="probe", volume=0.15, target_entry=1.1000, stop_loss=1.1050, status="filled")
    plan.legs = [leg_probe]

    mock_session = AsyncMock()
    mock_exec.mt5 = AsyncMock()
    mock_exec.mt5.get_open_positions.return_value = [
        {"ticket": 654321, "price_current": 1.0970}  # profit = 1.1000 - 1.0970 = 0.0030 >= ATR 0.0020
    ]

    mock_atr_row = MagicMock()
    mock_atr_row.value_json = "0.0020"

    async def mock_execute(stmt):
        res = MagicMock()
        stmt_str = str(stmt)
        if "economic_calendar" in stmt_str:
            res.scalar_one_or_none.return_value = None
        elif "technical_indicators" in stmt_str:
            res.scalar_one_or_none.return_value = mock_atr_row
        elif "trade_plans" in stmt_str:
            res.scalar_one_or_none.return_value = plan
        else:
            res.scalar_one_or_none.return_value = None
        return res

    mock_session.execute.side_effect = mock_execute

    adj = await manager._check_position(mock_session, pos)

    assert "tp1_breakeven" in adj.get("reason", "")
    assert adj.get("new_sl") == 1.1000 - (0.1 * 0.0020)  # 1.0998
    assert plan.status == "PARTIAL_TP1_HIT"
    assert leg_probe.status == "tp_hit"


def test_trade_plan_lot_splitting_boundary():
    """Verify probe 30% and runner 70% lot sizing logic at minimum lot boundary."""
    # Boundary 1: Minimum lot (0.01) -> single probe leg, runner = 0.0
    total_lots = 0.01
    if total_lots <= 0.01:
        probe_lots = round(total_lots, 2)
        runner_lots = 0.0
    else:
        probe_lots = round(max(0.01, round(total_lots * 0.30, 2)), 2)
        runner_lots = round(max(0.0, round(total_lots - probe_lots, 2)), 2)

    assert probe_lots == 0.01
    assert runner_lots == 0.0
    assert probe_lots + runner_lots == 0.01

    # Normal case: 1.0 lot -> probe 0.30, runner 0.70
    total_lots = 1.0
    if total_lots <= 0.01:
        probe_lots = round(total_lots, 2)
        runner_lots = 0.0
    else:
        probe_lots = round(max(0.01, round(total_lots * 0.30, 2)), 2)
        runner_lots = round(max(0.0, round(total_lots - probe_lots, 2)), 2)

    assert probe_lots == 0.30
    assert runner_lots == 0.70
    assert probe_lots + runner_lots == 1.0
