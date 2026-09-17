"""Unit tests for get_market_quote tool and handlers."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from analysis.tools.handlers.market_data_tools import handle_get_market_quote
from analysis.tools.domain.technical_handlers import TechnicalToolHandlers
from analysis.tools.executor import ToolExecutor
from analysis.tools.registry import default_tool_registry
from analysis.tools.tool_registry import ProgressiveToolRegistry
from analysis.tools.tools_definitions import ALL_TOOLS


@pytest.mark.asyncio
async def test_get_market_quote_mt5_success():
    """Test market quote fetching via live MT5 tick."""
    mock_mt5 = AsyncMock()
    mock_mt5.get_current_price = AsyncMock(return_value={
        "symbol": "EURUSD",
        "bid": 1.08500,
        "ask": 1.08520,
        "last": 1.08510,
        "time": datetime(2026, 9, 8, 0, 0, 0, tzinfo=timezone.utc),
    })

    with patch("execution.mt5_client.get_mt5_client", return_value=mock_mt5):
        res = await handle_get_market_quote({"symbol": "EURUSD"})

    assert res["status"] == "success"
    assert res["source"] == "mt5"
    assert res["symbol"] == "EURUSD"
    assert res["bid"] == 1.08500
    assert res["ask"] == 1.08520
    assert res["price"] == 1.08510
    assert res["spread"] == 0.0002
    assert res["spread_pips"] == 2.0
    assert "timestamp" in res


@pytest.mark.asyncio
async def test_get_market_quote_db_fallback():
    """Test fallback to DB PriceOHLCV when MT5 is offline/empty."""
    mock_mt5 = AsyncMock()
    mock_mt5.get_current_price = AsyncMock(return_value=None)

    mock_bar = MagicMock()
    mock_bar.close = 2650.50
    mock_bar.open = 2648.00
    mock_bar.high = 2655.00
    mock_bar.low = 2645.00
    mock_bar.volume = 1250.0
    mock_bar.timeframe = "H1"
    mock_bar.timestamp = datetime(2026, 9, 8, 0, 0, 0, tzinfo=timezone.utc)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_bar
    mock_session.execute.return_value = mock_result

    with patch("execution.mt5_client.get_mt5_client", return_value=mock_mt5):
        res = await handle_get_market_quote({"symbol": "XAUUSD"}, session=mock_session)

    assert res["status"] == "success"
    assert res["source"] == "db_ohlcv"
    assert res["symbol"] == "XAUUSD"
    assert res["price"] == 2650.50
    assert res["last_price"] == 2650.50
    assert res["spread_pips"] == 2.5
    assert res["timeframe"] == "H1"


@pytest.mark.asyncio
async def test_get_market_quote_no_data():
    """Test graceful handling when neither MT5 nor DB has data."""
    mock_mt5 = AsyncMock()
    mock_mt5.get_current_price = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("execution.mt5_client.get_mt5_client", return_value=mock_mt5):
        res = await handle_get_market_quote({"symbol": "GBPUSD"}, session=mock_session)

    assert res["status"] == "no_data"
    assert res["source"] == "unavailable"
    assert res["symbol"] == "GBPUSD"
    assert res["price"] is None


@pytest.mark.asyncio
async def test_get_market_quote_missing_symbol():
    """Test missing symbol error response."""
    res = await handle_get_market_quote({})
    assert "error" in res
    assert "symbol" in res["error"].lower()


@pytest.mark.asyncio
async def test_technical_domain_handler():
    """Test TechnicalToolHandlers.get_market_quote method."""
    mock_mt5 = AsyncMock()
    mock_mt5.get_current_price = AsyncMock(return_value={
        "symbol": "BTCUSD",
        "bid": 65000.0,
        "ask": 65015.0,
        "last": 65005.0,
        "time": datetime(2026, 9, 8, 0, 0, 0, tzinfo=timezone.utc),
    })

    handler = TechnicalToolHandlers(settings={})
    with patch("execution.mt5_client.get_mt5_client", return_value=mock_mt5):
        res = await handler.get_market_quote("BTCUSD")

    assert res["status"] == "success"
    assert res["symbol"] == "BTCUSD"
    assert res["price"] == 65007.5


@pytest.mark.asyncio
async def test_tool_executor_dispatch_and_aliases():
    """Test ToolExecutor executes get_market_quote and alias get_quote."""
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session)

    mock_mt5 = AsyncMock()
    mock_mt5.get_current_price = AsyncMock(return_value={
        "symbol": "EURUSD",
        "bid": 1.0850,
        "ask": 1.0852,
        "last": 1.0851,
        "time": datetime.now(timezone.utc),
    })

    with patch("execution.mt5_client.get_mt5_client", return_value=mock_mt5):
        # Direct call
        res1 = await executor.execute("get_market_quote", {"symbol": "EURUSD"})
        assert res1["status"] == "success"
        assert res1["symbol"] == "EURUSD"
        assert "get_market_quote" in executor.called_tools

        # Alias call 'get_quote'
        res2 = await executor.execute("get_quote", {"symbol": "EURUSD"})
        assert res2["status"] == "success"
        assert res2["symbol"] == "EURUSD"

        # Alias call 'market_quote'
        res3 = await executor.execute("market_quote", {"symbol": "EURUSD"})
        assert res3["status"] == "success"
        assert res3["symbol"] == "EURUSD"


def test_tool_definitions_and_registry_schemas():
    """Verify get_market_quote is registered in schemas and tool registry."""
    # 1. In ALL_TOOLS
    tool_names = [t["name"] for t in ALL_TOOLS if "name" in t]
    assert "get_market_quote" in tool_names

    # 2. In Modular ToolRegistry
    reg = default_tool_registry
    handler = reg.get("get_market_quote")
    assert handler is not None

    # 3. In ProgressiveToolRegistry core schemas
    prog_reg = ProgressiveToolRegistry()
    stage2_core = prog_reg.get_core_schemas(stage="stage2")
    core_names = [t["name"] for t in stage2_core]
    assert "get_market_quote" in core_names
