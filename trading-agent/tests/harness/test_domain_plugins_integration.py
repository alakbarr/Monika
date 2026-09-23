# ==============================================================================
# File: tests/harness/test_domain_plugins_integration.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock
from harness.contract import PluginCategory, PluginMetadata, TradingPlugin
from harness.engine import PluginEngine
from analysis.strategies.strategy_plugin import StrategyPlugin, wrap_strategy_as_plugin
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from risk.risk_rule_plugin import IRiskRulePlugin, ModularRiskRegistry, RiskRuleVerdict
from analysis.tools.tool_plugin import ToolPlugin
from analysis.tools.registry import ToolRegistry
from analysis.macro_pipeline_plugin import MacroToAssetPipeline
from execution.broker_registry import BrokerAdapterRegistry
from analysis.providers.provider_registry import ProviderRegistry


@pytest.mark.asyncio
async def test_strategy_plugin_domain_bridge():
    engine = PluginEngine()

    class SampleEdgeStrategy(EdgeStrategy):
        strategy_id = "test_alpha_plugin_123"

        async def analyze(self, session, symbol, timeframe="H1"):
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction="buy",
                valid=True,
                confidence=0.85,
            )

    strat_plugin = wrap_strategy_as_plugin(SampleEdgeStrategy)
    engine.register_plugin(strat_plugin)

    # Verify auto-bridged into StrategyRegistry
    retrieved = StrategyRegistry.get_strategy("test_alpha_plugin_123")
    assert retrieved is SampleEdgeStrategy


@pytest.mark.asyncio
async def test_risk_rule_plugin_domain_bridge():
    engine = PluginEngine()

    class CustomRiskRule(IRiskRulePlugin):
        metadata = PluginMetadata(
            id="custom_max_spread_rule",
            name="Max Spread Rule",
            version="1.0.0",
            category=PluginCategory.RISK_RULE,
        )

        async def validate_pre_order(self, session, symbol, direction, sizing, account_equity=None, **kwargs):
            return RiskRuleVerdict(rule_id=self.metadata.id, passed=True)

    rule = CustomRiskRule()
    engine.register_plugin(rule)

    risk_reg = ModularRiskRegistry.get_instance()
    rules = risk_reg.get_rules()
    assert any(r.metadata.id == "custom_max_spread_rule" for r in rules)


@pytest.mark.asyncio
async def test_tool_plugin_domain_bridge():
    engine = PluginEngine()

    class CustomMathToolPlugin(ToolPlugin):
        metadata = PluginMetadata(
            id="custom_math_tools",
            name="Custom Math Tools",
            version="1.0.0",
            category=PluginCategory.TOOL,
        )

        def get_tool_definitions(self):
            return []

        def get_handlers(self):
            async def _pivot_handler(args, **kwargs):
                return {"pivot": 1.2345}
            return {"calculate_pivot": _pivot_handler}

    tool_plugin = CustomMathToolPlugin()
    engine.register_plugin(tool_plugin)

    tool_reg = ToolRegistry.get_instance()
    assert tool_reg.has_tool("calculate_pivot")


@pytest.mark.asyncio
async def test_macro_to_asset_pipeline():
    engine = PluginEngine()
    mock_scheduler = MagicMock()
    mock_scheduler.run_cycle = AsyncMock(return_value=[])

    pipeline = MacroToAssetPipeline(scheduler=mock_scheduler)
    engine.register_plugin(pipeline)

    assert engine.active_pipeline is pipeline

    mock_session = AsyncMock()
    proposals = await pipeline.execute_analysis_cycle(mock_session, ["EURUSD", "GBPUSD"])
    assert proposals == []
    mock_scheduler.run_cycle.assert_awaited_once_with(mock_session, forced=False)

    telemetry = pipeline.get_pipeline_telemetry()
    assert telemetry["pipeline_id"] == "macro_to_asset"
    assert telemetry["cycles_completed"] == 1
    assert telemetry["scheduler_attached"] is True
