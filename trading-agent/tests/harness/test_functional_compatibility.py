# ==============================================================================
# File: tests/harness/test_functional_compatibility.py
# ==============================================================================

import os
import sys
import yaml
import pytest
import tempfile
from pathlib import Path
from typing import Dict, Any

from harness.contract import PluginCategory
from harness.context import PluginContext
from harness.engine import PluginEngine, FunctionalPluginAdapter
from harness.adapters.functional_adapter import (
    FunctionalPluginBridge,
    script_constants,
    tools,
)
from utils.infra.container import ServiceContainer
from utils.protocol.event_bus import EventBus
from analysis.prompt_sections import prompt_section_registry


@pytest.fixture
def test_container():
    c = ServiceContainer()
    c.register("config", {"trading": {"symbols": ["EURUSD"]}})
    c.register("event_bus", EventBus())
    return c


def test_runtime_shims_available():
    """Verify runtime compatibility shims are accessible and functional."""
    assert script_constants.DEFAULT_TIMEOUT == 5.0
    assert script_constants.CORE_TOOLS is not None
    assert "execute_order" in script_constants.CORE_TOOLS

    # Test tools.registry shim
    def dummy_tool(x: int) -> int:
        return x * 2

    tools.registry.registry.register_tool("shim_tool", dummy_tool)
    assert tools.registry.registry.has_tool("shim_tool")
    assert tools.registry.registry.get_tool("shim_tool")(5) == 10


@pytest.mark.asyncio
async def test_register_functional_pattern(test_container):
    """Verify that a standard register(ctx) script entry point executes cleanly."""
    engine = PluginEngine(container=test_container, event_bus=test_container.get("event_bus"))

    called_hooks = []

    def script_register(ctx: PluginContext):
        async def on_pre_tool(tool_name: str, tool_args: Dict[str, Any]):
            called_hooks.append((tool_name, tool_args))

        ctx.register_hook("pre_tool_call", on_pre_tool)
        ctx.register_tool("script_calc", lambda a, b: a + b)
        ctx.register_system_prompt_section("after_memory", lambda: "SCRIPT_MEMORY_GUARD")

    adapter = FunctionalPluginAdapter(
        plugin_id="script_dummy_calc",
        name="Script Dummy Calc",
        register_fn=script_register,
        category=PluginCategory.MIDDLEWARE,
    )

    engine.register_plugin(adapter)
    assert "script_dummy_calc" in engine.plugins

    # Test hook execution
    await engine.manager.emit("pre_tool_call", tool_name="fetch_calendar", tool_args={"limit": 5})
    assert len(called_hooks) == 1
    assert called_hooks[0] == ("fetch_calendar", {"limit": 5})

    # Test tool execution
    res = await engine.manager.execute_tool("script_calc", a=10, b=25)
    assert res == 35

    # Test prompt section execution
    sections = prompt_section_registry.get_sections("after_memory")
    assert "SCRIPT_MEMORY_GUARD" in sections


@pytest.mark.asyncio
async def test_functional_plugin_bridge_directory_loader(test_container):
    """Test loading an authentic standalone script plugin directory structure via FunctionalPluginBridge."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        plugin_dir = Path(tmp_dir) / "sample_script_plugin"
        plugin_dir.mkdir()

        # Write plugin.yaml
        manifest_data = {
            "name": "sample_cleaner_plugin",
            "version": "1.0.0",
            "author": "Monika Community",
            "description": "Sample Script Plugin",
            "entrypoint": "plugin.py",
            "hooks": ["pre_tool_call", "post_tool_call"],
        }
        with open(plugin_dir / "plugin.yaml", "w", encoding="utf-8") as f:
            yaml.dump(manifest_data, f)

        # Write plugin.py
        code = """
audit_log = []

def register(ctx):
    async def on_post_tool(tool_name, tool_result):
        audit_log.append(tool_name)
    ctx.register_hook("post_tool_call", on_post_tool)
    ctx.register_tool("get_cleaner_status", lambda: {"clean": True})
"""
        with open(plugin_dir / "plugin.py", "w", encoding="utf-8") as f:
            f.write(code)

        # Bridge loads directory into TradingPlugin
        plugin = FunctionalPluginBridge.load_plugin(plugin_dir)
        assert plugin is not None
        assert plugin.metadata.id == "sample_cleaner_plugin"
        assert plugin.metadata.author == "Monika Community"

        # Register into PluginEngine
        engine = PluginEngine(container=test_container, event_bus=test_container.get("event_bus"))
        engine.register_plugin(plugin)

        # Execute registered tool
        res = await engine.manager.execute_tool("get_cleaner_status")
        assert res == {"clean": True}

        # Emit post_tool_call hook
        await engine.manager.emit("post_tool_call", tool_name="order_place", tool_result={"id": 123})
        # Check module state
        mod = getattr(plugin, "_module", None)
        assert mod is not None
        assert "order_place" in mod.audit_log
