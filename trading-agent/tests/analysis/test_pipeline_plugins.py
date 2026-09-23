# ==============================================================================
# File: tests/analysis/test_pipeline_plugins.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock

from analysis.pipeline_plugin import AnalysisPipelinePlugin
from harness.contract import PluginCategory
from plugins.analysis_pipelines.macro_to_asset.macro_to_asset_pipeline import MacroToAssetPipeline
from plugins.analysis_pipelines.technical_scalping.scalping_pipeline import TechnicalScalpingPipeline
from harness.engine import PluginEngine
from utils.infra.container import ServiceContainer
from utils.protocol.event_bus import EventBus


@pytest.mark.asyncio
async def test_macro_to_asset_pipeline_lifecycle():
    pipeline = MacroToAssetPipeline(config={"enable_debate": True})
    assert pipeline.metadata.id == "macro_to_asset"
    assert pipeline.metadata.category == PluginCategory.ANALYSIS_PIPELINE
    assert pipeline.metadata.is_core is True

    container = ServiceContainer()
    event_bus = EventBus()
    await pipeline.on_register(container, event_bus)

    passed, warnings = await pipeline.on_preflight(container)
    assert passed is True

    mock_session = AsyncMock()
    proposals = await pipeline.execute_analysis_cycle(mock_session, ["EURUSD", "XAUUSD"])
    assert isinstance(proposals, list)

    telemetry = pipeline.get_pipeline_telemetry()
    assert telemetry["pipeline"] == "macro_to_asset"
    assert telemetry["assets_evaluated"] == 2


@pytest.mark.asyncio
async def test_technical_scalping_pipeline_lifecycle():
    pipeline = TechnicalScalpingPipeline(config={"timeframes": ["M1", "M5"]})
    assert pipeline.metadata.id == "technical_scalping"
    assert pipeline.metadata.category == PluginCategory.ANALYSIS_PIPELINE
    assert pipeline.timeframes == ["M1", "M5"]

    container = ServiceContainer()
    event_bus = EventBus()
    await pipeline.on_register(container, event_bus)

    passed, warnings = await pipeline.on_preflight(container)
    assert passed is True

    mock_session = AsyncMock()
    proposals = await pipeline.execute_analysis_cycle(mock_session, ["BTCUSD"])
    assert isinstance(proposals, list)

    telemetry = pipeline.get_pipeline_telemetry()
    assert telemetry["pipeline"] == "technical_scalping"
    assert telemetry["assets_evaluated"] == 1


@pytest.mark.asyncio
async def test_swappable_analysis_pipeline_in_engine():
    container = ServiceContainer()
    event_bus = EventBus()
    engine = PluginEngine(container=container, event_bus=event_bus)

    p1 = MacroToAssetPipeline()
    p2 = TechnicalScalpingPipeline()

    engine.register_plugin_instance(p1)
    engine.register_plugin_instance(p2)

    # Configure technical_scalping as the active pipeline
    settings = {
        "plugins": {
            "enabled": True,
            "directories": [],
            "analysis_pipeline": {
                "active": "technical_scalping",
                "options": {
                    "technical_scalping": {
                        "timeframes": ["M15"]
                    }
                }
            }
        }
    }

    ok = await engine.initialize(settings)
    assert ok is True

    active_pipelines = engine.get_plugins_by_category(PluginCategory.ANALYSIS_PIPELINE)
    assert len(active_pipelines) == 1
    assert active_pipelines[0].metadata.id == "technical_scalping"
    assert p1.is_enabled is False
    assert p2.is_enabled is True
    assert p2.config.get("timeframes") == ["M15"]
