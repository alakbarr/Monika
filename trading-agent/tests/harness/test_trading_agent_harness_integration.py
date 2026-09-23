# ==============================================================================
# File: tests/harness/test_trading_agent_harness_integration.py
# ==============================================================================

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from main import TradingAgent
from config.settings import load_settings


@pytest.mark.asyncio
async def test_trading_agent_plugin_engine_wiring():
    settings = load_settings()
    # Mock MT5Client, TelegramBot, DB to avoid connecting to live services during unit test
    with patch("execution.mt5_client.MT5Client") as mock_mt5, \
         patch("telegram_bot.bot.TelegramBot") as mock_tg, \
         patch("execution.execution_service.ExecutionService") as mock_exec:
        
        mock_mt5.return_value = MagicMock()
        mock_tg.return_value = MagicMock()
        mock_exec.return_value = MagicMock()

        agent = TradingAgent(settings=settings, dry_run=True)
        assert agent.plugin_engine is None

        agent._init_components()
        assert agent.plugin_engine is not None
        assert agent.container is not None

        # Verify that all 7 plugins across categories were discovered
        registry = agent.plugin_engine.registry
        expected_plugins = [
            "discord_alert_plugin",
            "macro_to_asset",
            "technical_scalping",
            "mt5_local",
            "paper_trading",
            "custom_indicator_plugin",
            "example_scraper_plugin",
        ]
        for pid in expected_plugins:
            assert pid in registry, f"Plugin {pid} not discovered by PluginEngine"

        if agent.risk_parameter_reloader:
            assert agent.plugin_engine in agent.risk_parameter_reloader.subscribers

        # Test plugin initialization
        plugins_cfg = settings.get("plugins", {})
        init_ok = await agent.plugin_engine.initialize(plugins_cfg)
        assert init_ok is True

        # Stop plugins cleanly
        await agent.plugin_engine.stop()
