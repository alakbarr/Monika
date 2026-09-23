# ==============================================================================
# File: tests/test_fase0_critical_fixes.py
# Description: Unit tests for Fase 0 Critical Bug Fixes & Integrations
# ==============================================================================

import datetime
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from logging_observability.dashboard.api import app, set_dashboard_dependencies
from logging_observability.dashboard.rbac import Role
from execution.service.trade_confirm import TradeConfirmManager
from risk.approval_hub import ApprovalHub
from telegram_bot.bot import TelegramBot

client = TestClient(app)


def test_backtest_rbac_protection():
    """Verify that backtest routes enforce RBAC Role permissions."""
    env = {
        "DASHBOARD_API_KEYS": "admin:adm_key,operator:ops_key,viewer:view_key",
        "DASHBOARD_API_KEY": "",
    }
    with patch.dict(os.environ, env):
        # 1. Viewer trying operator action (trigger backtest) -> 403
        res = client.post(
            "/api/backtest/run",
            headers={"X-API-Key": "view_key"},
            json={"days": 7, "mode": "full", "initial_equity": 10000.0, "step_hours": 6},
        )
        assert res.status_code == 403
        assert "operator" in res.json()["detail"].lower()

        # 2. Operator role CAN trigger backtest POST
        with patch("logging_observability.dashboard.routes.backtest._execute_background_backtest"):
            res_post_ok = client.post(
                "/api/backtest/run",
                headers={"X-API-Key": "ops_key"},
                json={"days": 7, "mode": "full", "initial_equity": 10000.0, "step_hours": 6},
            )
            assert res_post_ok.status_code == 200
            assert res_post_ok.json()["status"] == "queued"

        # 3. Viewer CAN access read endpoints
        with patch("logging_observability.dashboard.routes.backtest.get_session") as mock_get_sess:
            mock_sess = AsyncMock()
            mock_get_sess.return_value.__aenter__.return_value = mock_sess
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = []
            mock_sess.execute = AsyncMock(return_value=mock_res)

            res_get = client.get("/api/backtest/runs", headers={"X-API-Key": "view_key"})
            assert res_get.status_code == 200


@pytest.mark.asyncio
async def test_trade_confirm_approval_hub_synchronization():
    """Verify bidirectional synchronization between TradeConfirmManager and ApprovalHub."""
    hub = ApprovalHub.get_instance()
    manager = TradeConfirmManager()

    # Clear prior state
    hub._requests.clear()
    manager._pending_actions.clear()

    # 1. Create pending action in manager -> should register in ApprovalHub
    action = manager.create_pending_action(
        action_type="place_order",
        description="Test buy 0.1 lots EURUSD",
        payload={"symbol": "EURUSD", "volume": 0.1, "direction": "BUY"},
        ttl_seconds=60.0,
        channel_origin="telegram",
    )
    cid = action.confirm_id
    assert cid in hub._requests
    hub_req = hub._requests[cid]
    assert hub_req.status == "pending"
    assert hub_req.symbol == "EURUSD"
    assert hub_req.action == "PLACE_ORDER"

    # 2. Cancel action in manager -> should mark rejected in ApprovalHub
    cancelled = manager.cancel_action(cid)
    assert cancelled is True
    assert hub_req.status == "rejected"
    assert "Cancelled" in (hub_req.rejection_reason or "")

    # 3. Create another action and execute -> should mark approved in ApprovalHub
    action2 = manager.create_pending_action(
        action_type="close_position",
        description="Close position 12345",
        payload={"ticket": 12345, "symbol": "GBPUSD"},
        ttl_seconds=60.0,
        channel_origin="dashboard",
    )
    cid2 = action2.confirm_id
    assert cid2 in hub._requests

    async def mock_handler(payload):
        return {"ticket": payload["ticket"], "closed": True}

    ok, msg, res = await manager.execute_confirmed_action(cid2, mock_handler)
    assert ok is True
    assert hub._requests[cid2].status == "approved"


def test_telegram_dead_commands_registered():
    """Verify that override, regime, audit, and closeall are registered CommandHandlers."""
    bot = TelegramBot(settings={})
    app_mock = MagicMock()
    bot._app = app_mock

    bot._register_handlers()

    # Collect registered command names
    registered_cmds = []
    for call in app_mock.add_handler.call_args_list:
        handler = call[0][0]
        if hasattr(handler, "commands"):
            registered_cmds.extend(list(handler.commands))

    for cmd in ("override", "regime", "audit", "closeall"):
        assert cmd in registered_cmds, f"Command '{cmd}' not found in registered Telegram handlers"


@patch("database.db.AsyncSessionLocal")
def test_get_risk_enriched_fields(mock_session_local):
    """Verify that /api/risk returns enriched metrics."""
    mock_session = AsyncMock()
    mock_session_local.return_value.__aenter__.return_value = mock_session

    mock_res_risk = MagicMock()
    r = MagicMock()
    r.date = datetime.datetime.now(datetime.timezone.utc)
    r.daily_pnl = 150.0
    r.daily_pnl_pct = 1.5
    r.current_drawdown = 0.5
    r.trading_paused = False
    r.reason = None
    mock_res_risk.scalar_one_or_none.return_value = r

    mock_res_closed = MagicMock()
    mock_res_closed.all.return_value = []

    mock_res_open = MagicMock()
    mock_res_open.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[mock_res_risk, mock_res_closed, mock_res_open])

    set_dashboard_dependencies(
        settings={"trading": {"risk": {"risk_percent_per_trade": 1.5, "max_concurrent_positions": 4}}},
    )

    with patch("logging_observability.dashboard.rbac.resolve_role", return_value=Role.VIEWER):
        res = client.get("/api/risk")
        assert res.status_code == 200
        data = res.json()
        assert "margin_usage_pct" in data
        assert "total_open_risk_pct" in data
        assert "consecutive_losses" in data
        assert "max_consecutive_losses" in data
        assert "max_risk_pct" in data
        assert data["max_risk_pct"] == 1.5
        assert data["max_positions"] == 4
        assert "is_weekend" in data
