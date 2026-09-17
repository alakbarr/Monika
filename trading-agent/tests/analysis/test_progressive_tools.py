import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.tools.tool_registry import ProgressiveToolRegistry
from analysis.tools.handlers.category_loader import (
    handle_search_tools,
    handle_describe_tool,
    SearchToolsHandler,
    DescribeToolHandler,
)


def test_progressive_registry_search_tools():
    reg = ProgressiveToolRegistry()

    # Search for calendar
    calendar_matches = reg.search_tools("calendar", limit=3)
    assert len(calendar_matches) >= 1
    tool_names = [m["name"] for m in calendar_matches]
    assert any("calendar" in name for name in tool_names)

    # Search for technical / smc
    smc_matches = reg.search_tools("smc", limit=3)
    assert len(smc_matches) >= 1
    assert any("smc" in m["name"] for m in smc_matches)

    # Search empty returns empty
    assert reg.search_tools("") == []


def test_progressive_registry_describe_tool():
    reg = ProgressiveToolRegistry()

    # Known tool
    desc = reg.describe_tool("calculate_position_size")
    assert desc is not None
    assert desc["name"] == "calculate_position_size"
    assert "input_schema" in desc
    assert "symbol" in desc["input_schema"]["properties"]

    # Unknown tool
    unknown = reg.describe_tool("non_existent_tool_xyz")
    assert unknown is None


def test_progressive_registry_compact_schema():
    reg = ProgressiveToolRegistry()
    raw = reg.get_tool("calculate_position_size")
    assert raw is not None

    compact = reg.compact_schema(raw)
    assert compact["name"] == raw["name"]
    assert "input_schema" in compact
    assert "properties" in compact["input_schema"]
    assert "symbol" in compact["input_schema"]["properties"]

    # Check that descriptions in compact properties are shortened/trimmed
    raw_props = raw["input_schema"]["properties"]
    comp_props = compact["input_schema"]["properties"]
    for k in comp_props:
        if "desc" in comp_props[k]:
            assert len(comp_props[k]["desc"]) <= 70


def test_core_schemas_include_meta_tools():
    reg = ProgressiveToolRegistry()
    core_schemas = reg.get_core_schemas(stage="stage2")
    names = [s["name"] for s in core_schemas]
    assert "search_tools" in names
    assert "describe_tool" in names
    assert "load_tool_category" in names

    compact_core = reg.get_compact_core_schemas(stage="stage2")
    compact_names = [s["name"] for s in compact_core]
    assert "search_tools" in compact_names
    assert "describe_tool" in compact_names


@pytest.mark.asyncio
async def test_search_and_describe_handlers():
    # Test handle_search_tools
    res_search = await handle_search_tools({"query": "volatility", "limit": 2})
    assert isinstance(res_search, list)
    assert len(res_search) <= 2

    # Test handle_describe_tool
    res_desc = await handle_describe_tool({"tool_name": "get_market_quote"})
    assert "name" in res_desc
    assert res_desc["name"] == "get_market_quote"

    # Test describe unknown
    res_err = await handle_describe_tool({"tool_name": "unknown_tool"})
    assert "error" in res_err


@pytest.mark.asyncio
async def test_handler_classes_execution():
    session = AsyncMock()
    search_handler = SearchToolsHandler()
    desc_handler = DescribeToolHandler()

    res1 = await search_handler.execute({"query": "price"}, session=session)
    assert isinstance(res1, list)

    res2 = await desc_handler.execute({"tool_name": "calculate_position_size"}, session=session)
    assert res2["name"] == "calculate_position_size"
