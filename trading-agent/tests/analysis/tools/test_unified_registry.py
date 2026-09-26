# ==============================================================================
# File: tests/analysis/tools/test_unified_registry.py
# Description: Unit tests for UnifiedToolRegistry and ToolEntry
# ==============================================================================

import pytest
from pydantic import BaseModel, Field
from analysis.tools.unified_registry import UnifiedToolRegistry, ToolEntry


class SampleArgs(BaseModel):
    symbol: str = Field(description="Ticker symbol")
    quantity: float = Field(default=1.0, description="Quantity to analyze")


@pytest.fixture
def registry():
    return UnifiedToolRegistry()


@pytest.mark.asyncio
async def test_unified_registry_pydantic_decorator(registry):
    @registry.register(
        name="analyze_risk",
        category="RISK",
        input_model=SampleArgs,
    )
    async def analyze_risk_handler(params: SampleArgs):
        return f"Risk evaluated for {params.symbol}: {params.quantity * 100}"

    tool = registry.get_tool("analyze_risk")
    assert tool is not None
    assert tool.name == "analyze_risk"
    assert tool.category == "RISK"

    # Test schemas
    anthropic = tool.get_anthropic_schema()
    assert anthropic["name"] == "analyze_risk"
    assert "input_schema" in anthropic
    assert anthropic["input_schema"]["properties"]["symbol"]["type"] == "string"

    openai = tool.get_openai_schema()
    assert openai["type"] == "function"
    assert openai["function"]["name"] == "analyze_risk"

    gemini = tool.get_gemini_schema()
    assert gemini["name"] == "analyze_risk"
    assert "parameters" in gemini

    # Test tool_call execution
    res = await registry.tool_call("analyze_risk", {"symbol": "EURUSD", "quantity": 2.0})
    assert "Risk evaluated for EURUSD: 200.0" in res


@pytest.mark.asyncio
async def test_unified_registry_register_tool_dynamic_schema(registry):
    async def dummy_handler(args):
        return {"market": args.get("market"), "status": "active"}

    entry = registry.register_tool(
        name="custom_mcp_query",
        category="MCP",
        handler=dummy_handler,
        parameters_schema={
            "type": "object",
            "properties": {
                "market": {"type": "string"},
            },
            "required": ["market"],
        },
        description="Dynamic MCP tool query",
        aliases=["mcp_query"],
    )

    assert registry.get_tool("custom_mcp_query") is entry
    assert registry.get_tool("mcp_query") is entry

    gemini = entry.get_gemini_schema()
    assert gemini["name"] == "custom_mcp_query"
    assert gemini["parameters"]["properties"]["market"]["type"] == "STRING"

    res = await registry.dispatch("custom_mcp_query", {"market": "FOREX"})
    assert "'status': 'active'" in res


@pytest.mark.asyncio
async def test_unified_registry_invalid_args_handling(registry):
    @registry.register(
        name="strict_tool",
        category="ANALYSIS",
        input_model=SampleArgs,
    )
    async def strict_handler(params: SampleArgs):
        return "ok"

    res = await registry.dispatch("strict_tool", {"quantity": "invalid_number_format_xyz"})
    assert "Error executing tool 'strict_tool'" in res or "Invalid arguments" in res


@pytest.mark.asyncio
async def test_unified_registry_output_spilling(registry):
    @registry.register(
        name="giant_output_tool",
        category="DATA",
        input_model=SampleArgs,
    )
    async def giant_handler(params: SampleArgs):
        return "X" * 25000

    res = await registry.tool_call("giant_output_tool", {"symbol": "BTCUSD"})
    assert len(res) < 25000
    assert "[Output truncated" in res or "spillover" in res or len(res) <= 12000
