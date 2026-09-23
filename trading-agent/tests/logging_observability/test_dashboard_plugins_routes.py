# ==============================================================================
# File: tests/logging_observability/test_dashboard_plugins_routes.py
# Description: Unit tests for Plugin Marketplace & Lifecycle API endpoints
# ==============================================================================

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from logging_observability.dashboard.api import app

client = TestClient(app)


def test_get_plugins_endpoint():
    resp = client.get("/api/plugins")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "plugins" in data
    assert isinstance(data["plugins"], list)
    assert len(data["plugins"]) > 0


def test_get_plugin_catalog_endpoint():
    resp = client.get("/api/plugins/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "catalog" in data
    assert len(data["catalog"]) >= 3
    assert data["catalog"][0]["package"].startswith("monika-plugin-")


def test_toggle_plugin_endpoint():
    with patch("logging_observability.dashboard.routes.plugins.toggle_plugin_state") as mock_toggle:
        mock_toggle.return_value = (True, "Plugin toggled successfully.")

        payload = {
            "plugin_id": "technical_scalping",
            "category": "analysis_pipeline",
            "enabled": True,
        }
        resp = client.post("/api/plugins/toggle", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["plugin_id"] == "technical_scalping"
        assert data["enabled"] is True


def test_install_plugin_validation_rejection():
    # Attempt command injection
    payload = {"package_name": "malicious; rm -rf /"}
    resp = client.post("/api/plugins/install", json=payload)
    assert resp.status_code == 400


def test_install_plugin_mock_success():
    with patch("logging_observability.dashboard.routes.plugins.run_pip_install") as mock_pip:
        mock_pip.return_value = (True, "Successfully installed monika-plugin-test-1.0.0")

        payload = {"package_name": "monika-plugin-test"}
        resp = client.post("/api/plugins/install", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["package_name"] == "monika-plugin-test"
        assert "Successfully installed" in data["output"]
