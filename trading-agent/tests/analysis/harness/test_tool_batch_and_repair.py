# ==============================================================================
# File: tests/analysis/harness/test_tool_batch_and_repair.py
# ==============================================================================

import pytest
from analysis.harness.tool_batch_planner import ToolBatchPlanner
from analysis.harness.tool_repair import repair_tool_name, repair_tool_arguments, coerce_tool_arguments


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


def test_coerce_tool_arguments():
    """Verify coercion of stringified numbers, booleans, and floats to match JSON schema types."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "timeframe": {"type": "string"},
            "limit": {"type": "integer"},
            "threshold": {"type": "number"},
            "as_csv": {"type": "boolean"},
        },
    }

    # Test '20' string -> 20 integer (exact BTCUSD issue)
    args = {"symbol": "BTCUSD", "timeframe": "M15", "limit": "20", "threshold": "1.234", "as_csv": "true"}
    coerced = coerce_tool_arguments(args, schema)
    assert coerced["limit"] == 20
    assert isinstance(coerced["limit"], int)
    assert coerced["threshold"] == 1.234
    assert isinstance(coerced["threshold"], float)
    assert coerced["as_csv"] is True

    # Test float with .0 -> integer
    args2 = {"limit": 50.0, "as_csv": "false"}
    coerced2 = coerce_tool_arguments(args2, schema)
    assert coerced2["limit"] == 50
    assert isinstance(coerced2["limit"], int)
    assert coerced2["as_csv"] is False

    # Test invalid string stays un-coerced for jsonschema to report
    args3 = {"limit": "not_an_int"}
    coerced3 = coerce_tool_arguments(args3, schema)
    assert coerced3["limit"] == "not_an_int"


def test_coerce_xml_parameter_to_object():
    """Verify XML parameter tag string is parsed into an object for object-type fields."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "reevaluation_trigger": {"type": ["object", "null"]},
        },
    }
    raw_xml = '<parameter name="type">\nprice_level</parameter>'
    args = {"symbol": "AUDUSD", "reevaluation_trigger": raw_xml}
    coerced = coerce_tool_arguments(args, schema)
    assert isinstance(coerced["reevaluation_trigger"], dict)
    assert coerced["reevaluation_trigger"]["type"] == "price_level"


def test_coerce_string_to_array():
    """Verify string is coerced into an array of strings for array-type fields."""
    schema = {
        "type": "object",
        "properties": {
            "key_news_events_considered": {"type": ["array", "null"], "items": {"type": "string"}},
        },
    }
    args = {"key_news_events_considered": "No major news in last 6 hours. Economic calendar clear for AUD/USD."}
    coerced = coerce_tool_arguments(args, schema)
    assert isinstance(coerced["key_news_events_considered"], list)
    assert coerced["key_news_events_considered"] == ["No major news in last 6 hours. Economic calendar clear for AUD/USD."]


def test_coerce_missing_timeframe_default():
    """Verify missing required timeframe is auto-injected with default H1."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "timeframe": {"type": "string", "enum": ["M15", "H1", "H4", "D1"], "default": "H1"},
        },
        "required": ["symbol", "timeframe"],
    }
    args = {"symbol": "XBRUSD"}
    coerced = coerce_tool_arguments(args, schema)
    assert coerced["timeframe"] == "H1"


def test_coerce_timeframe_m15_to_h1():
    """Verify M15 timeframe is coerced to H1 when tool only supports ['H1', 'H4', 'D1']."""
    schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "timeframe": {"type": "string", "enum": ["H1", "H4", "D1"]},
        },
        "required": ["symbol", "timeframe"],
    }
    args = {"symbol": "BTCUSD", "timeframe": "M15"}
    coerced = coerce_tool_arguments(args, schema)
    assert coerced["timeframe"] == "H1"


