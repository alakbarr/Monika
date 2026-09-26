# ==============================================================================
# File: tests/execution/test_mt5_compat.py
# ==============================================================================

"""
Unit tests for MT5 cross-platform compatibility and RPC bridge layer.
Tests verify:
  - MT5 constant presence and accurate values
  - Fallback module behavior when MT5 is not present
  - MT5BridgeProxy integration and path stripping on Linux
  - sys.modules['MetaTrader5'] transparent injection
  - Connection error resilience and error recovery
"""

import sys
import os
import types
from unittest.mock import MagicMock, patch
import pytest

from execution.mt5_compat import (
    MT5_CONSTANTS,
    is_native_mt5_available,
    is_mt5linux_available,
    MT5BridgeProxy,
    MT5FallbackModule,
    get_mt5_module,
    ensure_mt5_module,
)


def test_mt5_constants_integrity():
    """Verify that essential MetaTrader5 constants exist with expected values."""
    assert len(MT5_CONSTANTS) > 100
    assert MT5_CONSTANTS["TIMEFRAME_H4"] == 16388
    assert MT5_CONSTANTS["TIMEFRAME_H1"] == 16385
    assert MT5_CONSTANTS["TIMEFRAME_M15"] == 15
    assert MT5_CONSTANTS["TIMEFRAME_D1"] == 16408
    assert MT5_CONSTANTS["ORDER_TYPE_BUY"] == 0
    assert MT5_CONSTANTS["ORDER_TYPE_SELL"] == 1
    assert MT5_CONSTANTS["TRADE_ACTION_DEAL"] == 1
    assert MT5_CONSTANTS["TRADE_ACTION_PENDING"] == 5
    assert MT5_CONSTANTS["TRADE_ACTION_SLTP"] == 6
    assert MT5_CONSTANTS["TRADE_RETCODE_DONE"] == 10009
    assert MT5_CONSTANTS["DEAL_REASON_SL"] == 4
    assert MT5_CONSTANTS["DEAL_REASON_TP"] == 5


def test_fallback_module_attributes_and_methods():
    """Verify that MT5FallbackModule returns correct constants and safe fallbacks."""
    fallback = MT5FallbackModule()
    
    # Constants access
    assert fallback.TIMEFRAME_H4 == 16388
    assert fallback.TRADE_RETCODE_DONE == 10009
    assert fallback.ORDER_TYPE_BUY == 0
    
    # Invalid attribute raises AttributeError
    with pytest.raises(AttributeError):
        _ = fallback.NON_EXISTENT_CONSTANT_XYZ

    # Methods return safe fallbacks
    assert fallback.initialize() is False
    assert fallback.login(12345, "secret", "demo") is False
    assert fallback.account_info() is None
    assert fallback.terminal_info() is None
    assert fallback.symbol_info("EURUSD") is None
    assert fallback.symbol_info_tick("EURUSD") is None
    assert fallback.positions_get() == ()
    assert fallback.orders_get() == ()
    assert fallback.copy_rates_from_pos("EURUSD", 16385, 0, 10) is None
    err_code, err_msg = fallback.last_error()
    assert err_code == -1
    assert "not available" in err_msg


def test_bridge_proxy_constants_and_getattr():
    """Verify that MT5BridgeProxy provides constants even before bridge is connected."""
    proxy = MT5BridgeProxy(host="127.0.0.1", port=18812)
    assert proxy.host == "127.0.0.1"
    assert proxy.port == 18812
    assert proxy.TIMEFRAME_H1 == 16385
    assert proxy.TRADE_RETCODE_DONE == 10009


def test_bridge_proxy_initialize_path_stripping():
    """Verify that on Linux / non-Windows, nonexistent paths are stripped for Wine compatibility."""
    proxy = MT5BridgeProxy()
    mock_client = MagicMock()
    mock_client.initialize.return_value = True
    proxy._bridge_client = mock_client

    with patch("os.path.exists", return_value=False), patch("sys.platform", "linux"):
        res = proxy.initialize(path="C:/Program Files/MetaTrader 5/terminal64.exe")
        assert res is True
        # Path was stripped because it doesn't exist on Linux host
        mock_client.initialize.assert_called_once_with()


def test_bridge_proxy_initialize_path_preserved_when_existing():
    """Verify that if path exists, it is preserved during initialize."""
    proxy = MT5BridgeProxy()
    mock_client = MagicMock()
    mock_client.initialize.return_value = True
    proxy._bridge_client = mock_client

    with patch("os.path.exists", return_value=True):
        res = proxy.initialize(path="C:/MT5/terminal64.exe")
        assert res is True
        mock_client.initialize.assert_called_once_with(path="C:/MT5/terminal64.exe")


def test_bridge_proxy_delegation():
    """Verify proxy delegates MT5 methods (login, order_send, positions_get, shutdown) to bridge client."""
    proxy = MT5BridgeProxy()
    mock_client = MagicMock()
    mock_client.login.return_value = True
    mock_client.order_send.return_value = MagicMock(retcode=10009, order=999)
    mock_client.positions_get.return_value = (MagicMock(ticket=123, symbol="EURUSD"),)
    proxy._bridge_client = mock_client

    assert proxy.login(12345, password="pwd", server="Real") is True
    mock_client.login.assert_called_once_with(login=12345, password="pwd", server="Real")

    send_res = proxy.order_send({"action": 1, "symbol": "EURUSD"})
    assert send_res.retcode == 10009

    positions = proxy.positions_get(symbol="EURUSD")
    assert len(positions) == 1
    assert positions[0].ticket == 123

    proxy.shutdown()
    mock_client.shutdown.assert_called_once()


def test_bridge_proxy_error_handling():
    """Verify proxy handles RPC connection failure cleanly without crashing."""
    proxy = MT5BridgeProxy(host="192.0.2.1", port=18812)
    mock_client = MagicMock()
    mock_client.initialize.side_effect = ConnectionRefusedError("Connection refused by RPC server")
    proxy._bridge_client = mock_client

    success = proxy.initialize()
    assert success is False
    err_code, err_msg = proxy.last_error()
    assert err_code == -10004
    assert "Connection refused" in err_msg


def test_ensure_mt5_module_registration():
    """Verify ensure_mt5_module registers module into sys.modules and allows standard import."""
    # Ensure clean state for test
    orig = sys.modules.get("MetaTrader5")
    try:
        mod = ensure_mt5_module()
        assert "MetaTrader5" in sys.modules
        assert sys.modules["MetaTrader5"] is mod
        assert hasattr(mod, "TIMEFRAME_H4")
        assert mod.TIMEFRAME_H4 == 16388

        # Verify idempotency
        mod2 = ensure_mt5_module()
        assert mod2 is mod

        # Test standard import syntax
        import MetaTrader5 as test_mt5
        assert test_mt5.TIMEFRAME_H4 == 16388
        assert test_mt5.TRADE_ACTION_DEAL == 1
    finally:
        if orig is not None:
            sys.modules["MetaTrader5"] = orig


def test_platform_check_helpers():
    """Verify platform detection helper functions return boolean results."""
    assert isinstance(is_native_mt5_available(), bool)
    assert isinstance(is_mt5linux_available(), bool)


def test_ensure_mt5_module_on_linux_simulation(monkeypatch):
    """Simulate non-Windows platform without native MT5, verifying proxy/fallback behavior."""
    import execution.mt5_compat as compat
    monkeypatch.setattr(compat, "is_native_mt5_available", lambda: False)
    monkeypatch.setattr(compat, "_active_mt5_module", None)
    
    orig = sys.modules.get("MetaTrader5")
    if "MetaTrader5" in sys.modules:
        del sys.modules["MetaTrader5"]
        
    try:
        mod = compat.ensure_mt5_module()
        assert "MetaTrader5" in sys.modules
        assert hasattr(mod, "TIMEFRAME_H4")
        assert mod.TIMEFRAME_H4 == 16388
        assert mod.TRADE_ACTION_DEAL == 1
    finally:
        compat._active_mt5_module = None
        if orig is not None:
            sys.modules["MetaTrader5"] = orig
        elif "MetaTrader5" in sys.modules:
            del sys.modules["MetaTrader5"]


def test_ensure_mt5_fallback_when_no_bridge(monkeypatch):
    """Simulate non-Windows platform with neither native nor bridge package available."""
    import execution.mt5_compat as compat
    monkeypatch.setattr(compat, "is_native_mt5_available", lambda: False)
    monkeypatch.setattr(compat, "is_mt5linux_available", lambda: False)
    monkeypatch.setattr(compat, "_active_mt5_module", None)
    
    orig = sys.modules.get("MetaTrader5")
    if "MetaTrader5" in sys.modules:
        del sys.modules["MetaTrader5"]
        
    try:
        mod = compat.ensure_mt5_module()
        assert "MetaTrader5" in sys.modules
        assert hasattr(mod, "TIMEFRAME_H4")
        assert mod.TIMEFRAME_H4 == 16388
        assert mod.initialize() is False
    finally:
        compat._active_mt5_module = None
        if orig is not None:
            sys.modules["MetaTrader5"] = orig
        elif "MetaTrader5" in sys.modules:
            del sys.modules["MetaTrader5"]

