"""
Unit & regression tests for PositionGuardian kill-switch latch synchronization
and physical disk flag removal across resume and healing workflows.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from monika.application.execution.execution_service import ExecutionService
from monika.application.scheduler.position_guardian import PositionGuardian
from monika.application.services.trading_service import TradingService
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import SystemConfig
from scripts.heal_kill_switch_state import heal


@pytest.mark.asyncio
async def test_position_guardian_kill_switch_latch_no_oscillation(tmp_path, monkeypatch):
    """
    Verifies that PositionGuardian does not oscillate/loop kill_switch activations
    when data/kill_switch.flag is active on disk.
    """
    import monika.core.paths as core_paths

    fake_data_dir = tmp_path / "data"
    fake_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core_paths, "DATA_DIR", fake_data_dir)

    flag_file = fake_data_dir / "kill_switch.flag"
    flag_file.write_text('{"source": "test", "active": true}', encoding="utf-8")

    kill_calls = []

    mock_exec = MagicMock()

    async def mock_kill(reason: str):
        kill_calls.append(reason)
        # Emulate ExecutionService setting DB kill_switch to false
        async with get_session() as sess:
            cfg = (
                await sess.execute(select(SystemConfig).where(SystemConfig.key == "kill_switch"))
            ).scalar_one_or_none()
            if cfg:
                cfg.value = "false"
            else:
                sess.add(SystemConfig(key="kill_switch", value="false"))
            await sess.commit()

    mock_exec.kill_switch = AsyncMock(side_effect=mock_kill)

    guardian = PositionGuardian(settings={}, execution_service=mock_exec)

    # 1. First tick arrives -> trips kill switch
    tick1 = SimpleNamespace(symbol="USDJPY", bid=150.0, ask=150.02)
    await guardian.on_tick(tick1)
    assert len(kill_calls) == 1
    assert guardian._kill_switch_triggered is True

    # 2. Periodic surveillance check runs -> sees disk flag still active, must NOT reset latch to False
    res = await guardian.check_and_protect()
    assert res.get("kill_switch_active") is True
    assert guardian._kill_switch_triggered is True

    # 3. Second tick arrives on different symbol -> must NOT re-trip kill switch
    tick2 = SimpleNamespace(symbol="XAUUSD", bid=2700.0, ask=2700.5)
    await guardian.on_tick(tick2)
    assert len(kill_calls) == 1  # Still 1! No loop!


@pytest.mark.asyncio
async def test_resume_trading_clears_disk_flag(tmp_path, monkeypatch):
    """
    Verifies that ExecutionService and TradingService resume_trading routines
    clean up the physical data/kill_switch.flag file from disk.
    """
    import monika.core.paths as core_paths

    fake_data_dir = tmp_path / "data"
    fake_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core_paths, "DATA_DIR", fake_data_dir)

    flag_file = fake_data_dir / "kill_switch.flag"

    # Test ExecutionService.resume_trading
    flag_file.write_text('{"active": true}', encoding="utf-8")
    assert flag_file.exists()

    exec_svc = ExecutionService(settings={})
    async with get_session() as session:
        await exec_svc.resume_trading(session, requested_by="unit_test")

    assert not flag_file.exists()

    # Test TradingService.resume_trading
    flag_file.write_text('{"active": true}', encoding="utf-8")
    assert flag_file.exists()

    async with get_session() as session:
        await TradingService.resume_trading(session, actor="unit_test")

    assert not flag_file.exists()


@pytest.mark.asyncio
async def test_heal_script_clears_disk_flag(tmp_path, monkeypatch):
    """
    Verifies that heal_kill_switch_state.py clears the disk flag in execute mode
    while preserving it in dry-run mode.
    """
    import monika.core.paths as core_paths

    fake_data_dir = tmp_path / "data"
    fake_data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core_paths, "DATA_DIR", fake_data_dir)

    flag_file = fake_data_dir / "kill_switch.flag"
    flag_file.write_text('{"active": true}', encoding="utf-8")

    # Dry-run: flag must remain
    await heal(dry_run=True)
    assert flag_file.exists()

    # Confirm mode: flag must be deleted
    await heal(dry_run=False)
    assert not flag_file.exists()
