# ==============================================================================
# File: tests/config/test_modular_config.py
# ==============================================================================

import os
import yaml
import tempfile
import pytest
from unittest.mock import MagicMock
from config.settings import load_settings, _deep_merge
from config.migrations import CURRENT_CONFIG_VERSION, migrate_config, migrate_settings, DEFAULT_SUBSETS
from harness.contract import PluginCategory, PluginMetadata, TradingPlugin
from harness.engine import PluginEngine


def test_load_settings_scans_plugins_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        main_cfg = os.path.join(tmpdir, "settings.yaml")
        plugins_dir = os.path.join(tmpdir, "plugins")
        os.makedirs(plugins_dir, exist_ok=True)

        # Main settings
        with open(main_cfg, "w", encoding="utf-8") as f:
            yaml.safe_dump({"trading": {"risk": {"max_drawdown_pct": 5.0}}}, f)

        # Plugin 1: discord_alert.yaml
        with open(os.path.join(plugins_dir, "discord_alert.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump({"webhook_url": "https://discord.com/api/webhooks/123", "enabled": True}, f)

        # Plugin 2: custom_strategy.yaml
        with open(os.path.join(plugins_dir, "custom_strategy.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump({"param_a": 42, "symbols": ["EURUSD"]}, f)

        loaded = load_settings(path=main_cfg)
        assert "plugins" in loaded
        assert "discord_alert" in loaded["plugins"]
        assert loaded["plugins"]["discord_alert"]["webhook_url"] == "https://discord.com/api/webhooks/123"
        assert loaded["plugins"]["custom_strategy"]["param_a"] == 42


def test_unified_config_migrations():
    assert CURRENT_CONFIG_VERSION == 3
    assert DEFAULT_SUBSETS is not None

    raw = {"trading": {}}
    migrated, modified = migrate_config(raw)
    assert migrated["_config_version"] == 3

    settings_migrated, actions = migrate_settings({"trading": {}})
    assert "_config_version" in settings_migrated


@pytest.mark.asyncio
async def test_config_reload_propagates_to_plugin_engine():
    engine = PluginEngine()

    reloaded_called = False

    class SubscribingPlugin(TradingPlugin):
        metadata = PluginMetadata(
            id="sub_plugin_1",
            name="Subscribing Plugin",
            version="1.0.0",
            category=PluginCategory.MIDDLEWARE,
        )

        def on_config_reloaded(self, new_config: dict) -> None:
            nonlocal reloaded_called
            reloaded_called = True

    plugin = SubscribingPlugin()
    engine.register_plugin(plugin)

    await engine.propagate_config_reload({"trading": {"risk": {"max_drawdown_pct": 4.5}}})
    assert reloaded_called is True
