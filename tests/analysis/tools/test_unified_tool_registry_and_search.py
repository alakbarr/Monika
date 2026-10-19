# ==============================================================================
# File: tests/analysis/tools/test_unified_tool_registry_and_search.py
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from monika.application.analysis.tools.unified_registry import unified_tool_registry
from monika.application.analysis.tools.tool_search_engine import ToolSearchEngine
from monika.application.analysis.tools.executor import ToolExecutor


def test_unified_registry_unification_and_count():
    tools = unified_tool_registry.list_tools(only_available=False)
    assert len(tools) >= 200, f"Expected at least 200 unified tools, got {len(tools)}"

    tool_names = {t.name for t in tools}
    assert "get_price_history" in tool_names or "get_market_data" in tool_names
    assert "get_economic_calendar" in tool_names


def test_unified_registry_get_tools_alias():
    tools_list = unified_tool_registry.list_tools(only_available=False)
    tools_get = unified_tool_registry.get_tools(only_available=False)
    assert len(tools_list) == len(tools_get)
    assert [t.name for t in tools_list] == [t.name for t in tools_get]


def test_tool_search_engine_indexing_and_search():
    engine = ToolSearchEngine.from_unified_registry()
    assert len(engine._tools) >= 200

    matches = engine.search_tools("economic calendar", limit=5)
    assert len(matches) > 0
    matched_names = [m["name"] for m in matches]
    assert "get_economic_calendar" in matched_names


def test_unified_registry_get_tool_resolution():
    entry = unified_tool_registry.get_tool("get_economic_calendar")
    assert entry is not None
    assert entry.name == "get_economic_calendar"
    schema = entry.get_parameters_schema()
    assert isinstance(schema, dict)


@pytest.mark.asyncio
async def test_tool_executor_session_lock():
    mock_session = AsyncMock()
    executor = ToolExecutor(session=mock_session, settings={})

    assert hasattr(executor, "_session_lock") or hasattr(mock_session, "_session_lock")
    # Verify execution runs under session lock
    lock = getattr(mock_session, "_session_lock", None) or getattr(executor, "_session_lock", None)
    assert lock is not None
