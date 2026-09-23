# ==============================================================================
# File: tests/logging_observability/test_dashboard_memory_routes.py
# Description: Unit tests for dashboard memory browsing endpoints
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from logging_observability.dashboard.api import app

client = TestClient(app)


class TestDashboardMemoryRoutes:

    @patch("logging_observability.dashboard.routes.memory.AsyncSessionLocal")
    def test_get_reflections(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_reflection = MagicMock()
        mock_reflection.id = 1
        mock_reflection.symbol = "XAUUSD"
        mock_reflection.decision = "buy"
        mock_reflection.confidence = 0.85
        mock_reflection.confluence_score = 7
        mock_reflection.rationale_summary = "Bullish momentum on 4H"
        mock_reflection.outcome_pnl_usd = 150.50
        mock_reflection.holding_hours = 4.2
        mock_reflection.exit_reason = "take_profit"
        mock_reflection.was_profitable = True
        mock_reflection.reflection_text = "Good entry timing"
        mock_reflection.next_trade_adjustment = "Trail stop earlier"
        mock_reflection.specific_lesson = "Hold winners during London open"
        mock_reflection.lesson_tags = '["momentum", "london"]'
        mock_reflection.alpha_return = 0.015
        mock_reflection.process_was_sound = True
        mock_reflection.outcome_process_classification = "good_process_good_outcome"
        mock_reflection.macro_thesis_correct = True
        mock_reflection.debate_verdict = "confirmed"
        mock_reflection.debate_summary = "Debate agreed on bullish trend"
        mock_reflection.is_paper_whatif = False
        mock_reflection.whatif_reason = None

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [mock_reflection]
        mock_session.execute = AsyncMock(return_value=mock_res)

        res = client.get("/api/memory/reflections?symbol=XAUUSD&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["symbol"] == "XAUUSD"
        assert data[0]["was_profitable"] is True
        assert data[0]["outcome_pnl_usd"] == 150.50

    @patch("logging_observability.dashboard.routes.memory.AsyncSessionLocal")
    def test_get_lessons(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_lesson = MagicMock()
        mock_lesson.id = 101
        mock_lesson.symbol = "EURUSD"
        mock_lesson.lesson_text = "Never enter right before US CPI"
        mock_lesson.status = "shadow"
        mock_lesson.proposed_at = None
        mock_lesson.evaluated_trades_count = 5
        mock_lesson.win_rate_delta = 0.05
        mock_lesson.sharpe_delta = 0.2
        mock_lesson.promoted_at = None
        mock_lesson.rejection_reason = None
        mock_lesson.condition_tags = "cpi,high_impact_news"

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [mock_lesson]
        mock_session.execute = AsyncMock(return_value=mock_res)

        res = client.get("/api/memory/lessons?status=shadow")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["symbol"] == "EURUSD"
        assert data[0]["status"] == "shadow"
        assert "CPI" in data[0]["lesson_text"]

    @patch("logging_observability.dashboard.routes.memory.AsyncSessionLocal")
    def test_get_playbooks(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_pb = MagicMock()
        mock_pb.id = 202
        mock_pb.rule_hash = "abc123hash"

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [mock_pb]
        mock_session.execute = AsyncMock(return_value=mock_res)

        res = client.get("/api/memory/playbooks")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["rule_hash"] == "abc123hash"

    @patch("logging_observability.dashboard.routes.memory.AsyncSessionLocal")
    def test_search_memory(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        # Mock reflections response
        mock_r = MagicMock()
        mock_r.id = 1
        mock_r.symbol = "GBPUSD"
        mock_r.decision = "sell"
        mock_r.outcome_pnl_usd = -50.0
        mock_r.reflection_text = "Loss due to BOE rate spike"
        mock_r.specific_lesson = "Beware BOE rate surprise"
        mock_r.next_trade_adjustment = "Wait 30m post announcement"
        mock_r.was_profitable = False

        mock_res_r = MagicMock()
        mock_res_r.scalars.return_value.all.return_value = [mock_r]

        # Mock lessons response
        mock_l = MagicMock()
        mock_l.id = 2
        mock_l.symbol = "GBPUSD"
        mock_l.lesson_text = "BOE spike rule: abstain"
        mock_l.status = "promoted"
        mock_l.win_rate_delta = 0.08

        mock_res_l = MagicMock()
        mock_res_l.scalars.return_value.all.return_value = [mock_l]

        mock_session.execute = AsyncMock(side_effect=[mock_res_r, mock_res_l])

        payload = {"query": "BOE", "limit": 10}
        res = client.post("/api/memory/search", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["query"] == "BOE"
        assert data["total_matches"] == 2
        assert len(data["reflections"]) == 1
        assert len(data["lessons"]) == 1
