import pytest
from analysis.tools.tool_registry import ProgressiveToolRegistry, default_registry


def test_registry_init_and_get_tool():
    registry = ProgressiveToolRegistry()
    calc_tool = registry.get_tool("calculate_position_size")
    assert calc_tool is not None
    assert calc_tool["name"] == "calculate_position_size"
    assert "input_schema" in calc_tool


def test_registry_core_schemas():
    registry = ProgressiveToolRegistry()
    stage1_core = registry.get_core_schemas(stage="stage1")
    names1 = [t["name"] for t in stage1_core]
    assert "load_tool_category" in names1
    assert "calculate_position_size" in names1

    stage2_core = registry.get_core_schemas(stage="stage2")
    names2 = [t["name"] for t in stage2_core]
    assert "load_tool_category" in names2
    assert "calculate_position_size" in names2


def test_registry_load_category():
    registry = ProgressiveToolRegistry()
    macro_tools = registry.load_category("MACRO")
    names = [t["name"] for t in macro_tools]
    assert "get_market_session" in names
    assert "get_economic_calendar" in names

    tech_tools = registry.load_category("TECHNICAL")
    tech_names = [t["name"] for t in tech_tools]
    assert "get_price_history" in tech_names
    assert "get_technical_indicators" in tech_names


def test_registry_stub_summary():
    registry = ProgressiveToolRegistry()
    summary = registry.get_stub_summary()
    assert "AVAILABLE TOOL CATEGORIES" in summary
    assert "MACRO:" in summary
    assert "TECHNICAL:" in summary
