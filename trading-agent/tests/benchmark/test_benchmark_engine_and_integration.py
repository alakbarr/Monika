"""
Unit and Integration Tests for LLM Benchmark System Overhaul.
Tests fixture loading, System One deterministic scoring, Model Registry tiers/routers,
All 45 Task Specs creation (offline fixture fallback), and Dashboard REST Endpoints.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from logging_observability.dashboard.rbac import Role

from benchmark.fixture_loader import (
    load_fixture_json,
    get_synthetic_market_snapshot,
    get_synthetic_stage1_bundle,
    get_synthetic_stage2_bundle,
    get_synthetic_fundamental_brief,
    get_synthetic_news_items,
    get_synthetic_risk_context,
)
from benchmark.system_one_scorer import (
    score_system_one,
    _score_accuracy,
    _score_latency,
    _score_calibration,
    _score_schema,
)
from benchmark.model_registry import (
    get_candidate_models,
    get_tier_models,
    get_router_matrix,
    make_role_config,
    CANDIDATE_MODELS,
)
from benchmark.task_specs import TASKS, TaskSpec, BenchmarkCase
from logging_observability.dashboard.routes.benchmark import benchmark_router


# ==========================================
# 1. Fixture Loader Tests
# ==========================================

def test_fixture_loader_market_snapshot():
    # Load market snapshot
    snapshot = get_synthetic_market_snapshot()
    assert snapshot is not None
    assert "volatility" in snapshot
    assert snapshot["volatility"]["vix"] == 15.68
    assert "EURUSD" in snapshot["fx_prices"]
    assert snapshot["fx_prices"]["EURUSD"] == 1.1377
    assert snapshot["fx_prices"]["XAUUSD"] == 4260.00


def test_fixture_loader_smc_and_bundles():
    # Synthetic stage 1 bundle
    s1_bundle = get_synthetic_stage1_bundle()
    assert "GLOBAL MACROECONOMIC SNAPSHOT" in s1_bundle
    assert "EURUSD" in s1_bundle

    # Synthetic stage 2 bundle
    text_bundle, raw_dict = get_synthetic_stage2_bundle("EURUSD")
    assert "ASSET ANALYSIS BUNDLE: EURUSD" in text_bundle
    assert raw_dict["symbol"] == "EURUSD"
    assert "technical" in raw_dict

    # Synthetic news items
    news_items = get_synthetic_news_items()
    assert len(news_items) >= 2

    # S1 news fixture direct load
    s1_news = load_fixture_json("s1_news_breaking_iran.json")
    assert "questions" in s1_news
    assert len(s1_news["questions"]) >= 2
    assert s1_news["expected_answers"]["threatens_positions"] is True


def test_fixture_loader_fallback_on_unknown():
    fallback_data = load_fixture_json("non_existent_fixture_key_12345.json")
    assert fallback_data == {}


# ==========================================
# 2. System One Deterministic Scorer Tests
# ==========================================

def test_system_one_calibration_calculation():
    # Perfect high confidence matches True
    output_good = {"should_run": True, "confidence": 0.95}
    expected_good = {"should_run": True, "should_run_confidence_min": 0.8}
    score_good = _score_calibration(output_good, expected_good)
    assert score_good >= 9.0

    # Miscalibration
    output_bad = {"should_run": False, "confidence": 0.95}
    expected_bad = {"should_run": True, "should_run_confidence_min": 0.8}
    score_bad = _score_calibration(output_bad, expected_bad)
    assert score_bad < 2.0


def test_system_one_latency_scoring():
    # Ultra fast: <= 100ms (0.1s) -> score 10.0
    assert _score_latency(0.045, target_ms=100.0, ceiling_ms=1000.0) == 10.0
    assert _score_latency(0.100, target_ms=100.0, ceiling_ms=1000.0) == 10.0

    # Intermediate latency: 550ms (0.55s) -> score around 5.0
    score_mid = _score_latency(0.550, target_ms=100.0, ceiling_ms=1000.0)
    assert 4.5 <= score_mid <= 5.5

    # Above 1000ms SLA ceiling -> score 0.0
    assert _score_latency(1.200, target_ms=100.0, ceiling_ms=1000.0) == 0.0


def test_system_one_full_scoring_perfect():
    output = {"should_run": True, "confidence": 0.95, "bias": "BULLISH"}
    expected = {
        "should_run": True,
        "bias": "BULLISH",
        "should_run_confidence_min": 0.80,
    }
    
    score_result = score_system_one(
        output=output,
        expected=expected,
        latency_s=0.075,
        questions=[{"name": "should_run"}, {"name": "bias"}],
        target_latency_ms=100.0,
    )
    
    assert score_result["overall_score"] >= 9.0
    assert score_result["accuracy_score"] == 10.0
    assert score_result["latency_score"] == 10.0
    assert score_result["schema_score"] == 10.0
    assert score_result["latency_ms"] == 75.0


def test_system_one_full_scoring_mismatch():
    output = {"should_run": False, "confidence": 0.80, "bias": "BEARISH"}
    expected = {
        "should_run": True,
        "bias": "BULLISH",
    }
    
    score_result = score_system_one(
        output=output,
        expected=expected,
        latency_s=0.800,
        questions=[{"name": "should_run"}, {"name": "bias"}],
    )
    
    assert score_result["accuracy_score"] == 0.0
    assert score_result["latency_score"] < 3.0
    assert score_result["overall_score"] < 4.0


# ==========================================
# 3. Model Registry & Tiers Tests
# ==========================================

def test_model_registry_candidates_and_tiers():
    all_models = get_candidate_models()
    assert len(all_models) >= 10
    assert "jev-latest" in all_models
    assert "gemini-3.7-flash" in all_models
    assert "claude-haiku-4-5-20251001" in all_models

    # Mock settings with tiers
    mock_settings = {
        "benchmark": {
            "tiers": {
                "system_one": {"models": ["jev-latest", "jev-1.13"]},
                "cheap_efficient": {"models": ["gemini-3.5-flash-lite", "groq-compound-mini"]},
                "high_intelligence": {"models": ["claude-opus-5", "gemini-3.1-pro-preview"]}
            }
        }
    }

    s1_models = get_tier_models("system_one", settings=mock_settings)
    assert s1_models == ["jev-latest", "jev-1.13"]

    high_models = get_tier_models("high_intelligence", settings=mock_settings)
    assert "claude-opus-5" in high_models


def test_model_registry_router_matrix():
    matrix = get_router_matrix()
    assert isinstance(matrix, dict)
    assert "gemini-flash" in matrix
    assert any("openrouter" in r for r in matrix["gemini-flash"])
    assert any("9router" in r for r in matrix["gemini-flash"])


def test_make_role_config():
    cfg = make_role_config(max_tokens=4096, temperature=0.1)
    assert cfg["max_tokens"] == 4096
    assert cfg["temperature"] == 0.1
    assert "thinking" in cfg
    assert "openrouter" in cfg["thinking"]
    assert "9router" in cfg["thinking"]


# ==========================================
# 4. Task Specs: Full 45 Tasks Coverage Test
# ==========================================

@pytest.mark.asyncio
async def test_all_task_specs_and_fixture_cases():
    assert len(TASKS) >= 45, f"Expected at least 45 tasks, found {len(TASKS)}"

    settings = {"_use_fixtures": True, "trading": {"asset_universe": ["EURUSD"]}}

    # Test key categories
    # 1. System One tasks
    assert "jev_news_realtime" in TASKS
    assert "jev_trigger_validator" in TASKS
    assert "jev_position_guard" in TASKS
    assert "jev_exit_prescreen" in TASKS

    case_jev = await TASKS["jev_news_realtime"].build_case(session=None, settings=settings, ex=None)
    assert isinstance(case_jev, BenchmarkCase)
    assert case_jev.expected_answers is not None
    assert case_jev.questions is not None

    # 2. Stage 1 Macro task
    case_s1 = await TASKS["stage1_fundamental"].build_case(session=None, settings=settings, ex=None)
    assert isinstance(case_s1, BenchmarkCase)
    assert "PRE-FETCHED DATA" in case_s1.user_prompt
    assert "EURUSD" in case_s1.user_prompt

    # 3. Stage 2 Per Asset task
    case_s2 = await TASKS["stage2_per_asset_primary"].build_case(session=None, settings=settings, ex=None)
    assert isinstance(case_s2, BenchmarkCase)
    assert "EURUSD" in case_s2.user_prompt

    # 4. Debate tasks
    case_bull = await TASKS["debate_bull"].build_case(session=None, settings=settings, ex=None)
    assert isinstance(case_bull, BenchmarkCase)
    assert case_bull.custom_fn is not None

    # 5. Risk Gate tasks
    case_risk = await TASKS["risk_gate_conservative"].build_case(session=None, settings=settings, ex=None)
    assert isinstance(case_risk, BenchmarkCase)
    assert case_risk.custom_fn is not None


# ==========================================
# 5. Dashboard Routes REST API Tests
# ==========================================

@pytest.fixture
def test_client():
    app = FastAPI()

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        request.state.role = Role.ADMIN
        request.state.is_localhost = True
        return await call_next(request)

    app.include_router(benchmark_router)
    return TestClient(app)


def test_api_get_tasks(test_client):
    response = test_client.get("/api/benchmark/tasks")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    assert len(data["tasks"]) >= 45
    assert data["total"] >= 45


def test_api_get_models(test_client):
    response = test_client.get("/api/benchmark/models")
    assert response.status_code == 200
    data = response.json()
    assert "candidates" in data
    assert "tiers" in data
    assert len(data["candidates"]) >= 4
    assert "system_one" in data["tiers"]
    assert "cheap_efficient" in data["tiers"]


def test_api_get_runs_and_leaderboard_empty_or_mocked(test_client):
    # Test runs list
    response = test_client.get("/api/benchmark/runs")
    assert response.status_code == 200
    data = response.json()
    assert "runs" in data

    # Test leaderboard
    response_lb = test_client.get("/api/benchmark/leaderboard")
    assert response_lb.status_code == 200
    lb_data = response_lb.json()
    assert "leaderboard" in lb_data

