# ==============================================================================
# File: tests/logging_observability/test_intelligence_routes.py
# Description: Unit tests for Intelligence & Discovery API Endpoints
# ==============================================================================

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from logging_observability.dashboard.api import app
from logging_observability.dashboard.routes.intelligence import intelligence_router


@pytest.fixture
def client():
    return TestClient(app)


def test_intelligence_router_routes_registered():
    """Verify all intelligence endpoints exist in the router."""
    routes = [r.path for r in intelligence_router.routes]
    assert "/api/calendar/events" in routes
    assert "/api/calendar/upcoming" in routes
    assert "/api/market/cot" in routes
    assert "/api/news/classified" in routes
    assert "/api/news/sentiment" in routes
    assert "/api/skills" in routes
    assert "/api/plugins" in routes
    assert "/api/reports/tearsheet/latest" in routes
    assert "/api/market/fedwatch" in routes
    assert "/api/market/yields" in routes
    assert "/api/market/fear-greed" in routes
    assert "/api/market/sentiment-composite" in routes


def test_get_calendar_events_mocked(client):
    """Test calendar events endpoint returns expected list structure."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/calendar/events?days_ahead=7")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


def test_get_upcoming_calendar_mocked(client):
    """Test upcoming calendar events endpoint."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/calendar/upcoming?hours_ahead=24")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


def test_get_cot_data_mocked(client):
    """Test COT data endpoint."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/market/cot?symbol=EURUSD")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


def test_get_classified_news_mocked(client):
    """Test classified news endpoint."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/news/classified?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


def test_get_news_sentiment_mocked(client):
    """Test news sentiment breakdown."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/news/sentiment?hours=24")
        assert response.status_code == 200
        data = response.json()
        assert "total_articles" in data
        assert "currencies" in data


def test_get_skills_endpoint(client):
    """Test /api/skills endpoint."""
    response = client.get("/api/skills")
    assert response.status_code == 200
    data = response.json()
    assert "skills" in data
    assert "total" in data
    assert isinstance(data["skills"], list)


def test_get_plugins_endpoint(client):
    """Test /api/plugins endpoint."""
    response = client.get("/api/plugins")
    assert response.status_code == 200
    data = response.json()
    assert "plugins" in data
    assert "total" in data
    assert isinstance(data["plugins"], list)


def test_get_latest_tearsheet_mocked(client):
    """Test /api/reports/tearsheet/latest endpoint when no outcomes exist."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/reports/tearsheet/latest")
        assert response.status_code == 200
        data = response.json()
        assert "total_trades" in data
        assert data["total_trades"] == 0
        assert data["initial_equity"] == 10000.0


def test_get_market_fedwatch_mocked(client):
    """Test /api/market/fedwatch endpoint."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/market/fedwatch")
        assert response.status_code == 200
        data = response.json()
        assert "fedwatch" in data
        assert "central_banks" in data
        assert isinstance(data["fedwatch"], list)
        assert isinstance(data["central_banks"], list)


def test_get_market_yields_mocked(client):
    """Test /api/market/yields endpoint."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/market/yields")
        assert response.status_code == 200
        data = response.json()
        assert "treasury_yields" in data
        assert "spread_2s10s" in data
        assert "is_inverted" in data
        assert "global_bonds" in data
        assert isinstance(data["treasury_yields"], list)


def test_get_market_fear_greed_mocked(client):
    """Test /api/market/fear-greed fallback default."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/market/fear-greed")
        assert response.status_code == 200
        data = response.json()
        assert "current_value" in data
        assert data["current_value"] == 50
        assert data["classification"] == "Neutral"


def test_get_market_sentiment_composite_mocked(client):
    """Test /api/market/sentiment-composite endpoint."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/market/sentiment-composite")
        assert response.status_code == 200
        data = response.json()
        assert "crypto" in data
        assert "forex_myfxbook" in data
        assert "forex_fxssi" in data
        assert "institutional_cot" in data
        assert "timestamp" in data


def test_get_crystallized_skills_endpoint(client):
    """Test /api/skills/crystallized endpoint."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/skills/crystallized")
        assert response.status_code == 200
        data = response.json()
        assert "skills" in data
        assert "total" in data
        assert isinstance(data["skills"], list)


def test_get_skill_stats_endpoint(client):
    """Test /api/skills/{name}/stats endpoint."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        response = client.get("/api/skills/eurusd_trend/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["skill_name"] == "eurusd_trend"
        assert data["status"] == "active"
        assert "win_rate" in data


def test_curate_skills_endpoint(client):
    """Test POST /api/skills/curate endpoint."""
    mock_session = AsyncMock()
    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        with patch("analysis.memory.skill_crystallizer.SkillCrystallizer.curate_and_prune_skills", new_callable=AsyncMock, return_value=[]):
            response = client.post("/api/skills/curate")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "curated"
            assert data["pruned_count"] == 0


def test_deprecate_skill_endpoint(client):
    """Test POST /api/skills/{name}/deprecate endpoint."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        with patch("analysis.memory.skill_crystallizer.SkillCrystallizer.deprecate_skill", return_value=True):
            response = client.post("/api/skills/test_skill/deprecate", json={"reason": "Test deprecation"})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "deprecated"
            assert data["skill_name"] == "test_skill"


def test_crystallize_skills_now_endpoint(client):
    """Test POST /api/skills/crystallize endpoint."""
    mock_session = AsyncMock()
    with patch("logging_observability.dashboard.routes.intelligence.AsyncSessionLocal") as mock_asl:
        mock_asl.return_value.__aenter__.return_value = mock_session
        with patch("analysis.memory.skill_crystallizer.SkillCrystallizer.evaluate_and_crystallize", new_callable=AsyncMock, return_value=[{"name": "test_cryst"}]):
            response = client.post("/api/skills/crystallize", json={"symbol": "EURUSD"})
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "crystallized"
            assert data["count"] == 1


