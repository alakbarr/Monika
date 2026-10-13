# ==============================================================================
# File: tests/analysis/tools/test_unified_registry.py
# Description: Unit tests for UnifiedToolRegistry and ToolEntry
# ==============================================================================

import pytest
from pydantic import BaseModel, Field
from monika.application.analysis.tools.unified_registry import UnifiedToolRegistry, ToolEntry
from monika.application.analysis.tools.kernel.env_sanitizer import sanitize_environment
from monika.application.analysis.tools.kernel.output_spiller import truncate_and_spill_output


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


class MockQuoteArgs(BaseModel):
    symbol: str = Field(description="Trading symbol e.g. EURUSD")
    timeframe: str = Field(default="H1", description="Chart timeframe")


def test_unified_registry_registration_and_schema():
    registry = UnifiedToolRegistry()

    @registry.register(
        name="test_get_quote",
        category="market_data",
        input_model=MockQuoteArgs,
    )
    async def get_quote_handler(args: MockQuoteArgs) -> dict:
        """Fetch live quote for a symbol."""
        return {"symbol": args.symbol, "bid": 1.0850, "ask": 1.0852}

    tools = registry.list_tools()
    assert any(t.name == "test_get_quote" for t in tools)

    anthropic_schemas = registry.get_anthropic_tools()
    target = next((s for s in anthropic_schemas if s["name"] == "test_get_quote"), None)
    assert target is not None
    assert "properties" in target["input_schema"]
    assert "symbol" in target["input_schema"]["properties"]

    openai_schemas = registry.get_openai_tools()
    target_oa = next((s for s in openai_schemas if s["function"]["name"] == "test_get_quote"), None)
    assert target_oa is not None
    assert target_oa["type"] == "function"


@pytest.mark.asyncio
async def test_unified_registry_dispatch_calculator():
    registry = UnifiedToolRegistry()

    class CalcArgs(BaseModel):
        a: int = 0
        b: int = 0

    @registry.register(
        name="test_calculator",
        category="math",
        input_model=CalcArgs,
    )
    async def calc_handler(args: CalcArgs) -> int:
        """Add two numbers."""
        return args.a + args.b

    result = await registry.dispatch("test_calculator", {"a": 10, "b": 25})
    assert result == "35"


def test_env_sanitizer_redacts_credentials():
    dirty_env = {
        "PATH": "C:\\Windows\\system32",
        "MT5_PASSWORD": "supersecretpassword",
        "ANTHROPIC_API_KEY": "sk-ant-api03-xxxx",
        "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/monika",
        "OPENAI_API_KEY": "sk-proj-yyyy",
        "SAFE_PARAM": "standard_value",
    }

    clean_env = sanitize_environment(dirty_env)
    assert "MT5_PASSWORD" not in clean_env
    assert "ANTHROPIC_API_KEY" not in clean_env
    assert "DATABASE_URL" not in clean_env
    assert "OPENAI_API_KEY" not in clean_env
    assert clean_env.get("PATH") == "C:\\Windows\\system32"
    assert clean_env.get("SAFE_PARAM") == "standard_value"


def test_output_spiller_truncation():
    small_text = "Standard short log line"
    res, spilled = truncate_and_spill_output(small_text, tool_name="test_tool", max_chars=100)
    assert res == small_text
    assert spilled is False

    long_text = "HEAD_LINE\n" + ("x" * 500) + "\nTAIL_LINE"
    res2, spilled2 = truncate_and_spill_output(long_text, tool_name="test_tool", max_chars=50)
    assert spilled2 is True
    assert "TRUNCATED" in res2 or "spilled" in res2
