import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.tools.tool_executor import ToolExecutor


@pytest.mark.asyncio
async def test_tool_executor_delegates_to_technical_handlers():
    """Verify ToolExecutor correctly delegates technical tools to TechnicalToolHandlers."""
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    fake_snapshot = {"ATR": {"value": 15.5}, "RSI": {"value": 55.0}}
    with patch("indicators.technical.TechnicalIndicatorCalculator.get_snapshot", new_callable=AsyncMock) as mock_snap:
        mock_snap.return_value = fake_snapshot

        res = await executor.execute("get_technical_indicators", {"symbol": "EURUSD", "timeframe": "H1"})
        assert res["symbol"] == "EURUSD"
        assert res["timeframe"] == "H1"
        assert res["indicators"] == fake_snapshot


@pytest.mark.asyncio
async def test_tool_executor_delegates_to_macro_handlers():
    """Verify ToolExecutor delegates macro queries to MacroToolHandlers."""
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    with patch.object(executor.macro_handlers, "get_market_session", new_callable=AsyncMock) as mock_sess:
        mock_sess.return_value = {"active_sessions": ["London", "New York"], "status": "active"}
        res = await executor.execute("get_market_session", {})
        assert res["status"] == "active"
        assert "London" in res["active_sessions"]
        mock_sess.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_executor_delegates_to_position_handlers():
    """Verify ToolExecutor delegates position queries to PositionToolHandlers."""
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    with patch.object(executor.position_handlers, "get_open_positions", new_callable=AsyncMock) as mock_pos:
        mock_pos.return_value = {"positions": [], "total": 0}
        res = await executor.execute("get_open_positions", {})
        assert res["total"] == 0
        mock_pos.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_executor_delegates_to_sentiment_handlers():
    """Verify ToolExecutor delegates sentiment tools to SentimentToolHandlers."""
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    with patch.object(executor.sentiment_handlers, "get_fear_greed", new_callable=AsyncMock) as mock_fg:
        mock_fg.return_value = {"value": 75, "classification": "Greed"}
        res = await executor.execute("get_fear_greed", {})
        assert res["classification"] == "Greed"
        mock_fg.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_executor_executes_read_url():
    """Verify ToolExecutor correctly executes read_url via WebReader."""
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    fake_page = {
        "success": True,
        "url": "https://federalreserve.gov/monetarypolicy.htm",
        "title": "Federal Reserve Monetary Policy",
        "content": "FOMC decisions, inflation targets, and discount window rate.",
    }
    with patch("data_sources.web_reader.WebReader.read_url", new_callable=AsyncMock) as mock_read:
        mock_read.return_value = fake_page

        res = await executor.execute("read_url", {"url": "https://federalreserve.gov/monetarypolicy.htm"})
        assert res["success"] is True
        assert "Federal Reserve" in res["title"]
        assert "FOMC decisions" in res["content"]
        mock_read.assert_awaited_once_with("https://federalreserve.gov/monetarypolicy.htm")


@pytest.mark.asyncio
async def test_tool_executor_executes_search_academic():
    """Verify ToolExecutor correctly executes search_academic via AcademicSearchClient."""
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    fake_papers = {
        "success": True,
        "query": "statistical arbitrage order flow toxicity",
        "total_results": 1,
        "papers": [
            {
                "title": "Flow Toxicity in High-Frequency Markets",
                "summary": "We study VPIN metrics across futures markets...",
                "authors": ["Easley", "Lopez de Prado", "O'Hara"],
                "link": "https://arxiv.org/abs/1105.1234",
            }
        ],
    }
    with patch("data_sources.academic_search.AcademicSearchClient.search_papers", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = fake_papers

        res = await executor.execute("search_academic", {"query": "statistical arbitrage order flow toxicity", "max_results": 3})
        assert res["success"] is True
        assert len(res["papers"]) == 1
        assert "Flow Toxicity" in res["papers"][0]["title"]
        mock_search.assert_awaited_once_with(query="statistical arbitrage order flow toxicity", max_results=3)


@pytest.mark.asyncio
async def test_tool_executor_unknown_tool_returns_structured_error():
    """Verify unknown tool returns structured error instead of unhandled exception."""
    mock_session = AsyncMock()
    executor = ToolExecutor(mock_session, settings={})

    res = await executor.execute("non_existent_tool_xyz", {"foo": "bar"})
    assert "error" in res
    assert res.get("error_type") == "UnknownToolError"

