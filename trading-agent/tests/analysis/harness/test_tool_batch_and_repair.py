# ==============================================================================
# File: tests/analysis/harness/test_tool_batch_and_repair.py
# ==============================================================================

import pytest
from analysis.harness.tool_batch_planner import ToolBatchPlanner
from analysis.harness.tool_repair import repair_tool_name, repair_tool_arguments


def test_tool_name_auto_repair():
    """Verify repair of hallucinated, namespaced, and prefixed tool names."""
    assert repair_tool_name("run_shell") == "web_search"
    assert repair_tool_name("tools.get_price_data") == "get_price_data"
    assert repair_tool_name("functions.get_bond_yield_spreads()") == "get_bond_yield_spreads"
    assert repair_tool_name("submit_submit_asset_analysis") == "submit_asset_analysis"
    assert repair_tool_name("fetch_price") == "get_price_data"
    assert repair_tool_name("calculate_size") == "calculate_position_size"
    assert repair_tool_name("market_snapshot") == "get_verified_market_snapshot"


def test_tool_arguments_auto_repair():
    """Verify repair of broken JSON, trailing commas, and python booleans."""
    # Valid dict
    assert repair_tool_arguments({"symbol": "EURUSD"}) == {"symbol": "EURUSD"}

    # Trailing commas
    bad_json = '{"symbol": "EURUSD", "timeframe": "H1",}'
    repaired = repair_tool_arguments(bad_json)
    assert repaired == {"symbol": "EURUSD", "timeframe": "H1"}

    # Python booleans & None
    py_json = '{"symbol": "XAUUSD", "is_prime": True, "filter": None}'
    repaired_py = repair_tool_arguments(py_json)
    assert repaired_py == {"symbol": "XAUUSD", "is_prime": True, "filter": None}


def test_tool_batch_segmented_planning():
    """Verify planning splits parallel tools and barriers into alternating segments."""
    planner = ToolBatchPlanner()

    tool_calls = [
        {"name": "get_price_data", "input": {"symbol": "EURUSD"}},
        {"name": "get_technical_analysis", "input": {"symbol": "EURUSD"}},
        {"name": "submit_asset_analysis", "input": {"symbol": "EURUSD", "decision": "buy"}},
        {"name": "get_news_items", "input": {"symbol": "EURUSD"}},
        {"name": "get_bond_yield_spreads", "input": {}},
    ]

    segments = planner.plan_segments(tool_calls)
    assert len(segments) == 3

    # Segment 1: Parallel (get_price_data, get_technical_analysis)
    assert segments[0][0] == "parallel"
    assert len(segments[0][1]) == 2

    # Segment 2: Sequential Barrier (submit_asset_analysis)
    assert segments[1][0] == "sequential"
    assert len(segments[1][1]) == 1
    assert segments[1][1][0]["name"] == "submit_asset_analysis"

    # Segment 3: Parallel (get_news_items, get_bond_yield_spreads)
    assert segments[2][0] == "parallel"
    assert len(segments[2][1]) == 2
