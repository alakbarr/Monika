import os
import time
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from analysis.memory.playbook_ledger import (
    PlaybookLedger,
    PlaybookState,
    PlaybookStatus,
    PlaybookMetadata,
    PlaybookLifecycleFSM,
    PlaybookLifecycleManager,
)
from analysis.memory.layered_memory import LayeredMemoryManager


@pytest.fixture
def temp_playbooks_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = PlaybookLedger(playbooks_dir=tmpdir)
        fsm = PlaybookLifecycleFSM(playbooks_dir=tmpdir, ledger=ledger)
        yield tmpdir, ledger, fsm


def test_playbook_ledger_exports():
    """Ensure all lifecycle classes are accessible from playbook_ledger."""
    assert PlaybookState is not None
    assert PlaybookStatus is PlaybookState
    assert PlaybookMetadata is not None
    assert PlaybookLifecycleFSM is not None
    assert PlaybookLifecycleManager is PlaybookLifecycleFSM


def test_playbook_promotion_to_active(temp_playbooks_env):
    tmpdir, ledger, fsm = temp_playbooks_env
    name = "XAUUSD_breakout"

    # Register candidate
    meta = fsm.register_playbook(name)
    assert meta.state == PlaybookState.CANDIDATE
    assert fsm.is_active(name) is False

    # Record 4 wins (not yet 5)
    for _ in range(4):
        fsm.record_trade_outcome(name, is_win=True, rr=2.0)
    assert fsm.get_state(name) == PlaybookState.CANDIDATE

    # 5th win triggers promotion
    res = fsm.record_trade_outcome(name, is_win=True, rr=2.5)
    assert res["state"] == PlaybookState.ACTIVE.value
    assert fsm.get_state(name) == PlaybookState.ACTIVE
    assert fsm.is_active(name) is True
    assert name in fsm.get_active_playbooks()


def test_playbook_demotion_to_stale_and_cooldown(temp_playbooks_env):
    tmpdir, ledger, fsm = temp_playbooks_env
    name = "EURUSD_breakout"

    # Seed versions in ledger
    ledger.record_mutation(name, "# v1", action="create")
    ledger.record_mutation(name, "# v2", action="update")

    # Promote to active
    fsm.register_playbook(name, state=PlaybookState.ACTIVE)
    assert fsm.is_active(name) is True

    # 3 consecutive losses
    res1 = fsm.record_trade_outcome(name, is_win=False, rr=-1.0)
    res2 = fsm.record_trade_outcome(name, is_win=False, rr=-1.0)
    assert fsm.get_state(name) == PlaybookState.ACTIVE

    res3 = fsm.record_trade_outcome(name, is_win=False, rr=-1.0)
    assert res3["state"] == PlaybookState.STALE.value
    assert fsm.get_state(name) == PlaybookState.STALE
    assert fsm.is_active(name) is False
    assert res3["rolled_back"] is True
    assert res3["stale_until_ts"] is not None
    assert res3["stale_until_ts"] > time.time() + 47 * 3600

    # Revalidation blocked during cooldown
    assert fsm.revalidate(name, force=False) is False
    assert fsm.get_state(name) == PlaybookState.STALE

    # Revalidation forced
    assert fsm.revalidate(name, force=True) is True
    assert fsm.get_state(name) == PlaybookState.CANDIDATE


def test_playbook_archival_on_low_winrate(temp_playbooks_env):
    tmpdir, ledger, fsm = temp_playbooks_env
    name = "BTCUSD_momentum"

    fsm.register_playbook(name, state=PlaybookState.CANDIDATE)

    # Record 20 trades with low win rate (6 wins, 14 losses = 30% WR < 45%)
    # Alternate to avoid 3 consecutive losses
    outcomes = [False, False, True, False, False, True, False, False, True, False,
                False, True, False, False, True, False, False, True, False, False]
    assert len(outcomes) == 20

    for won in outcomes[:-1]:
        fsm.record_trade_outcome(name, is_win=won, rr=1.5 if won else -1.0)

    # 20th trade triggers archival check
    res = fsm.record_trade_outcome(name, is_win=outcomes[-1], rr=-1.0)
    assert res["state"] == PlaybookState.ARCHIVED.value
    assert fsm.get_state(name) == PlaybookState.ARCHIVED
    assert fsm.is_active(name) is False
    assert name not in fsm.get_active_playbooks()


def test_evaluate_staleness_cooldown_expiration(temp_playbooks_env):
    tmpdir, ledger, fsm = temp_playbooks_env
    name = "USDJPY_mean_reversion"

    fsm.register_playbook(name, state=PlaybookState.STALE)
    meta = fsm.get_metadata(name)
    # Set stale_until_ts in past
    meta.stale_until_ts = time.time() - 100
    fsm._save_state()

    changed = fsm.evaluate_staleness()
    assert name in changed
    assert fsm.get_state(name) == PlaybookState.CANDIDATE
    assert fsm.get_metadata(name).stale_until_ts is None


@pytest.mark.asyncio
async def test_layered_memory_gating_excludes_stale_and_archived():
    mgr = LayeredMemoryManager()

    # Mock PlaybookLifecycleFSM and ProgressiveMemoryLoader
    with patch("analysis.memory.playbook_lifecycle.PlaybookLifecycleFSM") as MockFSM, \
         patch("analysis.memory.progressive_loader.ProgressiveMemoryLoader") as MockLoader:

        mock_fsm = MagicMock()
        mock_fsm.get_status.return_value = PlaybookState.STALE
        MockFSM.return_value = mock_fsm

        mock_loader = MagicMock()
        mock_loader.get_level1_playbook.return_value = "# EURUSD Playbook Content"
        MockLoader.return_value = mock_loader

        # STALE playbook should return empty string
        mem = await mgr.get_playbook_memory("EURUSD")
        assert mem == ""

        # ARCHIVED playbook should return empty string
        mock_fsm.get_status.return_value = PlaybookState.ARCHIVED
        mem = await mgr.get_playbook_memory("EURUSD")
        assert mem == ""

        # CANDIDATE playbook should return empty string
        mock_fsm.get_status.return_value = PlaybookState.CANDIDATE
        mem = await mgr.get_playbook_memory("EURUSD")
        assert mem == ""

        # ACTIVE playbook should return wrapped content
        mock_fsm.get_status.return_value = PlaybookState.ACTIVE
        mem = await mgr.get_playbook_memory("EURUSD")
        assert "# EURUSD Playbook Content" in mem
        assert "<market-memory-context>" in mem
