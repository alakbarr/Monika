import json
from utils.llm.context_compaction import ContextCompactionEngine
from analysis.tools.tools_definitions import minify_tool_definitions, make_strict_tool_definitions


def test_micro_prune_large_json_preserves_structure():
    """Verify bulky JSON list (>2500 tokens) is condensed without broken brackets or syntax errors."""
    engine = ContextCompactionEngine()
    
    bulky_list = [
        {"item_id": i, "symbol": "EURUSD", "comment": f"Historical data row number {i} with long descriptive note"}
        for i in range(120)
    ]
    raw_json = json.dumps(bulky_list)
    assert len(raw_json) > 10000

    pruned = engine.micro_prune(raw_json, tool_name="get_custom_logs")
    parsed = json.loads(pruned)

    assert isinstance(parsed, list)
    # Head and tail preserved
    assert parsed[0]["item_id"] == 0
    assert parsed[-1]["item_id"] == 119
    # Omitted count indicator present
    assert any("_omitted_items_count" in item for item in parsed)


def test_minify_tool_definitions():
    """Verify tool minifier shortens descriptions while preserving required arguments and schema keys."""
    sample_tools = [
        {
            "name": "calculate_position_size",
            "description": "Calculates the exact position size based on risk and ATR buffer. Do not compute manually. Follow all institutional sizing rules.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "The financial instrument to be traded such as EURUSD or XAUUSD."},
                    "entry_price": {"type": "number", "description": "Exact price where the order will be filled."},
                    "stop_loss": {"type": "number", "description": "Exact invalidation price level."}
                },
                "required": ["symbol", "entry_price", "stop_loss"]
            }
        }
    ]
    minified = minify_tool_definitions(sample_tools)
    assert len(minified) == 1
    t = minified[0]
    assert t["name"] == "calculate_position_size"
    assert len(t["description"]) < len(sample_tools[0]["description"])
    assert t["input_schema"]["required"] == ["symbol", "entry_price", "stop_loss"]


def test_make_strict_tool_definitions():
    """Verify strict tool generator adds additionalProperties: False for OpenAI/DeepSeek structured function calls."""
    sample_tools = [
        {
            "name": "get_atr",
            "description": "Get ATR value.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {"type": "string"}
                },
                "required": ["symbol"]
            }
        }
    ]
    strict = make_strict_tool_definitions(sample_tools)
    schema = strict[0]["input_schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"symbol", "timeframe"}
