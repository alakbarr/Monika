# ==============================================================================
# File: tests/analysis/tools/test_registry.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from analysis.tools.registry import default_tool_registry, ToolRegistry, register_tool
from analysis.tools.base_handler import ToolHandler
from analysis.tools.executor import ToolExecutor


def test_registry_registration_and_aliases():
    """Verify tool registration, alias resolution, and category grouping."""
    registry = ToolRegistry()

    @registry.register
    class SampleHandler(ToolHandler):
        name = "sample_read_tool"
        aliases = ["sample_read", "read_sample"]
        category = "TECHNICAL"
        parallel_safe = True

        async def execute(self, args, session, executor=None, **kwargs):
            return {"status": "ok", "value": args.get("val", 0) * 2}

    assert "sample_read_tool" in registry.list_tools()
    assert registry.resolve_name("sample_read") == "sample_read_tool"
    assert registry.resolve_name("read_sample") == "sample_read_tool"
    assert registry.is_parallel_safe("sample_read_tool") is True
    assert "sample_read_tool" in registry.get_by_category("TECHNICAL")


def test_default_registry_has_core_handlers():
    """Verify default registry auto-discovery contains domain handlers."""
    tools = default_tool_registry.list_tools()
    expected_tools = [
        "get_price_data",
        "get_technical_analysis",
        "get_bond_yield_spreads",
        "get_fedwatch_probabilities",
        "get_open_positions",
        "calculate_position_size",
        "submit_asset_analysis",
        "submit_fundamental_brief",
        "get_verified_market_snapshot",
    ]
    for tool in expected_tools:
        assert tool in tools or default_tool_registry.resolve_name(tool) in tools, f"Missing tool {tool}"


def test_parallel_safety_flag():
    """Verify barriers are marked parallel_safe=False and read tools parallel_safe=True."""
    assert default_tool_registry.is_parallel_safe("submit_asset_analysis") is False
    assert default_tool_registry.is_parallel_safe("propose_action") is False
    assert default_tool_registry.is_parallel_safe("get_price_data") is True
    assert default_tool_registry.is_parallel_safe("get_technical_analysis") is True
    assert default_tool_registry.is_parallel_safe("get_verified_market_snapshot") is True


@pytest.mark.asyncio
async def test_tool_executor_verified_snapshot():
    """Verify ToolExecutor handles get_verified_market_snapshot."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_res.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_res

    executor = ToolExecutor(mock_session, settings={}, symbol="EURUSD")
    res = await executor.execute("get_verified_market_snapshot", {"symbol": "EURUSD"})

    assert isinstance(res, dict)
    assert res.get("symbol") == "EURUSD"
    assert res.get("status") == "VERIFIED_GROUND_TRUTH"
    assert "warning" in res
    assert "THIS IS DETERMINISTIC GROUND TRUTH" in res["warning"]


@pytest.mark.asyncio
async def test_legacy_tool_executor_dispatches_via_registry():
    """Verify analysis.tools.tool_executor.ToolExecutor dispatches seamlessly to default_tool_registry handlers."""
    from analysis.tools.tool_executor import ToolExecutor as LegacyToolExecutor

    @default_tool_registry.register
    class CustomDynamicHandler(ToolHandler):
        name = "custom_dynamic_test_tool"
        category = "TECHNICAL"
        parallel_safe = True

        async def execute(self, args, session, executor=None, **kwargs):
            return {"status": "custom_ok", "param": args.get("val", 0) + 42}

    mock_session = AsyncMock()
    legacy_exec = LegacyToolExecutor(mock_session, settings={}, symbol="EURUSD")
    res = await legacy_exec.execute("custom_dynamic_test_tool", {"val": 8})

    assert isinstance(res, dict)
    assert res.get("status") == "custom_ok"
    assert res.get("param") == 50

