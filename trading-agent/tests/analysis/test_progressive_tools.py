"""
Unit tests for progressive tool disclosure execution via ToolExecutor.
"""

import pytest
from unittest.mock import MagicMock
from analysis.tools.executor import ToolExecutor


@pytest.mark.asyncio
async def test_progressive_tool_search():
    mock_session = MagicMock()
    executor = ToolExecutor(session=mock_session)

    # Search for volatility/ATR tools
    res = await executor.execute("search_tools", {"query": "volatility", "limit": 3})
    assert res["status"] == "success"
    assert len(res["matches"]) > 0
    names = [m["name"] for m in res["matches"]]
    assert any("atr" in n or "vix" in n for n in names)


@pytest.mark.asyncio
async def test_progressive_tool_describe():
    mock_session = MagicMock()
    executor = ToolExecutor(session=mock_session)

    res = await executor.execute("describe_tool", {"tool_name": "calculate_position_size"})
    assert res["status"] == "success"
    assert res["tool"]["name"] == "calculate_position_size"
    assert "input_schema" in res["tool"]


@pytest.mark.asyncio
async def test_progressive_tool_load_category():
    mock_session = MagicMock()
    executor = ToolExecutor(session=mock_session)

    res = await executor.execute("load_tool_category", {"category": "MACRO"})
    assert res["status"] == "success"
    assert res["category"] == "MACRO"
    assert res["loaded_count"] > 0
    assert "get_dxy" in res["tools"] or "get_vix" in res["tools"]
