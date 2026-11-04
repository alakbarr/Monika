"""
Package: monika.core.primitives
File: compaction.py
Description: Architectural Protocol & Registry for Progressive Memory Compaction (Pillar 5).
Clean Architecture compliant: Core definitions with zero outer layer dependencies.
"""

from __future__ import annotations

import logging
from typing import List, Protocol, runtime_checkable

logger = logging.getLogger("TradingAgent.Compaction")


@runtime_checkable
class CompactionTarget(Protocol):
    """
    Protocol for components that participate in memory compaction.
    Tiers:
    - Tier 1: Soft prune (LRU expiration, ephemeral cache flush, zero IO).
    - Tier 2: Medium prune (Identity map expunge, generational GC collect 1).
    - Tier 3: Aggressive prune (WAL checkpoint, connection pool recycle, GC collect 2).
    """

    def compact(self, tier: int) -> int:
        """Execute compaction for the given tier. Returns count of freed entries/objects."""
        ...


class CompactionRegistry:
    """Central registry of compaction targets."""

    def __init__(self) -> None:
        self._targets: List[CompactionTarget] = []

    def register(self, target: CompactionTarget) -> None:
        """Register a compaction target."""
        if target not in self._targets:
            self._targets.append(target)

    def unregister(self, target: CompactionTarget) -> None:
        """Unregister a compaction target."""
        if target in self._targets:
            self._targets.remove(target)

    def compact_all(self, tier: int = 1) -> int:
        """Trigger compaction across all registered targets for specified tier."""
        total_freed = 0
        for target in list(self._targets):
            try:
                freed = target.compact(tier)
                if isinstance(freed, int):
                    total_freed += freed
            except Exception as e:
                logger.debug(f"[CompactionRegistry] Target error in tier {tier}: {e}")
        return total_freed


_GLOBAL_COMPACTION_REGISTRY: CompactionRegistry | None = None


def get_compaction_registry() -> CompactionRegistry:
    """Singleton getter for CompactionRegistry."""
    global _GLOBAL_COMPACTION_REGISTRY
    if _GLOBAL_COMPACTION_REGISTRY is None:
        _GLOBAL_COMPACTION_REGISTRY = CompactionRegistry()
    return _GLOBAL_COMPACTION_REGISTRY
