import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from logging_observability.dashboard.api import app, _safe_json, set_dashboard_dependencies, _dependencies
from logging_observability.dashboard.rbac import Role, resolve_role
import datetime

client = TestClient(app)

class TestDashboardAPI:

    @patch("database.db.engine")
    def test_get_health(self, mock_engine):
        mock_conn = AsyncMock()
        mock_engine.connect.return_value.__aenter__.return_value = mock_conn
        
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = datetime.datetime.now()
        mock_conn.execute = AsyncMock(return_value=mock_res)
        
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "ok"

    @patch("database.db.AsyncSessionLocal")
    def test_get_overview(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        response = client.get("/api/overview")
        assert response.status_code == 200
        data = response.json()
        assert "agent_status" in data

    @patch("database.db.AsyncSessionLocal")
    def test_get_positions(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        mock_res = MagicMock()
        pos = MagicMock()
        pos.id = 1
        pos.mt5_ticket = 123
        pos.symbol = "XAUUSD"
        pos.direction = "buy"
        pos.volume = 0.1
        pos.entry_price = 2000.0
        pos.sl = 1990.0
        pos.tp = 2020.0
        pos.opened_at = datetime.datetime.now()
        pos.closed_at = None
        pos.status = "open"
        pos.pnl = 50.0
        
        mock_res.scalars().all.return_value = [pos]
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        response = client.get("/api/positions")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "XAUUSD"

    @patch("database.db.AsyncSessionLocal")
    def test_get_activity(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        mock_res = MagicMock()
        act = MagicMock()
        act.id = 1
        act.timestamp = datetime.datetime.now()
        act.category = "trading"
        act.description = "Test"
        act.related_id = None
        act.actor = "system"
        
        mock_res.scalars().all.return_value = [act]
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        response = client.get("/api/activity")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["category"] == "trading"

    @patch("database.db.AsyncSessionLocal")
    def test_get_analysis(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        mock_res = MagicMock()
        a = MagicMock()
        a.id = 1
        a.symbol = "XAUUSD"
        a.decision = "buy"
        a.confidence = 0.9
        a.generated_at = datetime.datetime.now()
        a.stop_loss = 1990.0
        a.take_profit = 2020.0
        a.rationale = "Test"
        a.reevaluation_trigger = '{"detail": "Test"}'
        a.invalidation = "Test"
        
        mock_res.scalars().all.return_value = [a]
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        response = client.get("/api/analysis")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "XAUUSD"

    @patch("database.db.AsyncSessionLocal")
    def test_get_orders(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        mock_res = MagicMock()
        o = MagicMock()
        o.id = 1
        o.action = "place"
        o.symbol = "XAUUSD"
        o.params_json = '{"volume": 0.1}'
        o.requested_by = "claude"
        o.approved_by = "risk_gate"
        o.result = '{"ticket": 123}'
        o.timestamp = datetime.datetime.now()
        
        mock_res.scalars().all.return_value = [o]
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        response = client.get("/api/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["action"] == "place"

    @patch("database.db.AsyncSessionLocal")
    def test_get_risk(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        mock_res = MagicMock()
        r = MagicMock()
        r.date = datetime.datetime.now()
        r.daily_pnl = 100.0
        r.current_drawdown = 2.0
        r.trading_paused = False
        r.reason = None
        
        mock_res.scalar_one_or_none.return_value = r
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        response = client.get("/api/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["daily_pnl"] == 100.0

    @patch("database.db.AsyncSessionLocal")
    def test_get_risk_with_real_model(self, mock_session_local):
        from database.models import RiskState

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_res = MagicMock()
        real_risk = RiskState(
            date=datetime.datetime.now(datetime.timezone.utc),
            daily_pnl=50.0,
            current_drawdown=1.5,
            trading_paused=False,
            reason=None,
        )
        mock_res.scalar_one_or_none.return_value = real_risk
        mock_session.execute = AsyncMock(return_value=mock_res)

        response = client.get("/api/risk")
        assert response.status_code == 200
        data = response.json()
        assert data["daily_pnl"] == 50.0
        assert data["daily_pnl_pct"] == 0.0

        # Now test with dynamic starting_balance attached
        setattr(real_risk, "starting_balance", 1000.0)
        response2 = client.get("/api/risk")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["daily_pnl_pct"] == 5.0

    @patch("database.db.AsyncSessionLocal")
    def test_get_vix(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        mock_res = MagicMock()
        v = MagicMock()
        v.date = datetime.datetime.now()
        v.close = 15.0
        
        mock_res.scalars().all.return_value = [v]
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        response = client.get("/api/vix")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["close"] == 15.0

    @patch("database.db.AsyncSessionLocal")
    def test_get_brief(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session
        
        mock_res = MagicMock()
        b = MagicMock()
        b.id = 1
        b.generated_at = datetime.datetime.now()
        b.valid_until = datetime.datetime.now()
        b.content_markdown = "Test"
        b.structured_json = '{"key": "value"}'
        
        mock_res.scalar_one_or_none.return_value = b
        mock_session.execute = AsyncMock(return_value=mock_res)
        
        response = client.get("/api/brief")
        assert response.status_code == 200
        data = response.json()
        brief_data = data.get("brief", data)
        assert brief_data["structured"]["key"] == "value"

    def test_safe_json(self):
        assert _safe_json(None) is None
        assert _safe_json('{"a": 1}') == {"a": 1}
        assert _safe_json('invalid json') == 'invalid json'

    def test_websocket_auth(self):
        # 1. Without DASHBOARD_API_KEY (localhost allowed)
        with patch.dict("os.environ", {"DASHBOARD_API_KEY": ""}):
            with client.websocket_connect("/ws/live-feed") as ws:
                init_msg = ws.receive_json()
                assert init_msg["type"] == "connection_established"

        # 2. With DASHBOARD_API_KEY set
        with patch.dict("os.environ", {"DASHBOARD_API_KEY": "secret123"}):
            # Missing / invalid token -> connection closed with 1008
            import starlette.websockets
            with pytest.raises(starlette.websockets.WebSocketDisconnect) as exc:
                with client.websocket_connect("/ws/live-feed?token=wrong_key"):
                    pass
            assert exc.value.code == 1008

            # Valid token via query param -> connection accepted
            with client.websocket_connect("/ws/live-feed?token=secret123") as ws:
                init_msg = ws.receive_json()
                assert init_msg["type"] == "connection_established"

    def test_trace_endpoints(self):
        from logging_observability.tracing.exporters import global_trace_store, TraceRecord
        rec = TraceRecord(
            trace_id="test_trc_001",
            span_id="test_spn_001",
            parent_span_id=None,
            name="test_span",
            kind="cycle",
            start_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            attributes={"cycle_id": "test_cycle_001", "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.005},
        )
        global_trace_store.record_span(rec)

        # 1. GET /api/traces
        res = client.get("/api/traces")
        assert res.status_code == 200
        data = res.json()
        assert "spans" in data
        assert any(s["trace_id"] == "test_trc_001" for s in data["spans"])

        # 2. GET /api/traces/{trace_id}
        res_tree = client.get("/api/traces/test_trc_001")
        assert res_tree.status_code == 200
        tree_data = res_tree.json()
        assert tree_data["trace_id"] == "test_trc_001"
        assert len(tree_data["roots"]) >= 1

        # 3. GET /api/traces/cycle/{cycle_id}
        res_cycle = client.get("/api/traces/cycle/test_cycle_001")
        assert res_cycle.status_code == 200
        cycle_data = res_cycle.json()
        assert cycle_data["cycle_id"] == "test_cycle_001"
        assert len(cycle_data["spans"]) >= 1

    @patch("database.db.AsyncSessionLocal")
    def test_get_debate_outcomes(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_res = MagicMock()
        ana = MagicMock()
        ana.id = 42
        ana.symbol = "EURUSD"
        ana.decision = "buy"
        ana.confidence = 82.5
        ana.confluence_score = 4
        ana.risk_multiplier = 1.0
        ana.rationale = "Bullish structure and macroeconomic divergence"
        ana.specialist_biases_json = '{"macro": "bullish"}'
        ana.debate_bull_thesis = '{"thesis": "Strong labor market supports EUR"}'
        ana.debate_bear_dissent = '{"dissent": "ECB rate cuts may accelerate"}'
        ana.debate_verdict = "buy"
        ana.debate_reason = "Bullish conviction remains dominant"
        ana.generated_at = datetime.datetime.now(datetime.timezone.utc)
        ana.execution_status = "executed"

        mock_res.scalars().all.return_value = [ana]
        mock_session.execute = AsyncMock(return_value=mock_res)

        response = client.get("/api/debate-outcomes?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["symbol"] == "EURUSD"
        assert item["decision"] == "buy"
        assert item["debate_verdict"] == "buy"
        assert item["debate_bull_thesis"] == {"thesis": "Strong labor market supports EUR"}
        assert item["debate_bear_dissent"] == {"dissent": "ECB rate cuts may accelerate"}

    @patch("database.db.AsyncSessionLocal")
    def test_get_mt5_signals(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_res = MagicMock()
        sig = MagicMock()
        sig.id = 101
        sig.asset_analysis_id = 42
        sig.symbol = "GBPUSD"
        sig.action = "buy"
        sig.status = "executed"
        sig.mt5_ticket = 998877
        sig.created_at = datetime.datetime.now(datetime.timezone.utc)
        sig.executed_at = datetime.datetime.now(datetime.timezone.utc)
        sig.error_message = None

        mock_res.scalars().all.return_value = [sig]
        mock_session.execute = AsyncMock(return_value=mock_res)

        response = client.get("/api/signals/mt5?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["symbol"] == "GBPUSD"
        assert data["items"][0]["mt5_ticket"] == 998877

    @patch("database.db.AsyncSessionLocal")
    def test_get_trade_triggers(self, mock_session_local):
        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_session

        mock_res = MagicMock()
        trig = MagicMock()
        trig.id = 201
        trig.asset_analysis_id = 42
        trig.trigger_type = "price_level"
        trig.status = "pending"
        trig.condition_json = '{"level": 1.0850}'
        trig.created_at = datetime.datetime.now(datetime.timezone.utc)
        trig.fired_at = None

        mock_res.scalars().all.return_value = [trig]
        mock_session.execute = AsyncMock(return_value=mock_res)

        response = client.get("/api/triggers?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["condition"] == {"level": 1.0850}

    @patch("utils.analytics.token_auditor.TokenAuditor.get_summary")
    @patch("utils.analytics.token_auditor.TokenAuditor.get_role_breakdown")
    @patch("utils.analytics.token_auditor.TokenAuditor.get_subsystem_breakdown")
    @patch("utils.analytics.token_auditor.TokenAuditor.get_symbol_breakdown")
    @patch("utils.analytics.token_auditor.TokenAuditor.get_recent_logs")
    def test_get_tokens_endpoints(self, mock_logs, mock_syms, mock_subs, mock_roles, mock_sum):
        mock_sum.return_value = {"total_calls": 5, "total_cost_usd": 0.05}
        mock_roles.return_value = [{"task_role": "market_analyst", "sum_total": 1200}]
        mock_subs.return_value = [{"subsystem": "stage1", "sum_total": 1200}]
        mock_syms.return_value = [{"symbol": "EURUSD", "sum_cost_usd": 0.02}]
        mock_logs.return_value = [{"id": 1, "task_role": "market_analyst"}]

        res1 = client.get("/api/v1/tokens/summary?hours=24")
        assert res1.status_code == 200
        assert res1.json()["total_calls"] == 5

        res2 = client.get("/api/v1/tokens/roles?hours=24")
        assert res2.status_code == 200
        assert res2.json()["total_roles"] == 1

        res3 = client.get("/api/v1/tokens/subsystems?hours=24")
        assert res3.status_code == 200
        assert res3.json()["total_subsystems"] == 1

        res4 = client.get("/api/v1/tokens/symbols?hours=24")
        assert res4.status_code == 200
        assert res4.json()["total_symbols"] == 1

        res5 = client.get("/api/v1/tokens/recent?limit=10")
        assert res5.status_code == 200
        assert res5.json()["total"] == 1

    # -----------------------------------------------------------------------
    # Phase 2: RBAC Tests
    # -----------------------------------------------------------------------
    def test_resolve_role_multi_keys(self):
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

    def test_resolve_role_single_key_backward_compat(self):
        env = {
            "DASHBOARD_API_KEYS": "",
            "DASHBOARD_API_KEY": "legacy_admin_key",
        }
        with patch.dict(os.environ, env):
            assert resolve_role("legacy_admin_key") == Role.ADMIN
            with pytest.raises(PermissionError):
                resolve_role("bad_key")

    def test_resolve_role_localhost_fallback(self):
        env = {
            "DASHBOARD_API_KEYS": "",
            "DASHBOARD_API_KEY": "",
        }
        with patch.dict(os.environ, env):
            assert resolve_role("", is_localhost=True) == Role.ADMIN
            with pytest.raises(PermissionError):
                resolve_role("", is_localhost=False)

    def test_rbac_endpoint_enforcement(self):
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

            # 2. Operator trying operator action (trigger-cycle) -> allowed through RBAC
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

    # -----------------------------------------------------------------------
    # Phase 2: Config Management Tests
    # -----------------------------------------------------------------------
    def test_get_config_settings(self):
        res = client.get("/api/config/settings")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert "settings" in data
        assert isinstance(data["settings"], dict)
        assert "file_path" in data

    def test_get_config_schema(self):
        res = client.get("/api/config/schema")
        assert res.status_code == 200
        data = res.json()
        assert "properties" in data
        assert "trading" in data["properties"] or "risk" in data["properties"]

    def test_put_config_settings_validation_failure(self):
        env = {"DASHBOARD_API_KEYS": "admin:adm_key", "DASHBOARD_API_KEY": ""}
        with patch.dict(os.environ, env):
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

    def test_put_config_settings_success(self, tmp_path):
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

    def test_put_config_settings_role_forbidden(self):
        env = {"DASHBOARD_API_KEYS": "admin:adm_key,operator:ops_key,viewer:view_key"}
        with patch.dict(os.environ, env):
            res = client.put(
                "/api/config/settings",
                headers={"X-API-Key": "ops_key"},
                json={"settings": {}}
            )
            assert res.status_code == 403

    def test_spoofed_forwarded_for_cannot_bypass_rbac(self):
        """Verify that sending X-Forwarded-For: 127.0.0.1 does NOT grant localhost/admin privileges."""
        env = {"DASHBOARD_API_KEYS": "", "DASHBOARD_API_KEY": ""}
        with patch.dict(os.environ, env):
            # Remote client sending spoofed loopback header without API key
            res = client.get("/api/overview", headers={"X-Forwarded-For": "127.0.0.1"})
            assert res.status_code == 403
            assert "DASHBOARD_API_KEY must be configured for remote network access" in res.json().get("detail", "")


    # -----------------------------------------------------------------------
    # Phase 2: Sessions & Transcript Tests
    # -----------------------------------------------------------------------
    def test_list_sessions(self):
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

    def test_get_session_messages(self):
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

    def test_get_auth_role(self):
        env = {"DASHBOARD_API_KEYS": "operator:ops_123"}
        with patch.dict(os.environ, env):
            res = client.get("/api/auth/role", headers={"X-API-Key": "ops_123"})
            assert res.status_code == 200
            assert res.json()["role"] == "operator"

    # -----------------------------------------------------------------------
    # Phase 2: WebSocket Agent Chat Tests
    # -----------------------------------------------------------------------
    def test_websocket_agent_chat_auth_and_messaging(self):
        env = {"DASHBOARD_API_KEYS": "operator:ops_key", "DASHBOARD_API_KEY": ""}
        with patch.dict(os.environ, env):
            import starlette.websockets
            with pytest.raises(starlette.websockets.WebSocketDisconnect) as exc:
                with client.websocket_connect("/ws/agent-chat?token=bad_key"):
                    pass
            assert exc.value.code == 1008

            with client.websocket_connect("/ws/agent-chat?token=ops_key&session_id=dash:custom_session") as ws:
                init_msg = ws.receive_json()
                assert init_msg["type"] == "connection_established"
                assert init_msg["role"] == "operator"
                assert init_msg["session_id"] == "dash:custom_session"

                ws.send_text("ping")
                assert ws.receive_text() == "pong"

    # -----------------------------------------------------------------------
    # Edge Cases Tests
    # -----------------------------------------------------------------------
    def test_put_config_settings_preserves_unmanaged_sections(self, tmp_path):
        """Verify that updating one section (e.g. risk) preserves existing unmanaged sections."""
        dummy_yaml = tmp_path / "settings.yaml"
        dummy_yaml.write_text(
            "app_name: 'TradingAgent'\n"
            "custom_metadata:\n"
            "  cluster_id: 'prod-01'\n"
            "trading:\n"
            "  risk:\n"
            "    max_daily_drawdown_percent: 2.0\n",
            encoding="utf-8"
        )
        partial_payload = {
            "settings": {
                "trading": {
                    "risk": {
                        "max_daily_drawdown_percent": 3.5
                    }
                }
            },
            "reason": "Update risk limit only"
        }
        with patch("logging_observability.dashboard.api._get_settings_path", return_value=str(dummy_yaml)):
            with patch("database.db.AsyncSessionLocal") as mock_session_ctx:
                mock_session = AsyncMock()
                mock_session.add = MagicMock()
                mock_session_ctx.return_value.__aenter__.return_value = mock_session

                res = client.put("/api/config/settings", json=partial_payload)
                assert res.status_code == 200
                import yaml
                with open(dummy_yaml, "r", encoding="utf-8") as f:
                    saved_data = yaml.safe_load(f)
                # Verify custom_metadata and app_name was NOT wiped!
                assert saved_data.get("app_name") == "TradingAgent"
                assert saved_data.get("custom_metadata", {}).get("cluster_id") == "prod-01"
                assert saved_data["trading"]["risk"]["max_daily_drawdown_percent"] == 3.5

    def test_resolve_role_none_and_whitespace(self):
        """Verify resolve_role handles None, whitespace, and empty strings safely."""
        env = {
            "DASHBOARD_API_KEYS": "admin:adm_key",
            "DASHBOARD_API_KEY": "",
        }
        with patch.dict(os.environ, env):
            with pytest.raises(PermissionError):
                resolve_role(None)
            with pytest.raises(PermissionError):
                resolve_role("   ")
            with pytest.raises(PermissionError):
                resolve_role("")

    # -----------------------------------------------------------------------
    # Phase 5: LangGraph DAG Visualizer Graph State Tests
    # -----------------------------------------------------------------------
    def test_get_graph_state_default(self):
        """Test GET /api/observability/graph-state returns valid LangGraph topology."""
        res = client.get("/api/observability/graph-state")
        assert res.status_code == 200
        data = res.json()

        assert "cycle_id" in data
        assert "status" in data
        assert "nodes" in data
        assert "edges" in data
        assert "total_tokens" in data
        assert "available_cycles" in data

        node_ids = [n["id"] for n in data["nodes"]]
        assert "fundamental_brief" in node_ids
        assert "prefetch_data" in node_ids
        assert "bull_advocate" in node_ids
        assert "bear_dissent" in node_ids
        assert "debate_judge" in node_ids
        assert "risk_gate" in node_ids
        assert "execution" in node_ids

        # Verify edge connectivity
        edge_pairs = [(e["from"], e["to"]) for e in data["edges"]]
        assert ("fundamental_brief", "prefetch_data") in edge_pairs
        assert ("prefetch_data", "bull_advocate") in edge_pairs
        assert ("prefetch_data", "bear_dissent") in edge_pairs
        assert ("bull_advocate", "debate_judge") in edge_pairs
        assert ("bear_dissent", "debate_judge") in edge_pairs
        assert ("debate_judge", "risk_gate") in edge_pairs
        assert ("risk_gate", "execution") in edge_pairs

    def test_get_graph_state_with_cycle_id(self):
        """Test GET /api/observability/graph-state with specific cycle_id."""
        res = client.get("/api/observability/graph-state?cycle_id=cycle-custom-2026")
        assert res.status_code == 200
        data = res.json()
        assert data["cycle_id"] == "cycle-custom-2026"
        assert len(data["nodes"]) == 7

    def test_get_graph_state_with_real_spans(self):
        """Test that real spans in global_trace_store accurately reflect in graph state."""
        from logging_observability.tracing.exporters import global_trace_store, TraceRecord

        test_cycle = "cycle-test-live-100"
        # 1. Successful node span
        fund_span = TraceRecord(
            trace_id=test_cycle,
            span_id="span-fund-1",
            parent_span_id=None,
            name="node:fundamental_analysis",
            kind="node",
            start_time="2026-09-14T02:00:00Z",
            end_time="2026-09-14T02:00:04Z",
            duration_ms=4120.0,
            attributes={
                "cycle_id": test_cycle,
                "node_name": "fundamental_analysis",
                "input_tokens": 15000,
                "output_tokens": 2500,
                "cost_usd": 0.021,
                "output_payload": {"macro_bias": "STRONG_BULLISH", "dxy": "dumping"}
            },
            status="OK"
        )
        # 2. Failed node span
        risk_span = TraceRecord(
            trace_id=test_cycle,
            span_id="span-risk-1",
            parent_span_id=None,
            name="node:risk_gate",
            kind="node",
            start_time="2026-09-14T02:00:05Z",
            end_time="2026-09-14T02:00:06Z",
            duration_ms=500.0,
            attributes={"cycle_id": test_cycle, "node_name": "risk_gate"},
            status="ERROR",
            error="Drawdown limit breached: 3.2% > 3.0%"
        )
        # 3. Running node span (no end_time)
        exec_span = TraceRecord(
            trace_id=test_cycle,
            span_id="span-exec-1",
            parent_span_id=None,
            name="node:execution",
            kind="node",
            start_time="2026-09-14T02:00:07Z",
            end_time=None,
            duration_ms=0.0,
            attributes={"cycle_id": test_cycle, "node_name": "execution"},
            status="OK"
        )

        global_trace_store.record_span(fund_span)
        global_trace_store.record_span(risk_span)
        global_trace_store.record_span(exec_span)

        res = client.get(f"/api/observability/graph-state?cycle_id={test_cycle}")
        assert res.status_code == 200
        data = res.json()
        assert data["cycle_id"] == test_cycle

        nodes_by_id = {n["id"]: n for n in data["nodes"]}

        # Fundamental should be done with recorded metrics
        assert nodes_by_id["fundamental_brief"]["status"] == "done"
        assert nodes_by_id["fundamental_brief"]["duration_ms"] == 4120.0
        assert nodes_by_id["fundamental_brief"]["tokens"]["input"] == 15000
        assert nodes_by_id["fundamental_brief"]["output_payload"]["macro_bias"] == "STRONG_BULLISH"

        # Risk gate should be marked failed with error
        assert nodes_by_id["risk_gate"]["status"] == "failed"
        assert "Drawdown limit breached" in nodes_by_id["risk_gate"]["error"]

        # Execution should be marked running
        assert nodes_by_id["execution"]["status"] == "running"

        # Unexecuted nodes MUST be marked as pending with zero metrics and null payloads (not fake done)
        for pending_id in ["prefetch_data", "bull_advocate", "bear_dissent", "debate_judge"]:
            assert nodes_by_id[pending_id]["status"] == "pending", f"Expected {pending_id} to be pending"
            assert nodes_by_id[pending_id]["duration_ms"] == 0.0
            assert nodes_by_id[pending_id]["tokens"]["total"] == 0
            assert nodes_by_id[pending_id]["output_payload"] is None

        # Overall cycle status should be failed because a node failed
        assert data["status"] == "failed"

    def test_get_graph_state_non_existent_cycle_pending(self):
        """Test that querying a non-existent cycle returns pending nodes rather than fake executed trades."""
        res = client.get("/api/observability/graph-state?cycle_id=cycle-ghost-999")
        assert res.status_code == 200
        data = res.json()
        assert data["cycle_id"] == "cycle-ghost-999"
        assert data["status"] == "pending"
        for node in data["nodes"]:
            assert node["status"] == "pending"
            assert node["duration_ms"] == 0.0
            assert node["tokens"]["total"] == 0
            assert node["output_payload"] is None

    def test_get_graph_state_llm_span_disambiguation(self):
        """Test that LLM spans (e.g. llm:debate_bull) are not falsely captured as node spans."""
        from logging_observability.tracing.exporters import global_trace_store, TraceRecord

        test_cycle = "cycle-llm-disambig-test"
        # LLM span containing 'debate' in name
        llm_span = TraceRecord(
            trace_id=test_cycle,
            span_id="span-llm-debate-1",
            parent_span_id=None,
            name="llm:debate_bull",
            kind="llm",
            start_time="2026-09-14T02:10:00Z",
            end_time="2026-09-14T02:10:02Z",
            duration_ms=2000.0,
            attributes={"cycle_id": test_cycle, "input_tokens": 1200, "output_tokens": 300},
            status="OK"
        )
        global_trace_store.record_span(llm_span)

        res = client.get(f"/api/observability/graph-state?cycle_id={test_cycle}")
        assert res.status_code == 200
        data = res.json()
        nodes_by_id = {n["id"]: n for n in data["nodes"]}

        # debate_judge must NOT match llm:debate_bull; it must remain pending
        assert nodes_by_id["debate_judge"]["status"] == "pending"
        assert nodes_by_id["debate_judge"]["duration_ms"] == 0.0

    def test_get_cycle_trace_summary_enriched(self):
        """Test that GET /api/traces/cycle/{cycle_id} returns enriched graph_state."""
        res = client.get("/api/traces/cycle/cycle-summary-test")
        assert res.status_code == 200
        data = res.json()
        assert "cycle_id" in data
        assert "summary" in data
        assert "spans" in data
        assert "graph_state" in data
        assert len(data["graph_state"]["nodes"]) == 7

    def test_pagination_limits_bounded_validation(self):
        """Test that query parameters enforce ge=1 and le bounds."""
        # limit=0 should fail validation (ge=1)
        res_zero = client.get("/api/positions?limit=0")
        assert res_zero.status_code == 422

        # limit=500 should fail validation (le=200)
        res_over = client.get("/api/positions?limit=500")
        assert res_over.status_code == 422






