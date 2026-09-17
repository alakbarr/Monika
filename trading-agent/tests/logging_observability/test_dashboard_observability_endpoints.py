# ==============================================================================
# File: tests/logging_observability/test_dashboard_observability_endpoints.py
# ==============================================================================

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from logging_observability.dashboard.api import app
from logging_observability.tracing.exporters import global_trace_store

client = TestClient(app)


class TestObservabilityEndpoints:

    @patch("database.db.AsyncSessionLocal")
    def test_get_playbook_tree(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_res = MagicMock()
        rule = MagicMock()
        rule.id = 1
        rule.rule_hash = "abc123456789"
        rule.symbol = "XAUUSD"
        rule.rule_text = "Bullish breakout above 2500"
        rule.status = "active"
        rule.times_triggered = 10
        rule.wins_count = 7
        rule.losses_count = 3
        rule.win_rate = 70.0
        rule.total_pnl = 15.5
        rule.promoted_at = None
        mock_res.scalars.return_value.all.return_value = [rule]
        mock_session.execute = AsyncMock(return_value=mock_res)

        response = client.get("/api/observability/playbook-tree")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Trading Playbooks"
        assert "children" in data
        assert any(c["name"] == "XAUUSD" for c in data["children"])

    @patch("database.db.AsyncSessionLocal")
    def test_get_prompt_cache_metrics(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_res = MagicMock()
        log = MagicMock()
        log.cycle_id = "cycle-2026-09-07-001"
        log.cached_tokens = 4000
        log.input_tokens = 5000
        log.cache_creation_tokens = 1000
        log.output_tokens = 500
        log.timestamp = None
        mock_res.scalars.return_value.all.return_value = [log]
        mock_session.execute = AsyncMock(return_value=mock_res)

        response = client.get("/api/observability/prompt-cache-metrics?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "overall_hit_rate_pct" in data
        assert data["overall_hit_rate_pct"] == 80.0
        assert data["total_cached_tokens"] == 4000
        assert data["total_input_tokens"] == 5000
        assert len(data["cycles"]) >= 1
        assert data["cycles"][0]["hit_rate_pct"] == 80.0

    def test_get_tool_latencies(self):
        from logging_observability.tracing.exporters import TraceRecord
        rec = TraceRecord(
            trace_id="test-trace",
            span_id="test-span",
            parent_span_id=None,
            name="get_price_history",
            kind="tool",
            start_time="2026-09-07T12:00:00Z",
            end_time="2026-09-07T12:00:00.120Z",
            duration_ms=120.0,
            status="OK",
        )
        global_trace_store.record_span(rec)

        response = client.get("/api/observability/tool-latencies")
        assert response.status_code == 200
        data = response.json()
        assert "total_tool_calls" in data
        assert "tools" in data
        assert any(t["tool_name"] == "get_price_history" for t in data["tools"])
        tool = next(t for t in data["tools"] if t["tool_name"] == "get_price_history")
        assert tool["buckets"]["50-200ms"] >= 1
