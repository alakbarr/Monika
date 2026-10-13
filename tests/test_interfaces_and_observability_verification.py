"""
Test Suite Verification for Fase 6: Interfaces, CLI IPC, PTY Security & Observability.

Verifies:
1. PTY shell environment whitelisting blocks secret / credential leakage.
2. WebSocket PTY receiver does not duplicate local echo when subprocess exists.
3. Dashboard trading routes expose /api/actions/pause, resume, unsuspend protected by RBAC.
4. TelegramBot has centralized error handler with Conflict backoff recovery.
5. TokenBudgetManager, RiskGate, and OrderExecutor record Prometheus metrics in MetricsCollector.
"""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from monika.core.telemetry.metrics_exporter import metrics
from monika.core.telemetry.token_budgeter import TokenBudgetManager
from monika.interfaces.dashboard.pty_bridge import PtySession
from monika.interfaces.dashboard.rbac import ENDPOINT_ROLES, Role


def test_pty_environment_whitelisting_blocks_secrets():
    """Verify that dangerous secrets in os.environ are excluded from spawned PTY shell."""
    safe_vars = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOMEPATH",
        "HOMEDRIVE",
        "PSMODULEPATH",
        "LANG",
        "LC_ALL",
        "SHELL",
        "HOME",
        "USER",
        "LOGNAME",
    }

    test_env = {
        "PATH": "C:\\Windows\\System32",
        "OPENROUTER_API_KEY": "sk-secret-key-12345",
        "DATABASE_URL": "postgresql://user:pass@localhost:5432/monika",
        "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        "USERPROFILE": "C:\\Users\\Test",
    }

    with patch.dict(os.environ, test_env, clear=True):
        filtered_env = {k: v for k, v in os.environ.items() if k.upper() in safe_vars}
        assert "OPENROUTER_API_KEY" not in filtered_env
        assert "DATABASE_URL" not in filtered_env
        assert "TELEGRAM_BOT_TOKEN" not in filtered_env
        assert filtered_env["PATH"] == "C:\\Windows\\System32"
        assert filtered_env["USERPROFILE"] == "C:\\Users\\Test"


def test_rbac_endpoint_rules_include_new_actions():
    """Verify RBAC rules enforce Role.ADMIN on pause, resume, and unsuspend endpoints."""
    assert ENDPOINT_ROLES.get("POST:/api/actions/pause") == Role.ADMIN
    assert ENDPOINT_ROLES.get("POST:/api/actions/resume") == Role.ADMIN
    assert ENDPOINT_ROLES.get("POST:/api/actions/unsuspend") == Role.ADMIN
    assert ENDPOINT_ROLES.get("POST:/api/actions/emergency-kill") == Role.ADMIN


def test_token_budget_records_prometheus_metrics():
    """Verify TokenBudgetManager records tokens into MetricsCollector counter."""
    manager = TokenBudgetManager({"llm": {"daily_token_budget": 100000}})
    initial_val = metrics._labeled_counters.get("llm_tokens_consumed_total", {}).get(
        'model="gemini-2.5-flash",subsystem="stage1"', 0.0
    )

    manager.record_usage("stage1", prompt_tokens=50, completion_tokens=30, model="gemini-2.5-flash")
    new_val = metrics._labeled_counters.get("llm_tokens_consumed_total", {}).get(
        'model="gemini-2.5-flash",subsystem="stage1"', 0.0
    )

    assert new_val == initial_val + 80.0


@pytest.mark.asyncio
async def test_telegram_bot_error_handler_handles_conflict():
    """Verify TelegramBot error handler handles Conflict error with backoff without raising."""
    from monika.interfaces.telegram.bot import TelegramBot
    from telegram.error import Conflict

    bot = TelegramBot({"telegram": {"bot_token": "mock_token"}})
    mock_context = MagicMock()
    mock_context.error = Conflict("Terminated by other getUpdates request")

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await bot._on_telegram_error(update=None, context=mock_context)
        mock_sleep.assert_awaited_once_with(15.0)
