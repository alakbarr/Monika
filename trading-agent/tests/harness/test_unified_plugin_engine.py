# ==============================================================================
# File: tests/harness/test_unified_plugin_engine.py
# ==============================================================================

import asyncio
import pytest
from typing import Dict, Any, List

from harness.contract import (
    TradingPlugin,
    PluginMetadata,
    PluginCategory,
    PluginOrigin,
)
from harness.context import PluginContext
from harness.engine import PluginEngine
from utils.infra.container import ServiceContainer
from utils.protocol.event_bus import EventBus
from analysis.prompt_sections import prompt_section_registry


class MockManifestPlugin(TradingPlugin):
    metadata = PluginMetadata(
        id="mock_manifest_plugin",
        name="Mock Manifest Plugin",
        version="1.0.0",
        category=PluginCategory.MIDDLEWARE,
    )

    def __init__(self, config=None):
        super().__init__(config)
        self.pre_tool_called = False
        self.pre_order_called = False
        self.tool_dispatched = False

    async def on_pre_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
        self.pre_tool_called = True

    async def on_pre_order(self, order_dict: Dict[str, Any]) -> Dict[str, Any]:
        self.pre_order_called = True
        return order_dict

    async def custom_tool_handler(self, symbol: str) -> Dict[str, Any]:
        self.tool_dispatched = True
        return {"status": "ok", "symbol": symbol}


class SlowHookPlugin(TradingPlugin):
    metadata = PluginMetadata(
        id="slow_hook_plugin",
        name="Slow Hook Plugin",
        version="1.0.0",
        category=PluginCategory.MIDDLEWARE,
    )

    def on_context_ready(self, ctx: PluginContext) -> None:
        async def slow_handler(*args, **kwargs):
            await asyncio.sleep(10.0)

        ctx.register_hook("pre_tool_call", slow_handler)


@pytest.fixture
def test_container():
    c = ServiceContainer()
    c.register("config", {"trading": {"symbols": ["EURUSD"]}})
    c.register("event_bus", EventBus())
    return c


@pytest.mark.asyncio
async def test_unified_engine_context_and_hook_wiring(test_container):
    engine = PluginEngine(container=test_container, event_bus=test_container.get("event_bus"))
    plugin = MockManifestPlugin()

    # Manually assign manifest hooks & tools simulation
    plugin.manifest = {
        "hooks": {
            "pre_tool_call": "on_pre_tool",
            "pre_order": "on_pre_order",
        },
        "tools": {
            "mock_custom_tool": "custom_tool_handler"
        }
    }

    engine.register_plugin(plugin)
    assert "mock_manifest_plugin" in engine.plugins
    assert plugin.context is not None

    # Verify manifest hooks auto-wired into manager
    handlers = engine.manager.get_handlers("pre_tool_call")
    assert len(handlers) >= 1

    # Verify manifest tools registered into manager
    assert "mock_custom_tool" in engine.manager.registered_tools

    # Emit pre_tool_call hook
    await engine.manager.emit("pre_tool_call", tool_name="fetch_news", tool_args={"query": "fed"})
    assert plugin.pre_tool_called is True

    # Emit pre_order waterfall
    allowed, res = await engine.manager.emit_waterfall("pre_order", {"symbol": "EURUSD", "volume": 0.1})
    assert plugin.pre_order_called is True
    assert allowed is True
    assert res == {"symbol": "EURUSD", "volume": 0.1}

    # Dispatch registered tool
    tool_res = await engine.manager.execute_tool("mock_custom_tool", symbol="XAUUSD")
    assert plugin.tool_dispatched is True
    assert tool_res == {"status": "ok", "symbol": "XAUUSD"}


@pytest.mark.asyncio
async def test_protected_tool_override_rejected(test_container):
    engine = PluginEngine(container=test_container, event_bus=test_container.get("event_bus"))
    plugin = MockManifestPlugin()

    engine.register_plugin(plugin)
    ctx = plugin.context
    assert ctx is not None

    # Attempt to override core protected tool (e.g. execute_order, risk_check)
    with pytest.raises(PermissionError) as exc_info:
        ctx.register_tool("execute_order", lambda *a, **kw: {"hijacked": True})

    assert "protected core tool" in str(exc_info.value)
    assert "execute_order" not in engine.manager.registered_tools


@pytest.mark.asyncio
async def test_hook_timeout_isolation(test_container):
    engine = PluginEngine(container=test_container, event_bus=test_container.get("event_bus"))
    plugin = SlowHookPlugin()

    engine.register_plugin(plugin)
    assert len(engine.manager.get_handlers("pre_tool_call")) >= 1

    # Emitting pre_tool_call should not hang or crash when handler exceeds timeout
    # Handler will be cancelled/timed out, but emit should complete without raising
    # Note: PluginManager default timeout is 5.0s, emit will handle timeout gracefully
    await engine.manager.emit("pre_tool_call", tool_name="test_tool")


@pytest.mark.asyncio
async def test_prompt_section_registration_via_context(test_container):
    engine = PluginEngine(container=test_container, event_bus=test_container.get("event_bus"))
    plugin = MockManifestPlugin()
    engine.register_plugin(plugin)

    ctx = plugin.context
    assert ctx is not None

    def my_prompt_builder():
        return "EXTRA_SYSTEM_INSTRUCTIONS"

    ctx.register_system_prompt_section("before_instructions", my_prompt_builder)

    sections = prompt_section_registry.get_sections("before_instructions")
    assert "EXTRA_SYSTEM_INSTRUCTIONS" in sections

    rendered = prompt_section_registry.render_prefix()
    assert "EXTRA_SYSTEM_INSTRUCTIONS" in rendered
