# ==============================================================================
# File: tests/logging_observability/test_dashboard_phase2.py
# ==============================================================================

"""
Unit tests for Phase 2: RBAC Middleware, Config Editor, Sessions, and Agent Chat.
"""

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from logging_observability.dashboard.api import (
    app,
    set_dashboard_dependencies,
    _dependencies,
)
from logging_observability.dashboard.rbac import Role, resolve_role, ROLE_HIERARCHY


@pytest.fixture
def client():
    _dependencies.clear()
    return TestClient(app)


# ---------------------------------------------------------------------------
# Subphase 2A: RBAC Unit Tests
# ---------------------------------------------------------------------------

def test_resolve_role_multi_keys():
    """Verify resolve_role parses DASHBOARD_API_KEYS correctly."""
    env = {
        "DASHBOARD_API_KEYS": "admin:adm_key_123,operator:ops_key_456,viewer:view_key_789",
        "DASHBOARD_API_KEY": "",
    }
    with patch.dict(os.environ, env):
        assert resolve_role("adm_key_123") == Role.ADMIN
        assert resolve_role("ops_key_456") == Role.OPERATOR
        assert resolve_role("view_key_789") == Role.VIEWER

        with pytest.raises(PermissionError):
            resolve_role("wrong_key")


def test_resolve_role_single_key_backward_compat():
    """Verify singular DASHBOARD_API_KEY maps to Role.ADMIN."""
    env = {
        "DASHBOARD_API_KEYS": "",
        "DASHBOARD_API_KEY": "legacy_admin_key",
    }
    with patch.dict(os.environ, env):
        assert resolve_role("legacy_admin_key") == Role.ADMIN
        with pytest.raises(PermissionError):
            resolve_role("bad_key")


def test_resolve_role_localhost_fallback():
    """Verify unconfigured localhost dev access defaults to Role.ADMIN."""
    env = {
        "DASHBOARD_API_KEYS": "",
        "DASHBOARD_API_KEY": "",
    }
    with patch.dict(os.environ, env):
        assert resolve_role("", is_localhost=True) == Role.ADMIN
        with pytest.raises(PermissionError):
            resolve_role("", is_localhost=False)


def test_rbac_endpoint_enforcement(client):
    """Verify endpoints enforce minimum role levels (viewer < operator < admin)."""
    env = {
        "DASHBOARD_API_KEYS": "admin:adm_key,operator:ops_key,viewer:view_key",
        "DASHBOARD_API_KEY": "",
    }
    with patch.dict(os.environ, env):
        # 1. Viewer trying operator action (trigger-cycle) -> 403
        res = client.post(
            "/api/actions/trigger-cycle",
            headers={"X-API-Key": "view_key"},
            json={"forced": True}
        )
        assert res.status_code == 403
        assert "operator" in res.json()["detail"].lower()

        # 2. Operator trying operator action (trigger-cycle) -> allowed through RBAC (503 if sched uninit)
        res = client.post(
            "/api/actions/trigger-cycle",
            headers={"X-API-Key": "ops_key"},
            json={"forced": True}
        )
        assert res.status_code != 403

        # 3. Operator trying admin action (override-risk) -> 403
        res = client.post(
            "/api/actions/override-risk",
            headers={"X-API-Key": "ops_key"},
            json={"risk_percent_per_trade": 1.5}
        )
        assert res.status_code == 403
        assert "admin" in res.json()["detail"].lower()

        # 4. Admin trying admin action -> allowed through RBAC
        with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session.add = MagicMock()
            mock_res = MagicMock()
            mock_res.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_res)
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            res = client.post(
                "/api/actions/override-risk",
                headers={"X-API-Key": "adm_key"},
                json={"risk_percent_per_trade": 1.5}
            )
            assert res.status_code == 200
            assert res.json()["status"] == "success"


# ---------------------------------------------------------------------------
# Subphase 2B: Config Management Tests
# ---------------------------------------------------------------------------

def test_get_config_settings(client):
    """Verify GET /api/config/settings returns valid settings dictionary and raw YAML."""
    res = client.get("/api/config/settings")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "settings" in data
    assert isinstance(data["settings"], dict)
    assert "file_path" in data


def test_get_config_schema(client):
    """Verify GET /api/config/schema returns JSON schema for TradingAgentConfig."""
    res = client.get("/api/config/schema")
    assert res.status_code == 200
    data = res.json()
    assert "properties" in data
    assert "trading" in data["properties"] or "risk" in data["properties"]


def test_put_config_settings_validation_failure(client):
    """Verify PUT /api/config/settings rejects invalid configuration with 422."""
    env = {"DASHBOARD_API_KEYS": "admin:adm_key", "DASHBOARD_API_KEY": ""}
    with patch.dict(os.environ, env):
        # Provide invalid risk: max_daily_drawdown_percent must be <= 15.0
        invalid_payload = {
            "settings": {
                "trading": {
                    "risk": {
                        "max_daily_drawdown_percent": 99.0  # violates le=15.0
                    }
                }
            },
            "reason": "Test invalid config"
        }
        res = client.put(
            "/api/config/settings",
            headers={"X-API-Key": "adm_key"},
            json=invalid_payload
        )
        assert res.status_code == 422
        assert res.json()["status"] == "validation_error"


def test_put_config_settings_success(client, tmp_path):
    """Verify PUT /api/config/settings saves config, creates .bak, and hot-reloads."""
    dummy_yaml = tmp_path / "settings.yaml"
    dummy_yaml.write_text("trading:\n  risk:\n    max_daily_drawdown_percent: 3.0\n", encoding="utf-8")

    mock_reloader = MagicMock()
    mock_reloader.check_and_reload.return_value = True
    set_dashboard_dependencies(risk_parameter_reloader=mock_reloader)

    valid_payload = {
        "settings": {
            "trading": {
                "risk": {
                    "max_daily_drawdown_percent": 4.0,
                    "max_weekly_drawdown_percent": 8.0,
                    "max_concurrent_positions": 5
                }
            }
        },
        "reason": "Adjust drawdown limits"
    }

    with patch("logging_observability.dashboard.api._get_settings_path", return_value=str(dummy_yaml)):
        with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_session.add = MagicMock()
            mock_session_ctx.return_value.__aenter__.return_value = mock_session

            res = client.put("/api/config/settings", json=valid_payload)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
            assert data["reloaded"] is True
            assert os.path.exists(str(dummy_yaml) + ".bak")


def test_put_config_settings_role_forbidden(client):
    """Verify operator or viewer cannot edit configuration (Admin required)."""
    env = {"DASHBOARD_API_KEYS": "admin:adm_key,operator:ops_key,viewer:view_key"}
    with patch.dict(os.environ, env):
        res = client.put(
            "/api/config/settings",
            headers={"X-API-Key": "ops_key"},
            json={"settings": {}}
        )
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# Subphase 2D: Sessions & Transcript Tests
# ---------------------------------------------------------------------------

def test_list_sessions(client):
    """Verify GET /api/sessions queries and formats sessions properly."""
    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        row = MagicMock()
        row.telegram_user_id = "dash:operator"
        row.message_count = 5
        row.last_active = None
        row.first_active = None

        mock_res1 = MagicMock()
        mock_res1.all.return_value = [row]

        mock_res2 = MagicMock()
        mock_res2.first.return_value = MagicMock(message="Hello agent", role="user")

        mock_session.execute.side_effect = [mock_res1, mock_res2]

        res = client.get("/api/sessions")
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 1
        assert items[0]["session_id"] == "dash:operator"
        assert items[0]["source"] == "dashboard"
        assert items[0]["message_count"] == 5
        assert items[0]["last_message"] == "Hello agent"


def test_get_session_messages(client):
    """Verify GET /api/sessions/{session_id}/messages returns transcript."""
    with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        msg1 = MagicMock()
        msg1.id = 1
        msg1.telegram_user_id = "dash:admin"
        msg1.role = "user"
        msg1.message = "cek status"
        msg1.timestamp = None

        mock_res = MagicMock()
        mock_res.scalars.return_value.all.return_value = [msg1]
        mock_session.execute.return_value = mock_res

        res = client.get("/api/sessions/dash:admin/messages")
        assert res.status_code == 200
        msgs = res.json()
        assert len(msgs) == 1
        assert msgs[0]["message"] == "cek status"
        assert msgs[0]["role"] == "user"


def test_get_auth_role(client):
    """Verify GET /api/auth/role returns resolved caller role."""
    env = {"DASHBOARD_API_KEYS": "operator:ops_123"}
    with patch.dict(os.environ, env):
        res = client.get("/api/auth/role", headers={"X-API-Key": "ops_123"})
        assert res.status_code == 200
        assert res.json()["role"] == "operator"


# ---------------------------------------------------------------------------
# Subphase 2C: WebSocket Agent Chat Tests
# ---------------------------------------------------------------------------

def test_websocket_agent_chat_auth_and_messaging(client):
    """Verify /ws/agent-chat authentication and bidirectional interaction."""
    env = {"DASHBOARD_API_KEYS": "operator:ops_key", "DASHBOARD_API_KEY": ""}
    with patch.dict(os.environ, env):
        # 1. Invalid key -> 1008
        import starlette.websockets
        with pytest.raises(starlette.websockets.WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws/agent-chat?token=bad_key"):
                pass
        assert exc.value.code == 1008

        # 2. Valid key -> receives connection_established and handles ping
        with client.websocket_connect("/ws/agent-chat?token=ops_key") as ws:
            init_msg = ws.receive_json()
            assert init_msg["type"] == "connection_established"
            assert init_msg["role"] == "operator"

            # Ping/pong
            ws.send_text("ping")
            assert ws.receive_text() == "pong"


def test_websocket_handshake_authentication(client):
    """Verify WebSocket endpoints accept authentication via initial handshake message (H-13)."""
    env = {"DASHBOARD_API_KEYS": "operator:ops_key", "DASHBOARD_API_KEY": ""}
    with patch.dict(os.environ, env):
        # /ws/live-feed handshake auth
        with client.websocket_connect("/ws/live-feed") as ws:
            # Client connects without token, and sends handshake message
            ws.send_json({"type": "authenticate", "token": "ops_key"})
            init_msg = ws.receive_json()
            assert init_msg["type"] == "connection_established"
            assert init_msg["status"] == "connected"

        # /ws/agent-chat handshake auth
        with client.websocket_connect("/ws/agent-chat") as ws:
            ws.send_json({"type": "authenticate", "token": "ops_key"})
            init_msg = ws.receive_json()
            assert init_msg["type"] == "connection_established"
            assert init_msg["role"] == "operator"


def test_websocket_agent_chat_rbac_enforcement(client):
    """Verify viewer cannot send messages to agent chat (requires Operator/Admin) (H-12)."""
    env = {"DASHBOARD_API_KEYS": "viewer:view_key,operator:ops_key", "DASHBOARD_API_KEY": ""}
    with patch.dict(os.environ, env):
        with client.websocket_connect("/ws/agent-chat?token=view_key") as ws:
            init_msg = ws.receive_json()
            assert init_msg["type"] == "connection_established"
            assert init_msg["role"] == "viewer"

            # Attempt to send message as viewer
            ws.send_json({"type": "message", "text": "hello agent"})
            err_msg = ws.receive_json()
            assert err_msg["type"] == "error"
            assert "Forbidden" in err_msg["message"]


def test_override_risk_validation_bounds(client):
    """Verify OverrideRiskRequest enforces ge/le bounds on risk parameters (H-15)."""
    env = {"DASHBOARD_API_KEYS": "operator:ops_key", "DASHBOARD_API_KEY": ""}
    with patch.dict(os.environ, env):
        # 1. Out of bounds high risk_percent_per_trade (> 5.0)
        res = client.post(
            "/api/actions/override-risk",
            headers={"X-API-Key": "ops_key"},
            json={"risk_percent_per_trade": 10.0}
        )
        assert res.status_code == 422

        # 2. Out of bounds low risk_percent_per_trade (< 0.1)
        res = client.post(
            "/api/actions/override-risk",
            headers={"X-API-Key": "ops_key"},
            json={"risk_percent_per_trade": 0.05}
        )
        assert res.status_code == 422

        # 3. Out of bounds high max_daily_drawdown_percent (> 20.0)
        res = client.post(
            "/api/actions/override-risk",
            headers={"X-API-Key": "ops_key"},
            json={"max_daily_drawdown_percent": 25.0}
        )
        assert res.status_code == 422

        # 4. Out of bounds low max_daily_drawdown_percent (< 0.5)
        res = client.post(
            "/api/actions/override-risk",
            headers={"X-API-Key": "ops_key"},
            json={"max_daily_drawdown_percent": 0.2}
        )
        assert res.status_code == 422

