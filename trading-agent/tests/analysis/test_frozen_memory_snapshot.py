import pytest
from datetime import datetime, timezone, timedelta
from analysis.memory.frozen_snapshot import (
    FrozenMemorySnapshot,
    FrozenSnapshotManager,
    get_frozen_snapshot_manager,
)


def test_frozen_memory_snapshot_immutability():
    playbooks = {"EURUSD": {"status": "active", "rule": "fade_extreme_atr"}}
    snapshot = FrozenMemorySnapshot(
        soul_content="Capital preservation is paramount.",
        macro_content="US Yields steady at 4.2%.",
        stable_core="REGIME: LOW_VOL_CHOP",
        active_playbooks=playbooks,
    )

    # Verify content properties
    assert snapshot.soul == "Capital preservation is paramount."
    assert "US Yields steady" in snapshot.macro_reality
    assert "REGIME: LOW_VOL_CHOP" in snapshot.stable_core
    assert snapshot.get_playbook("EURUSD") == {"status": "active", "rule": "fade_extreme_atr"}
    assert snapshot.get_playbook("eur_usd") == {"status": "active", "rule": "fade_extreme_atr"}

    # Verify system prompt prefix composition
    prefix = snapshot.system_prompt_prefix
    assert "Capital preservation is paramount." in prefix
    assert "# Verified Macroeconomic Ground-Truth" in prefix
    assert "# Core Trading Discipline & Regime" in prefix

    # Verify SHA256 deterministic hash
    assert len(snapshot.snapshot_hash) == 64
    second_snapshot = FrozenMemorySnapshot(
        soul_content="Capital preservation is paramount.",
        macro_content="US Yields steady at 4.2%.",
        stable_core="REGIME: LOW_VOL_CHOP",
        active_playbooks=playbooks,
    )
    assert snapshot.snapshot_hash == second_snapshot.snapshot_hash

    # Verify immutability of playbooks mapping
    with pytest.raises(TypeError):
        snapshot.playbooks["GBPUSD"] = {"status": "candidate"}  # MappingProxyType blocks mutations


def test_frozen_memory_snapshot_expiration():
    old_time = datetime.now(timezone.utc) - timedelta(seconds=4000)
    old_snapshot = FrozenMemorySnapshot(
        soul_content="Core rule",
        macro_content="Macro rule",
        created_at=old_time,
    )
    assert old_snapshot.is_expired(max_age_seconds=3600.0) is True

    fresh_snapshot = FrozenMemorySnapshot(
        soul_content="Core rule",
        macro_content="Macro rule",
    )
    assert fresh_snapshot.is_expired(max_age_seconds=3600.0) is False


@pytest.mark.asyncio
async def test_frozen_snapshot_manager_caching_and_rehydration():
    manager = FrozenSnapshotManager(settings={})
    snap1 = await manager.get_snapshot(force_refresh=False)
    snap2 = await manager.get_snapshot(force_refresh=False)

    # Without force_refresh, must return exact same snapshot instance (prefix cache hits)
    assert snap1 is snap2
    assert snap1.snapshot_hash == snap2.snapshot_hash

    # With rehydrate, forces new snapshot generation
    snap3 = await manager.rehydrate()
    assert snap3 is not None
    assert snap3.created_at >= snap1.created_at


@pytest.mark.asyncio
async def test_layered_memory_manager_integration():
    from analysis.memory.layered_memory import LayeredMemoryManager
    lmm = LayeredMemoryManager(settings={})
    snapshot = await lmm.get_frozen_snapshot()
    assert isinstance(snapshot, FrozenMemorySnapshot)
    assert snapshot.snapshot_hash is not None
