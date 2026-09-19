import pytest
from pydantic import BaseModel, Field

from analysis.tools.unified_registry import UnifiedToolRegistry
from analysis.tools.kernel.env_sanitizer import sanitize_environment
from analysis.tools.kernel.output_spiller import truncate_and_spill_output


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
    
    # Anthropic schema check
    anthropic_schemas = registry.get_anthropic_tools()
    target = next((s for s in anthropic_schemas if s["name"] == "test_get_quote"), None)
    assert target is not None
    assert "properties" in target["input_schema"]
    assert "symbol" in target["input_schema"]["properties"]

    # OpenAI schema check
    openai_schemas = registry.get_openai_tools()
    target_oa = next((s for s in openai_schemas if s["function"]["name"] == "test_get_quote"), None)
    assert target_oa is not None
    assert target_oa["type"] == "function"


@pytest.mark.asyncio
async def test_unified_registry_dispatch():
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
