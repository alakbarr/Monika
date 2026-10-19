# ==============================================================================
# File: tests/services/test_trading_service.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock

from monika.application.services.portfolio_service import PortfolioService
from monika.application.services.trading_service import TradingService
from monika.domain.entities.position import PositionEntity
from tests.conftest import create_mock_async_session


@pytest.mark.asyncio
async def test_trading_service_modify_position_success():
    mock_session = create_mock_async_session()
    mock_pos = PositionEntity(
        id=1,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        sl=1.0900,
        tp=1.1200,
        status="open",
        mt5_ticket=1001,
        is_paper=True,
    )

    # Mock position repository in TradingService
    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_by_ticket = AsyncMock(return_value=mock_pos)
        mock_repo.update_sl_tp = AsyncMock(return_value=mock_pos)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        ok = await TradingService.modify_position(
            session=mock_session,
            ticket=1001,
            sl=1.0950,
            tp=1.1250,
            actor="test_runner",
        )
        assert ok is True
        mock_repo.get_by_ticket.assert_awaited_once_with(1001, open_only=True)
        mock_repo.update_sl_tp.assert_awaited_once_with(ticket=1001, sl=1.0950, tp=1.1250)


@pytest.mark.asyncio
async def test_trading_service_close_positions_batch():
    mock_session = create_mock_async_session()
    mock_pos1 = PositionEntity(
        id=1,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        status="open",
        mt5_ticket=1001,
        is_paper=True,
    )
    mock_pos2 = PositionEntity(
        id=2,
        symbol="GBPUSD",
        direction="sell",
        volume=0.2,
        entry_price=1.2500,
        status="open",
        mt5_ticket=1002,
        is_paper=True,
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()

        async def _mock_get(ticket, open_only=True):
            if ticket == 1001:
                return mock_pos1
            if ticket == 1002:
                return mock_pos2
            return None

        mock_repo.get_by_ticket = AsyncMock(side_effect=_mock_get)
        mock_repo.close_position = AsyncMock(return_value=mock_pos1)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        res = await TradingService.close_positions_batch(
            session=mock_session,
            tickets=[1001, 1002, 9999],
            reason="Test batch close",
            actor="test_runner",
        )
        assert res["success"] is True
        assert res["closed_count"] == 2
        assert res["failed_count"] == 1
        assert res["tickets"] == [1001, 1002, 9999]


@pytest.mark.asyncio
async def test_trading_service_bulk_breakeven():
    mock_session = create_mock_async_session()

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.apply_bulk_breakeven = AsyncMock(return_value=3)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        res = await TradingService.bulk_breakeven(
            session=mock_session,
            symbol="EURUSD",
            actor="test_runner",
        )
        assert res["success"] is True
        assert res["updated_count"] == 3
        mock_repo.apply_bulk_breakeven.assert_awaited_once_with(symbol="EURUSD")


@pytest.mark.asyncio
async def test_trading_service_set_trailing_override():
    mock_session = create_mock_async_session()
    mock_pos = PositionEntity(
        id=1,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        status="open",
        mt5_ticket=1001,
        is_paper=True,
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_by_ticket = AsyncMock(return_value=mock_pos)
        mock_repo.update_trailing_override = AsyncMock(return_value=mock_pos)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        updated = await TradingService.set_trailing_override(
            session=mock_session,
            ticket=1001,
            override_data={"trailing_pips": 15.0},
            actor="test_runner",
        )
        assert updated is not None
        mock_repo.update_trailing_override.assert_awaited_once()


@pytest.mark.asyncio
async def test_portfolio_service_get_order_logs():
    mock_session = create_mock_async_session()
    mock_log = MagicMock(id=1, action="place", symbol="EURUSD")

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_recent_order_logs = AsyncMock(return_value=[mock_log])
        mp.setattr(
            "monika.application.services.portfolio_service.PositionRepository",
            lambda s: mock_repo,
        )

        logs = await PortfolioService.get_order_logs(mock_session, limit=10, action="place")
        assert len(logs) == 1
        assert logs[0].action == "place"
        mock_repo.get_recent_order_logs.assert_awaited_once_with(limit=10, action="place")


@pytest.mark.asyncio
async def test_trading_service_submit_order_kill_switch_active():
    mock_session = create_mock_async_session()
    with pytest.MonkeyPatch.context() as mp:
        mock_cfg = MagicMock()
        mock_cfg.is_kill_switch_active = AsyncMock(return_value=True)
        mock_cfg.get = AsyncMock(return_value="false")
        mp.setattr(
            "monika.application.services.trading_service.SystemConfigRepository",
            lambda s: mock_cfg,
        )

        res = await TradingService.submit_order(
            session=mock_session,
            symbol="EURUSD",
            action="BUY",
            volume=0.1,
            entry_price=1.1000,
            is_paper=True,
        )
        assert res.success is False
        assert "kill switch" in (res.error_message or "").lower()


@pytest.mark.asyncio
async def test_trading_service_submit_order_paper_evaluates_risk_gate():
    mock_session = create_mock_async_session()
    with pytest.MonkeyPatch.context() as mp:
        mock_cfg = MagicMock()
        mock_cfg.is_kill_switch_active = AsyncMock(return_value=False)
        mock_cfg.is_system_paused = AsyncMock(return_value=False)
        mock_cfg.get_suspended_symbols = AsyncMock(return_value=[])
        mock_cfg.get = AsyncMock(return_value="false")
        mp.setattr(
            "monika.application.services.trading_service.SystemConfigRepository",
            lambda s: mock_cfg,
        )

        mock_risk_gate = MagicMock()
        mock_risk_eval = MagicMock()
        mock_risk_eval.approved = False
        mock_risk_eval.rejection_reasons = ["Max drawdown exceeded"]
        mock_risk_gate.evaluate_proposal = AsyncMock(return_value=mock_risk_eval)

        res = await TradingService.submit_order(
            session=mock_session,
            symbol="EURUSD",
            action="BUY",
            volume=0.1,
            entry_price=1.1000,
            stop_loss=1.0900,
            take_profit=1.1200,
            is_paper=True,
            risk_gate=mock_risk_gate,
        )
        assert res.success is False
        assert "Rejected by RiskGate: Max drawdown exceeded" in (res.error_message or "")
        mock_risk_gate.evaluate_proposal.assert_awaited_once()


@pytest.mark.asyncio
async def test_trading_service_submit_order_live_broker_fail_closed():
    mock_session = create_mock_async_session()
    with pytest.MonkeyPatch.context() as mp:
        mock_cfg = MagicMock()
        mock_cfg.is_kill_switch_active = AsyncMock(return_value=False)
        mock_cfg.is_system_paused = AsyncMock(return_value=False)
        mock_cfg.get_suspended_symbols = AsyncMock(return_value=[])
        mock_cfg.get = AsyncMock(return_value="false")
        mp.setattr(
            "monika.application.services.trading_service.SystemConfigRepository",
            lambda s: mock_cfg,
        )

        mock_risk_gate = MagicMock()
        mock_risk_eval = MagicMock()
        mock_risk_eval.approved = True
        mock_risk_gate.evaluate_proposal = AsyncMock(return_value=mock_risk_eval)

        mock_broker = MagicMock()
        mock_broker.place_order = AsyncMock(return_value={"success": False, "message": "No money"})

        res = await TradingService.submit_order(
            session=mock_session,
            symbol="EURUSD",
            action="BUY",
            volume=0.1,
            entry_price=1.1000,
            stop_loss=1.0900,
            take_profit=1.1200,
            is_paper=False,
            broker_adapter=mock_broker,
            risk_gate=mock_risk_gate,
        )
        assert res.success is False
        assert "No money" in (res.error_message or "")


@pytest.mark.asyncio
async def test_trading_service_modify_position_broker_failure_fails_closed():
    mock_session = create_mock_async_session()
    mock_pos = PositionEntity(
        id=1,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        sl=1.0900,
        tp=1.1200,
        status="open",
        mt5_ticket=1001,
        is_paper=False,
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_by_ticket = AsyncMock(return_value=mock_pos)
        mock_repo.update_sl_tp = AsyncMock(return_value=mock_pos)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        mock_broker = MagicMock()
        mock_broker.modify_position = AsyncMock(side_effect=RuntimeError("Broker network disconnect"))

        ok = await TradingService.modify_position(
            session=mock_session,
            ticket=1001,
            sl=1.0950,
            tp=1.1250,
            actor="test_runner",
            broker_adapter=mock_broker,
        )
        assert ok is False
        mock_repo.update_sl_tp.assert_not_called()


@pytest.mark.asyncio
async def test_trading_service_close_position_live_broker_records_pnl():
    mock_session = create_mock_async_session()
    mock_pos = PositionEntity(
        id=1,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1000,
        status="open",
        mt5_ticket=1001,
        is_paper=False,
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_by_ticket = AsyncMock(return_value=mock_pos)
        mock_repo.close_position = AsyncMock(return_value=mock_pos)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        mock_broker = MagicMock()
        mock_broker.close_position = AsyncMock(return_value={"success": True, "pnl": 125.50})

        ok = await TradingService.close_position(
            session=mock_session,
            ticket=1001,
            reason="TP reached",
            broker_adapter=mock_broker,
        )
        assert ok is True
        mock_repo.close_position.assert_awaited_once_with(ticket=1001, pnl=125.50)


@pytest.mark.asyncio
async def test_trading_service_bulk_breakeven_syncs_broker():
    mock_session = create_mock_async_session()
    mock_pos_live = PositionEntity(
        id=1,
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        entry_price=1.1050,
        tp=1.1200,
        status="open",
        mt5_ticket=5555,
        is_paper=False,
    )

    with pytest.MonkeyPatch.context() as mp:
        mock_repo = MagicMock()
        mock_repo.get_open_positions = AsyncMock(return_value=[mock_pos_live])
        mock_repo.apply_bulk_breakeven = AsyncMock(return_value=1)
        mp.setattr(
            "monika.application.services.trading_service.PositionRepository",
            lambda s: mock_repo,
        )

        mock_broker = MagicMock()
        mock_broker.modify_position = AsyncMock(return_value={"success": True})

        res = await TradingService.bulk_breakeven(
            session=mock_session,
            symbol="EURUSD",
            actor="test_runner",
            broker_adapter=mock_broker,
        )
        assert res["success"] is True
        mock_broker.modify_position.assert_awaited_once_with(
            ticket=5555,
            sl=1.1050,
            tp=1.1200,
        )


@pytest.mark.asyncio
async def test_trading_service_resume_trading_clears_emergency_kill_active():
    mock_session = create_mock_async_session()
    with pytest.MonkeyPatch.context() as mp:
        mock_cfg = MagicMock()
        cleared_keys = []

        async def _set(key, val):
            if val == "false":
                cleared_keys.append(key)

        mock_cfg.set = AsyncMock(side_effect=_set)
        mp.setattr(
            "monika.application.services.trading_service.SystemConfigRepository",
            lambda s: mock_cfg,
        )

        res = await TradingService.resume_trading(session=mock_session)
        assert res["status"] == "RESUMED"
        assert "emergency_kill_active" in cleared_keys
        assert "kill_switch" in cleared_keys
