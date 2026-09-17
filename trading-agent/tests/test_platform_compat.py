# ==============================================================================
# File: tests/test_platform_compat.py
# ==============================================================================

import sys
import pytest
from pathlib import Path
from utils.infra.platform_compat import (
    IS_WINDOWS,
    IS_LINUX,
    configure_event_loop,
    safe_subprocess_run,
    normalize_path,
)
from execution.broker_adapter import MT5RemoteGatewayAdapter


def test_platform_detection_and_event_loop_factory():
    """Verify event loop factory returns SelectorEventLoop on Windows."""
    factory_dict = configure_event_loop()
    if sys.platform == "win32":
        assert IS_WINDOWS is True
        assert "loop_factory" in factory_dict
        import asyncio
        assert factory_dict["loop_factory"] == asyncio.SelectorEventLoop
    else:
        assert IS_WINDOWS is False


def test_normalize_path():
    """Verify path normalization produces resolved Path objects."""
    p = normalize_path("data/test_file.txt")
    assert isinstance(p, Path)
    assert p.is_absolute()


@pytest.mark.asyncio
async def test_safe_subprocess_run_echo():
    """Verify safe_subprocess_run runs commands without SelectorEventLoop errors."""
    cmd = [sys.executable, "-c", "import sys; sys.stdout.write('TEST_OUTPUT_OK')"]
    code, stdout, stderr = await safe_subprocess_run(cmd)

    assert code == 0
    assert "TEST_OUTPUT_OK" in stdout


def test_mt5_remote_gateway_adapter_initialization():
    """Verify MT5RemoteGatewayAdapter initializes with valid endpoints."""
    adapter = MT5RemoteGatewayAdapter(gateway_url="http://192.168.1.50:8080", api_token="secret_token")
    assert adapter.gateway_url == "http://192.168.1.50:8080"
    assert adapter.api_token == "secret_token"
    assert adapter._connected is False


@pytest.mark.asyncio
async def test_trading_agent_remote_gateway_wiring_and_shutdown():
    """Verify TradingAgent dynamically wires MT5RemoteGatewayAdapter and stops components cleanly."""
    from unittest.mock import MagicMock, AsyncMock, patch
    from main import TradingAgent

    custom_settings = {
        "execution": {
            "adapter_type": "remote_gateway",
            "remote_gateway_url": "http://192.168.1.100:8080",
            "remote_gateway_token": "test_token_123",
        },
        "alpha_discovery": {
            "enabled": True,
            "interval_hours": 12.0,
        },
        "trading": {"asset_universe": ["EURUSD"]},
    }
    agent = TradingAgent(settings=custom_settings, dry_run=True)
    assert agent.alpha_discovery_scheduler is None
    assert agent.post_release_analyzer is None

    with patch("execution.mt5_client.MT5Client"):
        agent._init_components()

    assert agent.execution_service is not None
    assert isinstance(agent.execution_service.broker_adapter, MT5RemoteGatewayAdapter)
    assert agent.execution_service.broker_adapter.gateway_url == "http://192.168.1.100:8080"
    assert agent.execution_service.broker_adapter.api_token == "test_token_123"
    assert agent.alpha_discovery_scheduler is not None

    # Test clean shutdown of both sync and async stop methods
    mock_post_release = MagicMock()
    mock_post_release.stop = AsyncMock()
    agent.post_release_analyzer = mock_post_release

    mock_alpha_discovery = MagicMock()
    mock_alpha_discovery.stop = MagicMock()
    agent.alpha_discovery_scheduler = mock_alpha_discovery

    if agent.mt5_client:
        agent.mt5_client.disconnect = AsyncMock()

    agent.telegram_bot = None
    agent._activity_log = MagicMock()
    agent._activity_log.system = AsyncMock()

    with patch("database.db.get_session"), \
         patch("main.close_db", new_callable=AsyncMock):
        await agent._shutdown()

    mock_post_release.stop.assert_awaited_once()
    mock_alpha_discovery.stop.assert_called_once()


class _MockResponse:
    def __init__(self, status=200, json_data=None, text_data=""):
        self.status = status
        self._json_data = json_data or {}
        self._text_data = text_data

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _MockClientSession:
    def __init__(self, response):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response

    def post(self, *args, **kwargs):
        return self.response

    def delete(self, *args, **kwargs):
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.asyncio
async def test_mt5_remote_gateway_rpc_methods():
    """Verify all MT5RemoteGatewayAdapter RPC operations (ensure_connected, get_tick, submit_order, close, positions)."""
    from unittest.mock import patch
    from database.models import Order

    adapter = MT5RemoteGatewayAdapter(gateway_url="http://127.0.0.1:8080", api_token="sec_token")

    # 1. ensure_connected (success & failure)
    with patch("aiohttp.ClientSession", return_value=_MockClientSession(_MockResponse(200, {"status": "ok"}))):
        assert await adapter.ensure_connected() is True
        assert adapter._connected is True

    with patch("aiohttp.ClientSession", return_value=_MockClientSession(_MockResponse(503, text_data="Service Unavailable"))):
        assert await adapter.ensure_connected() is False
        assert adapter._connected is False

    # 2. get_tick
    mock_tick = {"symbol": "EURUSD", "bid": 1.0850, "ask": 1.0852, "last": 1.0851, "spread": 0.0002}
    with patch("aiohttp.ClientSession", return_value=_MockClientSession(_MockResponse(200, mock_tick))):
        tick = await adapter.get_tick("EURUSD")
        assert tick["bid"] == 1.0850
        assert tick["ask"] == 1.0852

    # 3. submit_order (success)
    order = Order(
        symbol="EURUSD",
        order_type="MARKET",
        direction="BUY",
        requested_volume=0.1,
        requested_price=1.0850,
        client_order_id="ord_12345",
    )
    mock_order_res = {"success": True, "ticket": 999123, "price": 1.0850}
    with patch("aiohttp.ClientSession", return_value=_MockClientSession(_MockResponse(200, mock_order_res))):
        res = await adapter.submit_order(order, sl=1.0800, tp=1.0950, comment="Test Order")
        assert res["success"] is True
        assert res["ticket"] == 999123

    # 4. submit_order (gateway error reject)
    with patch("aiohttp.ClientSession", return_value=_MockClientSession(_MockResponse(400, text_data="Invalid volume"))):
        res_err = await adapter.submit_order(order)
        assert res_err["success"] is False
        assert "Gateway error 400" in res_err["error"]

    # 5. cancel_order
    with patch("aiohttp.ClientSession", return_value=_MockClientSession(_MockResponse(200))):
        assert await adapter.cancel_order("ord_12345") is True

    # 6. close_position
    mock_close_res = {"success": True, "ticket": 999123, "price": 1.0890, "pnl": 40.0}
    with patch("aiohttp.ClientSession", return_value=_MockClientSession(_MockResponse(200, mock_close_res))):
        close_res = await adapter.close_position(999123, lots=0.1)
        assert close_res["success"] is True
        assert close_res["ticket"] == 999123

    # 7. get_positions & get_open_positions
    mock_positions = [{"ticket": 999123, "symbol": "EURUSD", "volume": 0.1}]
    with patch("aiohttp.ClientSession", return_value=_MockClientSession(_MockResponse(200, mock_positions))):
        pos = await adapter.get_positions()
        assert len(pos) == 1
        assert pos[0]["ticket"] == 999123

        # get_open_positions with filter
        eur_pos = await adapter.get_open_positions("EURUSD")
        assert len(eur_pos) == 1
        xau_pos = await adapter.get_open_positions("XAUUSD")
        assert len(xau_pos) == 0

    # 8. get_account_info
    mock_acc = {"balance": 10500.0, "equity": 10540.0, "margin": 100.0, "free_margin": 10440.0}
    with patch("aiohttp.ClientSession", return_value=_MockClientSession(_MockResponse(200, mock_acc))):
        acc = await adapter.get_account_info()
        assert acc["balance"] == 10500.0
        assert acc["equity"] == 10540.0


@pytest.mark.asyncio
async def test_trading_agent_start_connects_remote_gateway():
    """Verify TradingAgent.start() verifies remote gateway connectivity via adapter.ensure_connected()."""
    from unittest.mock import MagicMock, AsyncMock, patch
    from main import TradingAgent

    custom_settings = {
        "execution": {
            "adapter_type": "remote_gateway",
            "remote_gateway_url": "http://192.168.1.100:8080",
            "remote_gateway_token": "test_token_123",
        },
        "alpha_discovery": {"enabled": False},
        "trading": {"asset_universe": ["EURUSD"]},
    }
    agent = TradingAgent(settings=custom_settings, dry_run=True)
    with patch("execution.mt5_client.MT5Client"):
        agent._init_components()

    # Mock ensure_connected on the wired remote adapter
    mock_ensure = AsyncMock(return_value=True)
    agent.execution_service.broker_adapter.ensure_connected = mock_ensure

    with patch.object(agent, "_post_restart_recovery", new_callable=AsyncMock), \
         patch.object(agent, "_activity_log") as mock_act, \
         patch.object(agent, "_send_startup_notification", new_callable=AsyncMock):
        mock_act.system = AsyncMock()

        # Call the connection block of start()
        from execution.broker_adapter import MT5LiveAdapter
        custom_adapter = getattr(agent.execution_service, "broker_adapter", None)
        assert custom_adapter is not None
        assert not isinstance(custom_adapter, MT5LiveAdapter)
        connected = await custom_adapter.ensure_connected()
        assert connected is True
        mock_ensure.assert_awaited_once()



