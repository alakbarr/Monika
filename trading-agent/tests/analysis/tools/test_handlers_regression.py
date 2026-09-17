"""Regression tests for repaired tool handlers (Pylance type & contract fixes)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from analysis.tools.handlers.category_loader import (
    handle_load_tool_category,
    handle_get_market_context,
    handle_get_institutional_data,
)
from analysis.tools.handlers.market_data import (
    GetPriceDataHandler,
    GetTechnicalAnalysisHandler,
)
from analysis.tools.handlers.sentiment_data import (
    WebSearchHandler,
    GetForexSentimentHandler,
    GetFxssiSentimentHandler,
)
from analysis.tools.handlers.timesfm import handle_get_timesfm_forecast
from analysis.tools.handlers.ptc_handler import PTCHandler


@pytest.mark.asyncio
async def test_handle_load_tool_category_returns_list():
    res = await handle_load_tool_category({"category": "TECHNICAL"})
    assert isinstance(res, list)


@pytest.mark.asyncio
async def test_category_loader_market_context_delegation():
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok"})
    mock_executor._resolve_symbol = MagicMock(return_value="EURUSD")

    res = await handle_get_market_context({"symbol": "EURUSD"}, executor=mock_executor)
    assert "market_session" in res
    assert mock_executor.execute.called


@pytest.mark.asyncio
async def test_market_data_composite_handlers():
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok"})
    mock_session = AsyncMock()

    price_handler = GetPriceDataHandler()
    price_res = await price_handler.execute(
        {"symbol": "EURUSD", "direction": "buy", "entry_price": 1.10},
        session=mock_session,
        executor=mock_executor,
    )
    assert "price_history" in price_res

    ta_handler = GetTechnicalAnalysisHandler()
    ta_res = await ta_handler.execute(
        {"symbol": "EURUSD", "timeframes": ["H4"]},
        session=mock_session,
        executor=mock_executor,
    )
    assert "H4" in ta_res


@pytest.mark.asyncio
async def test_sentiment_handlers_delegation():
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok"})
    mock_executor._tool_web_search = AsyncMock(return_value={"results": ["article 1"]})
    mock_executor._tool_get_forex_sentiment = AsyncMock(return_value={"long_pct": 60})
    mock_executor._tool_get_fxssi_sentiment = AsyncMock(return_value={"long_pct": 55})
    mock_session = AsyncMock()

    web_handler = WebSearchHandler()
    web_res = await web_handler.execute({"query": "inflation"}, session=mock_session, executor=mock_executor)
    assert web_res == {"results": ["article 1"]}

    forex_handler = GetForexSentimentHandler()
    forex_res = await forex_handler.execute({"symbol": "EURUSD"}, session=mock_session, executor=mock_executor)
    assert forex_res == {"long_pct": 60}

    fxssi_handler = GetFxssiSentimentHandler()
    fxssi_res = await fxssi_handler.execute({"symbol": "EURUSD"}, session=mock_session, executor=mock_executor)
    assert fxssi_res == {"long_pct": 55}


@pytest.mark.asyncio
async def test_timesfm_no_session_guard():
    res = await handle_get_timesfm_forecast(symbol="EURUSD", session=None)
    assert res["status"] == "no_session"
    assert res["confidence"] == 0.0


@pytest.mark.asyncio
async def test_ptc_handler_server_typing():
    mock_executor = MagicMock()
    ptc = PTCHandler(mock_executor)
    rpc, port = await ptc._start_tool_rpc_server(allowed_tools=["get_quote"])
    try:
        assert port > 0
        assert rpc._server is not None
    finally:
        rpc.close()
        await rpc.wait_closed()
