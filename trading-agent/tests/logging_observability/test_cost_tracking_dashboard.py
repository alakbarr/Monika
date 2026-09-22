"""
Tests for PR-21: Per-Turn Cost Tracking Dashboard.
Verifies cycle-level cost accumulation, by_model, by_role breakdowns, and REST API endpoints.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from logging_observability.dashboard.api import app
from utils.analytics.token_auditor import TokenAuditor


@pytest.mark.asyncio
async def test_token_auditor_get_cycle_cost_breakdown():
    mock_session = AsyncMock()

    class DummyRow:
        def __init__(self, d):
            self._mapping = d

    sample_rows = [
        DummyRow({
            "cycle_id": "cycle-001",
            "model_name": "claude-3-5-sonnet",
            "role": "stage2_specialist",
            "turns": 3,
            "tokens": 4500,
            "cost_usd": 0.045,
            "avg_latency_ms": 1200.0,
        }),
        DummyRow({
            "cycle_id": "cycle-001",
            "model_name": "gemini-2.5-flash",
            "role": "fundamental_analyst",
            "turns": 2,
            "tokens": 2000,
            "cost_usd": 0.002,
            "avg_latency_ms": 400.0,
        }),
        DummyRow({
            "cycle_id": "cycle-002",
            "model_name": "gpt-4o-mini",
            "role": "signal_arbitrator",
            "turns": 1,
            "tokens": 800,
            "cost_usd": 0.0008,
            "avg_latency_ms": 300.0,
        }),
    ]

    mock_result = MagicMock()
    mock_result.all.return_value = sample_rows
    mock_session.execute = AsyncMock(return_value=mock_result)

    with patch("utils.analytics.token_auditor.get_session") as mock_get_session:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx

        res = await TokenAuditor.get_cycle_cost_breakdown(hours=24)

        assert res["total_cycles"] == 2
        assert res["total_turns"] == 6
        assert res["total_tokens"] == 7300
        assert res["total_cost_usd"] > 0
        assert res["avg_cost_per_turn_usd"] > 0

        # Verify cycle-001 details
        c1 = next(c for c in res["cycles"] if c["cycle_id"] == "cycle-001")
        assert c1["total_turns"] == 5
        assert "claude-3-5-sonnet" in c1["by_model"]
        assert "gemini-2.5-flash" in c1["by_model"]
        assert "stage2_specialist" in c1["by_role"]
        assert "fundamental_analyst" in c1["by_role"]


def test_dashboard_routes_tokens_cycles_endpoint():
    mock_data = {
        "time_window_hours": 24,
        "total_cycles": 1,
        "total_turns": 4,
        "total_tokens": 5000,
        "total_cost_usd": 0.025,
        "avg_cost_per_turn_usd": 0.00625,
        "cycles": [
            {
                "cycle_id": "cycle-abc",
                "total_cost_usd": 0.025,
                "total_turns": 4,
                "total_tokens": 5000,
                "by_model": {"gemini-2.5-flash": {"turns": 4, "tokens": 5000, "cost_usd": 0.025}},
                "by_role": {"market_recon": {"turns": 4, "tokens": 5000, "cost_usd": 0.025}},
            }
        ],
    }

    with patch.object(TokenAuditor, "get_cycle_cost_breakdown", new_callable=AsyncMock) as mock_breakdown:
        mock_breakdown.return_value = mock_data
        client = TestClient(app)
        resp = client.get("/api/v1/tokens/cycles?hours=12")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cycles"] == 1
        assert data["total_turns"] == 4
        assert len(data["cycles"]) == 1
        assert data["cycles"][0]["cycle_id"] == "cycle-abc"


def test_dashboard_routes_per_turn_cost_endpoint():
    mock_data = {
        "time_window_hours": 24,
        "total_cycles": 2,
        "total_turns": 10,
        "total_tokens": 12000,
        "total_cost_usd": 0.05,
        "avg_cost_per_turn_usd": 0.005,
        "cycles": [],
    }

    with patch.object(TokenAuditor, "get_cycle_cost_breakdown", new_callable=AsyncMock) as mock_breakdown:
        mock_breakdown.return_value = mock_data
        client = TestClient(app)
        resp = client.get("/api/v1/tokens/per-turn-cost?hours=24")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_turns"] == 10
        assert data["total_cost_usd"] == 0.05
        assert data["avg_cost_per_turn_usd"] == 0.005
        assert data["cycle_count"] == 2
