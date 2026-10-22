"""
Unit and integration tests for Phase 2 Architectural Remediation:
Core Primitives, Configuration Management, Fail-Closed Validation & Composition Root.
"""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monika.core.config.atomic_writer import AtomicConfigWriter
from monika.core.config.env_file_manager import EnvFileManager
from monika.core.config.migrations import (
    CURRENT_CONFIG_VERSION,
    get_config_version,
    migrate_config,
    migrate_settings,
)
from monika.core.primitives.clock import clock, ensure_utc, frozen_time, now, set_simulated_now
from monika.core.primitives.event_bus import AppEvent, EventBus
from monika.core.primitives.turn_marker import TurnMarker, TurnMarkerManager
from monika.core.primitives.worktree import SubagentWorktree
from monika.core.validation.data_temporal_validator import DataTemporalValidator
from monika.core.validation.data_validator import is_spread_acceptable
from monika.domain.risk.position_sizing import SizingResult
from monika.domain.risk.risk_gate import RiskGate


# ==============================================================================
# 1. Financial Safety & Fail-Closed Validation
# ==============================================================================


@pytest.mark.asyncio
async def test_market_checks_fail_closed_when_validator_missing():
    """If default data freshness validator is None, market checks MUST reject (fail-closed)."""
    gate = RiskGate(settings={"trading": {}})
    with patch("monika.domain.risk.ports.get_default_data_freshness_validator", return_value=None):
        passed, reason = await gate._check_data_freshness(session=None, symbol="XAUUSD")
        assert passed is False
        assert "not_configured" in reason


@pytest.mark.asyncio
async def test_market_checks_fail_closed_when_not_ready():
    """If data freshness returns ready=False or missing ready key, MUST reject."""
    gate = RiskGate(settings={"trading": {}})
    mock_validator = AsyncMock(return_value={"ready": False, "errors": ["H1 OHLCV stale"]})
    with patch("monika.domain.risk.ports.get_default_data_freshness_validator", return_value=mock_validator):
        passed, reason = await gate._check_data_freshness(session=None, symbol="XAUUSD")
        assert passed is False
        assert "Stale market data" in reason


def test_spread_circuit_breaker_nan_and_inf_rejection():
    """NaN, infinite, negative, or inverted prices MUST evaluate to False (trading blocked)."""
    nan = float("nan")
    inf = float("inf")

    assert is_spread_acceptable("EURUSD", nan, 1.0500) is False
    assert is_spread_acceptable("EURUSD", 1.0500, nan) is False
    assert is_spread_acceptable("EURUSD", inf, 1.0500) is False
    assert is_spread_acceptable("EURUSD", 1.0500, inf) is False
    assert is_spread_acceptable("EURUSD", -1.0500, 1.0500) is False
    assert is_spread_acceptable("EURUSD", 1.0500, 1.0400) is False  # Inverted (ask < bid)
    # Valid spread
    assert is_spread_acceptable("EURUSD", 1.0500, 1.0501) is True


@pytest.mark.asyncio
async def test_risk_gate_modular_registry_failure_fail_closed():
    """If a modular risk check raises an exception, the trade MUST be rejected."""
    gate = RiskGate(settings={"trading": {"risk": {"max_risk_per_trade_percent": 1.0}}})

    mock_registry = MagicMock()
    mock_registry.evaluate_modular_rules = AsyncMock(
        side_effect=RuntimeError("Database connection severed during risk evaluation")
    )
    gate.modular_risk_registry = mock_registry

    sizing = SizingResult(
        symbol="EURUSD",
        direction="buy",
        entry_price=1.0500,
        stop_loss=1.0400,
        take_profit=1.0700,
        account_equity=10000.0,
        risk_percent=1.0,
        risk_amount_usd=100.0,
        sl_distance_price=0.0100,
        sl_distance_pips=100.0,
        pip_value_per_lot=10.0,
        raw_lots=0.1,
        recommended_lots=0.1,
        rr_ratio=2.0,
        is_valid=True,
    )
    res = await gate.evaluate(
        session=None,
        symbol="EURUSD",
        direction="buy",
        sizing=sizing,
        account_equity=10000.0,
        is_backtest=True,
    )
    assert res.approved is False
    assert "modular_risk_registry" in res.checks_failed


# ==============================================================================
# 2. Core Primitives Hardening
# ==============================================================================


def test_turn_marker_poison_pill_prevention(tmp_path: Path):
    """Crash recovery attempts must increment and discard after 3 failed recoveries."""
    mgr = TurnMarkerManager(marker_dir=tmp_path)
    marker = TurnMarker(
        session_id="sess_123",
        task_type="recurring_cycle",
        symbol="EURUSD",
        stage="analysis",
        started_at=datetime.now(UTC).timestamp(),
        attempts=1,
    )
    mgr.record_start(marker)

    # Attempt 1 -> reads marker, increments attempts to 2
    m1 = mgr.check_interrupted(max_age_seconds=60.0)
    assert m1 is not None
    assert m1.attempts == 2

    # Attempt 2 -> reads marker, increments attempts to 3
    m2 = mgr.check_interrupted(max_age_seconds=60.0)
    assert m2 is not None
    assert m2.attempts == 3

    # Attempt 3 -> attempts >= 3, discarded as poison pill!
    m3 = mgr.check_interrupted(max_age_seconds=60.0)
    assert m3 is None
    assert not mgr.marker_file.exists()


def test_subagent_worktree_path_traversal_rejection(tmp_path: Path):
    """Path traversal sequences in subagent_id must be rejected immediately."""
    with pytest.raises(ValueError, match="Invalid subagent_id"):
        SubagentWorktree(subagent_id="../../malicious", base_dir=tmp_path)

    with pytest.raises(ValueError, match="Invalid subagent_id"):
        SubagentWorktree(subagent_id="sub/slash", base_dir=tmp_path)

    # Valid ID succeeds
    wt = SubagentWorktree(subagent_id="valid-sub_01", base_dir=tmp_path, use_git=False)
    assert wt.worktree_dir.name == "subagent-valid-sub_01"


def test_clock_ensure_utc_and_frozen_time():
    """Clock must strictly enforce UTC timezone awareness."""
    naive_dt = datetime(2026, 1, 15, 12, 0, 0)
    aware_utc = ensure_utc(naive_dt)
    assert aware_utc is not None
    assert aware_utc.tzinfo == UTC

    # Non-UTC aware datetime converted to UTC
    est = timezone(timedelta(hours=-5))
    est_dt = datetime(2026, 1, 15, 7, 0, 0, tzinfo=est)
    converted = ensure_utc(est_dt)
    assert converted is not None
    assert converted.tzinfo == UTC
    assert converted.hour == 12

    # Frozen time with EST converts to UTC
    with frozen_time(est_dt):
        current = now()
        assert current.tzinfo == UTC
        assert current.hour == 12

    set_simulated_now(None)


@pytest.mark.asyncio
async def test_event_bus_cancellation_no_double_task_done():
    """EventBus background worker cancellation must not trigger ValueError: task_done() called too many times."""
    bus = EventBus()
    queue = bus.get_or_create_queue("test_q")
    worker = bus.start_queue_worker("test_q")

    # Cancel worker while waiting on queue or executing
    worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker

    # Queue should still be healthy
    assert queue.empty()


# ==============================================================================
# 3. Config Subsystem Consolidation
# ==============================================================================


def test_env_file_manager_rejects_literal_newlines(tmp_path: Path):
    """EnvFileManager must reject newline injection attempts."""
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING_KEY=123\n", encoding="utf-8")

    with pytest.raises(ValueError, match="cannot contain literal newline"):
        EnvFileManager.update_env_values(
            {"INJECTED": "val\nADMIN_OVERRIDE=true"},
            env_path=str(env_file),
        )

    # File content preserved unmodified
    content = env_file.read_text(encoding="utf-8")
    assert "ADMIN_OVERRIDE" not in content


def test_config_migrations_discrete_ladder():
    """Config migrations must execute step-by-step and upgrade versions accurately."""
    v1_config = {
        "_config_version": 1,
        "trading": {"symbols": ["XAUUSD"]},
    }
    migrated, was_migrated = migrate_config(v1_config)
    assert was_migrated is True
    assert migrated["_config_version"] == CURRENT_CONFIG_VERSION
    assert "token_budget" in migrated
    assert "paper_trading" in migrated
    assert "security" in migrated

    # Idempotent on current version
    migrated_again, modified_again = migrate_config(migrated)
    assert modified_again is False
    assert migrated_again["_config_version"] == CURRENT_CONFIG_VERSION
