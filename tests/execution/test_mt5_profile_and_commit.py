# ==============================================================================
# File: tests/execution/test_mt5_profile_and_commit.py
# Monika MT5 Trade Mode Hard Pinning & 2-Phase Order Commit Test Suite
# ==============================================================================

from unittest.mock import MagicMock, patch
import pytest

from execution.mt5_client import _connect, _is_connected, MT5ProfileMismatchError, MT5Client
from risk.pending_action import PendingActionStatus, PendingActionManager


def test_connect_login_pinning_mismatch():
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.login.return_value = True
    # Account returned by broker is 999999, but configured is 123456
    mock_info = MagicMock()
    mock_info.login = 999999
    mock_info.trade_mode = 0  # DEMO
    mock_mt5.account_info.return_value = mock_info

    with patch.dict("sys.modules", {"MetaTrader5": mock_mt5}):
        with pytest.raises(MT5ProfileMismatchError, match="Login Pinning Violation"):
            _connect(
                path="C:/Program Files/MetaTrader 5/terminal64.exe",
                account=123456,
                password="password",
                server="Broker-Demo",
            )
        mock_mt5.shutdown.assert_called_once()


def test_connect_trade_mode_mismatch():
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.login.return_value = True
    mock_info = MagicMock()
    mock_info.login = 123456
    mock_info.trade_mode = 2  # REAL account!
    mock_mt5.account_info.return_value = mock_info

    with patch.dict("sys.modules", {"MetaTrader5": mock_mt5}):
        # We expect DEMO mode, but broker terminal is connected to REAL
        with pytest.raises(MT5ProfileMismatchError, match="Trade Mode Mismatch"):
            _connect(
                path="C:/Program Files/MetaTrader 5/terminal64.exe",
                account=123456,
                password="password",
                server="Broker-Demo",
                expected_trade_mode="DEMO",
            )
        mock_mt5.shutdown.assert_called_once()


def test_connect_success_matching_profile():
    mock_mt5 = MagicMock()
    mock_mt5.initialize.return_value = True
    mock_mt5.login.return_value = True
    mock_info = MagicMock()
    mock_info.login = 123456
    mock_info.trade_mode = 0  # DEMO
    mock_info.balance = 50000.0
    mock_info.currency = "USD"
    mock_mt5.account_info.return_value = mock_info

    with patch.dict("sys.modules", {"MetaTrader5": mock_mt5}):
        ok = _connect(
            path="",
            account=123456,
            password="password",
            server="Broker-Demo",
            expected_trade_mode="DEMO",
        )
        assert ok is True
        mock_mt5.shutdown.assert_not_called()


@pytest.mark.asyncio
async def test_place_order_two_phase_commit_lifecycle(tmp_path):
    client = MT5Client()
    client._connected = True
    client.pending_action_manager = PendingActionManager(base_dir=tmp_path / "pending_orders")

    # Mock _run to return success
    fake_order_res = {
        "success": True,
        "ticket": 778899,
        "price": 1.1025,
        "error": None,
    }

    async def mock_run(fn, *args, **kwargs):
        if fn == _is_connected:
            return True
        # Verify that pending action marker was already created on disk (Phase 1)
        unconfirmed = client.pending_action_manager.get_unconfirmed_actions()
        assert len(unconfirmed) == 1
        assert unconfirmed[0].symbol == "EURUSD"
        assert unconfirmed[0].status == PendingActionStatus.DISPATCHING
        return fake_order_res

    client._run = mock_run

    result = await client.place_order(
        symbol="EURUSD",
        direction="buy",
        volume=0.1,
        price=1.1025,
        sl=1.0950,
        tp=1.1150,
        comment="Test2Phase",
    )

    assert result["success"] is True
    assert result["ticket"] == 778899

    # Verify that marker transitioned to COMMITTED (Phase 2)
    unconfirmed = client.pending_action_manager.get_unconfirmed_actions()
    assert len(unconfirmed) == 0

    all_files = list(client.pending_action_manager.base_dir.glob("*.json"))
    assert len(all_files) == 1
    act = client.pending_action_manager.get_action(all_files[0].stem.replace("pending_action_", ""))
    assert act.status == PendingActionStatus.COMMITTED
    assert act.broker_ticket == 778899
