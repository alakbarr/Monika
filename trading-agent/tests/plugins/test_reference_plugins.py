"""
Unit tests verifying the 3 reference plugins (indicators, scrapers, alerts)
and their discovery, loading, and tool execution.
"""

from pathlib import Path
import pytest
from plugins.loader import PluginLoader
from utils.plugins.manager import PluginManager

from plugins.indicators.custom_indicator.custom_indicator import calculate_vwap_deviation
from plugins.scrapers.example_scraper.example_scraper import fetch_external_wire_feed
from plugins.alerts.discord_alert.discord_alert import dispatch_discord_alert


def test_discover_reference_plugins():
    plugins_dir = Path("trading-agent/plugins")
    loader = PluginLoader(manager=PluginManager())
    discovered = loader.discover_plugins(str(plugins_dir))

    names = {manifest.name for manifest, _ in discovered}
    assert "custom_indicator_plugin" in names
    assert "example_scraper_plugin" in names
    assert "discord_alert_plugin" in names


def test_load_reference_plugins():
    plugins_dir = Path("trading-agent/plugins")
    mgr = PluginManager()
    loader = PluginLoader(manager=mgr)
    loaded = loader.load_plugins_from_directory(str(plugins_dir))

    loaded_names = {m.name for m in loaded}
    assert "custom_indicator_plugin" in loaded_names
    assert "example_scraper_plugin" in loaded_names
    assert "discord_alert_plugin" in loaded_names


def test_custom_indicator_calculation():
    res = calculate_vwap_deviation({"symbol": "EURUSD", "current_price": 1.0850, "vwap_reference": 1.0820})
    assert res["status"] == "calculated"
    assert res["symbol"] == "EURUSD"
    assert res["deviation_pct"] > 0


def test_example_scraper_fetch():
    res = fetch_external_wire_feed({"topic": "central_bank"})
    assert res["status"] == "success"
    assert res["count"] == 1
    assert "External wire" in res["items"][0]["headline"]


def test_discord_alert_dispatch():
    res = dispatch_discord_alert({"channel": "live-trades", "message": "BUY EURUSD filled at 1.0850"})
    assert res["status"] == "dispatched"
    assert res["channel"] == "live-trades"
    assert "BUY EURUSD" in res["message_preview"]
