"""Unit tests for ToolRegistry and modular tool handlers (Phase 5)."""

import pytest
from analysis.tools.registry import ToolRegistry, ToolDefinition, default_tool_registry
import analysis.tools.handlers  # triggers self-registration


def test_tool_registry_singleton():
    reg1 = ToolRegistry.get_instance()
    reg2 = ToolRegistry.get_instance()
    assert reg1 is reg2
    assert reg1 is default_tool_registry


def test_tool_registry_has_registered_tools():
    reg = ToolRegistry.get_instance()
    market_tools = reg.get_available_tools(toolsets={"market_data"})
    assert len(market_tools) >= 5

    macro_tools = reg.get_available_tools(toolsets={"macro"})
    assert len(macro_tools) >= 5

    sentiment_tools = reg.get_available_tools(toolsets={"sentiment"})
    assert len(sentiment_tools) >= 4

    trading_tools = reg.get_available_tools(toolsets={"trading"})
    assert len(trading_tools) >= 4

    smc_tools = reg.get_available_tools(toolsets={"smc"})
    assert len(smc_tools) >= 4


def test_tool_definition_availability():
    t_avail = ToolDefinition(
        name="test_tool_1",
        description="Always available",
        parameters={},
        handler=lambda args, **ctx: "ok",
        check_fn=lambda: True,
    )
    assert t_avail.is_available() is True

    t_unavail = ToolDefinition(
        name="test_tool_2",
        description="Disabled tool",
        parameters={},
        handler=lambda args, **ctx: "ok",
        check_fn=lambda: False,
    )
    assert t_unavail.is_available() is False


def test_tool_registry_schemas_format():
    reg = ToolRegistry.get_instance()
    schemas = reg.get_schemas(toolsets={"market_data"})
    assert len(schemas) > 0
    first = schemas[0]
    assert first["type"] == "function"
    assert "name" in first["function"]
    assert "description" in first["function"]
    assert "parameters" in first["function"]


@pytest.mark.asyncio
async def test_tool_registry_dispatch():
    reg = ToolRegistry.get_instance()

    async def sample_handler(args, **ctx):
        return f"result for {args.get('item')}"

    reg.register(ToolDefinition(
        name="sample_tool",
        description="A sample tool for testing dispatch",
        parameters={"type": "object"},
        handler=sample_handler,
        toolset="test",
    ))

    res = await reg.dispatch("sample_tool", {"item": "gold"})
    assert res["is_error"] is False
    assert res["content"] == "result for gold"

    # Unknown tool
    res_err = await reg.dispatch("non_existent_tool", {})
    assert res_err["is_error"] is True
    assert "Unknown tool" in res_err["error"]


@pytest.mark.asyncio
async def test_tool_definition_execute_duck_typing():
    """Verify ToolDefinition can be executed via .execute(...) like legacy ToolHandler."""
    async def sample_handler(args, **ctx):
        session = ctx.get("session")
        return f"executed for {args.get('item')} with session={session}"

    tdef = ToolDefinition(
        name="duck_tool",
        description="Duck typing test",
        parameters={},
        handler=sample_handler,
    )
    res = await tdef.execute({"item": "silver"}, session="mock_sess")
    assert res == "executed for silver with session=mock_sess"

