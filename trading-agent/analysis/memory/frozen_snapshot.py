"""
File: trading-agent/analysis/memory/frozen_snapshot.py

Freeze-Snapshot Memory Engine & Prompt-Cache Preservation.
Provides immutable, hash-verified memory snapshots for agent execution cycles,
ensuring 100% stable system prompt prefixes across multi-turn reasoning and
maximizing LLM provider KV-cache hits.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("TradingAgent.FrozenSnapshot")


class FrozenMemorySnapshot:
    """
    Immutable snapshot of core trading soul, macro ground-truth, and active playbooks.
    Once instantiated, contents cannot be mutated mid-turn, preserving provider prefix cache.
    """

    def __init__(
        self,
        soul_content: str,
        macro_content: str,
        stable_core: str = "",
        active_playbooks: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
    ):
        self._soul = str(soul_content or "").strip()
        self._macro = str(macro_content or "").strip()
        self._stable_core = str(stable_core or "").strip()
        self._playbooks = MappingProxyType(dict(active_playbooks or {}))
        self._created_at = created_at or datetime.now(timezone.utc)

        # Deterministic SHA256 content hash
        hash_payload = json.dumps(
            {
                "soul": self._soul,
                "macro": self._macro,
                "stable_core": self._stable_core,
                "playbooks": {k: str(v) for k, v in sorted(self._playbooks.items())},
            },
            sort_keys=True,
        ).encode("utf-8")
        self._snapshot_hash = hashlib.sha256(hash_payload).hexdigest()

    @property
    def soul(self) -> str:
        return self._soul

    @property
    def macro_reality(self) -> str:
        return self._macro

    @property
    def stable_core(self) -> str:
        return self._stable_core

    @property
    def playbooks(self) -> MappingProxyType:
        return self._playbooks

    @property
    def snapshot_hash(self) -> str:
        return self._snapshot_hash

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def system_prompt_prefix(self) -> str:
        """
        Cache-stable system prompt prefix.
        Combines invariant soul, verified macro reality, and stable core discipline.
        Guaranteed identical across all turns within the cycle.
        """
        sections = []
        if self._soul:
            sections.append(self._soul)
        if self._macro:
            sections.append(f"# Verified Macroeconomic Ground-Truth\n{self._macro}")
        if self._stable_core:
            sections.append(f"# Core Trading Discipline & Regime\n{self._stable_core}")
        return "\n\n".join(sections)

    def get_playbook(self, symbol: str) -> Optional[Any]:
        """Retrieve symbol playbook from frozen snapshot without disk/DB mutation."""
        clean = (symbol or "").upper().replace("/", "").replace("_", "")
        return self._playbooks.get(clean)

    def is_expired(self, max_age_seconds: float = 3600.0) -> bool:
        """Check if snapshot age exceeds cycle boundary TTL."""
        age = (datetime.now(timezone.utc) - self._created_at).total_seconds()
        return age > max_age_seconds

    def __repr__(self) -> str:
        return (
            f"<FrozenMemorySnapshot hash={self._snapshot_hash[:12]} "
            f"playbooks={len(self._playbooks)} created={self._created_at.isoformat()}>"
        )


class FrozenSnapshotManager:
    """
    Singleton / Lifecycle Manager for FrozenMemorySnapshot.
    Re-hydrates snapshots strictly at cycle boundaries or upon explicit invalidation.
    """

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        self._current_snapshot: Optional[FrozenMemorySnapshot] = None
        self._lock = asyncio.Lock()

    async def get_snapshot(
        self,
        session: Optional[AsyncSession] = None,
        force_refresh: bool = False,
        max_age_seconds: float = 3600.0,
    ) -> FrozenMemorySnapshot:
        """
        Retrieve current active frozen snapshot or build a new one if missing/expired.
        Thread-safe under async lock.
        """
        async with self._lock:
            if (
                not force_refresh
                and self._current_snapshot is not None
                and not self._current_snapshot.is_expired(max_age_seconds)
            ):
                return self._current_snapshot

            self._current_snapshot = await self._build_snapshot(session)
            logger.info(
                f"[FrozenSnapshotManager] Hydrated new memory snapshot: {self._current_snapshot}"
            )
            return self._current_snapshot

    async def rehydrate(self, session: Optional[AsyncSession] = None) -> FrozenMemorySnapshot:
        """Explicitly rehydrate snapshot at cycle boundary."""
        return await self.get_snapshot(session=session, force_refresh=True)

    async def _build_snapshot(self, session: Optional[AsyncSession] = None) -> FrozenMemorySnapshot:
        """Internal assembly of frozen snapshot from disk configs and database."""
        # 1. Load TRADING_SOUL.md
        root_dir = Path(__file__).resolve().parent.parent.parent
        soul_path = root_dir / "config" / "TRADING_SOUL.md"
        soul_content = ""
        if soul_path.exists():
            try:
                soul_content = soul_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read TRADING_SOUL.md: {e}")

        # 2. Load MACRO_REALITY.md
        macro_path = root_dir / "config" / "MACRO_REALITY.md"
        macro_content = ""
        if macro_path.exists():
            try:
                macro_content = macro_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read MACRO_REALITY.md: {e}")

        # 3. Load Layer 1A Stable Core Memory
        stable_core = ""
        try:
            from analysis.memory.layered_memory import LayeredMemoryManager
            mgr = LayeredMemoryManager(self.settings)
            stable_core = await mgr.get_stable_core_memory(session)
        except Exception as e:
            logger.debug(f"Failed to load stable core memory for snapshot: {e}")

        # 4. Load Active Playbooks
        active_playbooks: Dict[str, Any] = {}
        try:
            from analysis.memory.playbook_lifecycle import PlaybookLifecycleManager
            lifecycle = PlaybookLifecycleManager()
            all_pbs = lifecycle.list_all_playbooks() if hasattr(lifecycle, "list_all_playbooks") else {}
            for sym, pb in (all_pbs or {}).items():
                if getattr(pb, "status", None) == "active" or (isinstance(pb, dict) and pb.get("status") == "active"):
                    active_playbooks[sym.upper()] = pb
        except Exception as e:
            logger.debug(f"Failed to load active playbooks for snapshot: {e}")

        return FrozenMemorySnapshot(
            soul_content=soul_content,
            macro_content=macro_content,
            stable_core=stable_core,
            active_playbooks=active_playbooks,
        )


# Global singleton instance
_GLOBAL_SNAPSHOT_MANAGER: Optional[FrozenSnapshotManager] = None


def get_frozen_snapshot_manager(settings: Optional[dict] = None) -> FrozenSnapshotManager:
    """Get or initialize global FrozenSnapshotManager instance."""
    global _GLOBAL_SNAPSHOT_MANAGER
    if _GLOBAL_SNAPSHOT_MANAGER is None:
        _GLOBAL_SNAPSHOT_MANAGER = FrozenSnapshotManager(settings)
    return _GLOBAL_SNAPSHOT_MANAGER
