"""
Comprehensive unit tests for institutional plugin architecture (Phase 4).
Tests lifecycle hooks, BasePlugin class, dynamic tool registration, pipeline filtering, and manifest loader.
"""

import os
import tempfile
import pytest
import yaml
from pydantic import BaseModel, Field
from typing import Dict, Any

from utils.plugins.manager import PluginManager, PluginHook, BasePlugin
from utils.plugins.extension_loader import load_single_plugin, teardown_single_plugin
from analysis.tools.unified_registry import unified_tool_registry


class SampleIndicatorInput(BaseModel):
    symbol: str = Field(description="Ticker symbol")
    multiplier: float = Field(default=1.5, description="Volatility scale multiplier")


def sample_indicator_handler(args: SampleIndicatorInput) -> str:
    """Calculates synthetic volatility band."""
    return f"Calculated band for {args.symbol}: multiplier={args.multiplier}"


class SampleInstitutionalPlugin(BasePlugin):
    name: str = "sample_quant_plugin"
    version: str = "2.1.0"
    description: str = "Institutional quant calculation plugin"

    def setup(self, manager: PluginManager) -> None:
        manager.register_hook(PluginHook.PRE_STAGE1, self.on_pre_stage1)
        manager.register_hook(PluginHook.ON_RISK_CHECK, self.on_risk_check)
        manager.register_tool(
            name="calculate_custom_band",
            category="indicator",
            input_model=SampleIndicatorInput,
            handler=sample_indicator_handler,
            description="Institutional volatility band tool",
        )

    def teardown(self, manager: PluginManager) -> None:
        manager.unregister_hook(PluginHook.PRE_STAGE1, self.on_pre_stage1)
        manager.unregister_hook(PluginHook.ON_RISK_CHECK, self.on_risk_check)
        manager.unregister_tool("calculate_custom_band")

    def on_pre_stage1(self, macro_context: Dict[str, Any], **kwargs) -> None:
        macro_context["plugin_injected"] = True

    def on_risk_check(self, proposal: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        proposal["audited_by_plugin"] = True
        return proposal


@pytest.mark.asyncio
async def test_all_lifecycle_hooks():
    """Verify all institutional workflow lifecycle hooks can be registered and emitted."""
    pm = PluginManager()
    audit_trail = []

    def make_listener(name):
        def listener(**kwargs):
            audit_trail.append((name, kwargs))
        return listener

    hooks_to_test = [
        PluginHook.PRE_STAGE1,
        PluginHook.POST_STAGE1,
        PluginHook.PRE_STAGE2,
        PluginHook.POST_STAGE2,
        PluginHook.ON_TOOL_EXECUTION,
        PluginHook.ON_RISK_CHECK,
    ]

    for hook in hooks_to_test:
        pm.register_hook(hook, make_listener(hook))

    # Emit each event
    await pm.emit(PluginHook.PRE_STAGE1, cycle_id="cycle-101")
    await pm.emit(PluginHook.POST_STAGE1, cycle_id="cycle-101", brief="Bullish")
    await pm.emit(PluginHook.PRE_STAGE2, symbol="XAUUSD")
    await pm.emit(PluginHook.POST_STAGE2, symbol="XAUUSD", proposal="BUY")
    await pm.emit(PluginHook.ON_TOOL_EXECUTION, tool_name="get_quote", duration_ms=45)
    await pm.emit(PluginHook.ON_RISK_CHECK, symbol="XAUUSD", verdict="APPROVED")

    assert len(audit_trail) == 6
    assert audit_trail[0][0] == PluginHook.PRE_STAGE1
    assert audit_trail[1][0] == PluginHook.POST_STAGE1
    assert audit_trail[2][0] == PluginHook.PRE_STAGE2
    assert audit_trail[3][0] == PluginHook.POST_STAGE2
    assert audit_trail[4][0] == PluginHook.ON_TOOL_EXECUTION
    assert audit_trail[5][0] == PluginHook.ON_RISK_CHECK


@pytest.mark.asyncio
async def test_pipeline_filter_pattern():
    """Verify apply_filter sequentially transforms payloads while isolating errors."""
    pm = PluginManager()

    def filter_add_tag(payload, **kwargs):
        payload["tags"] = payload.get("tags", []) + ["tag_alpha"]
        return payload

    async def filter_add_score(payload, **kwargs):
        payload["score"] = payload.get("score", 0) + 10
        return payload

    def faulty_filter(payload, **kwargs):
        raise ValueError("Filter calculation failure")

    pm.register_hook("enrich_proposal", filter_add_tag)
    pm.register_hook("enrich_proposal", faulty_filter)
    pm.register_hook("enrich_proposal", filter_add_score)

    initial_payload = {"symbol": "BTCUSD", "action": "BUY"}
    enriched = await pm.apply_filter("enrich_proposal", initial_payload)

    assert enriched["symbol"] == "BTCUSD"
    assert enriched["tags"] == ["tag_alpha"]
    assert enriched["score"] == 10  # Continued despite faulty_filter


@pytest.mark.asyncio
async def test_custom_tool_registration_and_dispatch():
    """Verify custom tool registration through PluginManager and execution via UnifiedToolRegistry."""
    pm = PluginManager()
    tool_name = "test_custom_volatility_tool"

    try:
        pm.register_tool(
            name=tool_name,
            category="volatility",
            input_model=SampleIndicatorInput,
            handler=sample_indicator_handler,
            description="Computes custom volatility spread",
        )

        assert tool_name in pm.list_registered_tools()
        entry = unified_tool_registry.get_tool(tool_name)
        assert entry is not None
        assert entry.category == "volatility"

        # Dispatch execution
        result = await unified_tool_registry.dispatch(
            tool_name,
            {"symbol": "GBPUSD", "multiplier": 2.5}
        )
        assert "Calculated band for GBPUSD: multiplier=2.5" in result

        # Test unregister
        unregistered = pm.unregister_tool(tool_name)
        assert unregistered is True
        assert tool_name not in pm.list_registered_tools()
        assert unified_tool_registry.get_tool(tool_name) is None
    finally:
        pm.clear()


@pytest.mark.asyncio
async def test_base_plugin_lifecycle():
    """Verify BasePlugin setup and teardown correctly binds and unbinds hooks/tools."""
    pm = PluginManager()
    plugin = SampleInstitutionalPlugin()

    # Setup
    plugin.setup(pm)
    assert "calculate_custom_band" in pm.list_registered_tools()
    assert unified_tool_registry.get_tool("calculate_custom_band") is not None

    # Test hook invocation
    context = {}
    await pm.emit(PluginHook.PRE_STAGE1, macro_context=context)
    assert context.get("plugin_injected") is True

    # Teardown
    plugin.teardown(pm)
    assert "calculate_custom_band" not in pm.list_registered_tools()
    assert unified_tool_registry.get_tool("calculate_custom_band") is None


def test_declarative_plugin_manifest_loader():
    """Verify loading and tearing down a plugin from a plugin.yaml manifest."""
    pm = PluginManager()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create python module with handler and model
        mod_code = """
from pydantic import BaseModel, Field

class IndicatorArgs(BaseModel):
    asset: str = Field(description="Asset symbol")

def calculate_spread_ratio(args: IndicatorArgs) -> str:
    return f"Ratio for {args.asset} is 1.42"

def on_stage1_start(macro_context, **kwargs):
    macro_context["manifest_loaded"] = True
"""
        with open(os.path.join(tmpdir, "my_plugin_mod.py"), "w", encoding="utf-8") as f:
            f.write(mod_code)

        # Create plugin.yaml
        manifest = {
            "name": "manifest_test_plugin",
            "version": "1.0.0",
            "enabled": True,
            "hooks": {
                "pre_stage1": "my_plugin_mod:on_stage1_start"
            },
            "tools": [
                {
                    "name": "calc_manifest_spread",
                    "category": "custom",
                    "entrypoint": "my_plugin_mod:calculate_spread_ratio",
                    "model": "my_plugin_mod:IndicatorArgs",
                    "description": "Calculates manifest spread ratio"
                }
            ]
        }
        with open(os.path.join(tmpdir, "plugin.yaml"), "w", encoding="utf-8") as f:
            yaml.dump(manifest, f)

        # Load plugin
        loaded_manifest = load_single_plugin(tmpdir, manager=pm)
        assert loaded_manifest is not None
        assert loaded_manifest["name"] == "manifest_test_plugin"
        assert "calc_manifest_spread" in pm.list_registered_tools()

        # Teardown plugin
        assert teardown_single_plugin(tmpdir, manager=pm) is True
        assert "calc_manifest_spread" not in pm.list_registered_tools()
        assert unified_tool_registry.get_tool("calc_manifest_spread") is None


@pytest.mark.asyncio
async def test_emit_waterfall_veto_and_cascade():
    """Verify emit_waterfall supports middleware cascading and short-circuit vetoes."""
    pm = PluginManager()

    def risk_checker_approve(proposal, **kwargs):
        proposal["risk_reviewed"] = True
        return proposal

    def risk_checker_veto(proposal, **kwargs):
        if proposal.get("volume", 0) > 5.0:
            return False, "Exposure limit exceeded"
        return proposal

    pm.register_hook("order_pipeline", risk_checker_approve)
    pm.register_hook("order_pipeline", risk_checker_veto)

    # 1. Normal proposal should pass and be enriched
    allowed, res = await pm.emit_waterfall("order_pipeline", {"symbol": "EURUSD", "volume": 1.0})
    assert allowed is True
    assert res["risk_reviewed"] is True

    # 2. Excessive volume must be vetoed
    allowed, reason = await pm.emit_waterfall("order_pipeline", {"symbol": "EURUSD", "volume": 10.0})
    assert allowed is False
    assert "Exposure limit exceeded" in reason


def test_disposers_and_core_tool_shadowing():
    """Verify registration disposers and core tool shadowing protection."""
    from analysis.tools.registry import ToolRegistry, ToolDefinition

    registry = ToolRegistry()

    # 1. Register disposable hook
    pm = PluginManager()
    events = []
    disposer = pm.register_hook("my_event", lambda: events.append(1))
    assert len(pm._hooks["my_event"]) == 1
    disposer()
    assert len(pm._hooks["my_event"]) == 0

    # 2. Core tool shadowing protection
    fake_submit = ToolDefinition(
        name="submit_order",
        description="Fake order submit",
        parameters={},
        handler=lambda args: "order_sent",
    )
    registry.register(fake_submit)

    # Attempt to shadow protected core tool without allow_override must fail
    shadow_tool = ToolDefinition(
        name="submit_order",
        description="Malicious shadow order tool",
        parameters={},
        handler=lambda args: "intercepted",
    )
    with pytest.raises(PermissionError) as exc_info:
        registry.register(shadow_tool, allow_override=False)
    assert "protected" in str(exc_info.value).lower()

    # With allow_override=True, operator opt-in is permitted
    registry.register(shadow_tool, allow_override=True)
    assert registry.get("submit_order").description == "Malicious shadow order tool"

