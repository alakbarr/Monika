"""
Unit tests for Harness API routes in dashboard interfaces.
"""

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from monika.interfaces.dashboard.api import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DASHBOARD_API_KEYS", "admin:test_adm_key")
    return TestClient(app, headers={"X-API-Key": "test_adm_key"})


def test_harness_tree_endpoint(client):
    response = client.get("/api/v1/harness/tree")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "surface_name" in data
    assert data["total_components"] >= 4
    assert data["always_on_chars"] > 0
    assert data["always_on_chars"] <= data["always_on_max_chars"]
    assert isinstance(data["components"], list)


def test_harness_library_endpoint(client, tmp_path):
    with patch(
        "monika.application.analysis.harness.library.get_data_dir",
        return_value=tmp_path,
    ):
        response = client.get("/api/v1/harness/library")
        assert response.status_code == 200
        data = response.json()
        assert "total_domains" in data
        assert isinstance(data["domains"], list)


def test_harness_cycle_endpoint(client, tmp_path):
    with patch(
        "monika.application.analysis.harness.library.get_data_dir",
        return_value=tmp_path,
    ):
        response = client.post(
            "/api/v1/harness/cycle",
            json={"domain": "EURUSD_TREND", "k_candidates": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["domain"] == "EURUSD_TREND"
        assert "chosen_candidate" in data
        assert "composite_score" in data
