# ==============================================================================
# File: analysis/memory/memory_lifecycle_gc.py
# Monika Memory Architecture: Ebbinghaus Forgetting Curve GC & Cold Compaction
# ==============================================================================

"""
Memory Lifecycle Garbage Collector & Compaction Engine.

Applies Ebbinghaus Forgetting Curve dynamics to empirical trading memories:
    R(t) = exp(- delta_t / S)
where:
    delta_t = time elapsed since last retrieval / reinforcement (days)
    S = S_base * (1 + ln(1 + retrieval_count)) * importance_weight
    S_base = base memory stability (default 14 days)

Lifecycle States:
1. ACTIVE (R >= 0.50): Injected into prompt working context for relevant market regimes.
2. DORMANT (0.20 <= R < 0.50): Retained in vector / database index for deep semantic retrieval,
   but excluded from standard preflight context.
3. OBSOLETE (R < 0.20): Compacted into cold storage archive JSON, freed from working memory.

Generates audit-trail log records (`gc.log`) with item counts and token recoveries.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TradingAgent.Memory.GC")


@dataclass
class MemoryNode:
    id: str
    category: str  # "trade_reflection", "macro_lesson", "failure_pattern", "skill"
    summary: str
    created_at: datetime
    last_retrieved_at: datetime
    retrieval_count: int = 1
    importance_weight: float = 1.0  # 1.0 = normal, 2.0 = critical loss/lesson
    retention_score: float = 1.0
    status: str = "active"  # "active", "dormant", "archived"


@dataclass
class GCReport:
    run_at: str
    total_scanned: int
    active_retained: int
    dormant_flagged: int
    archived_evicted: int
    tokens_recovered_est: int
    details: List[Dict[str, Any]] = field(default_factory=list)


class MemoryLifecycleGC:
    """Ebbinghaus memory garbage collector and archival manager."""

    def __init__(
        self,
        base_stability_days: float = 14.0,
        active_threshold: float = 0.50,
        archive_threshold: float = 0.20,
        archive_dir: Optional[Path] = None,
    ):
        self.base_stability_days = base_stability_days
        self.active_threshold = active_threshold
        self.archive_threshold = archive_threshold
        self.archive_dir = archive_dir or Path("memory_archive")

    def compute_retention(
        self,
        node: MemoryNode,
        as_of: Optional[datetime] = None,
    ) -> float:
        """
        Calculates retention probability R(t) = exp(-delta_t / S).
        """
        now = as_of or datetime.now(timezone.utc)
        last_seen = node.last_retrieved_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        delta_days = max(0.0, (now - last_seen).total_seconds() / 86400.0)

        # Stability S scales with reinforcement and importance
        reinforcement_boost = 1.0 + math.log(1.0 + max(0, node.retrieval_count))
        stability = self.base_stability_days * reinforcement_boost * max(0.2, node.importance_weight)

        retention = math.exp(-delta_days / max(0.1, stability))
        return round(min(1.0, max(0.0, retention)), 4)

    def run_gc_pass(
        self,
        nodes: List[MemoryNode],
        as_of: Optional[datetime] = None,
    ) -> Tuple[List[MemoryNode], GCReport]:
        """
        Evaluates a collection of memory nodes, updates retention scores,
        transitions statuses, and archives obsolete items.
        Returns: (remaining_nodes, gc_report)
        """
        now_dt = as_of or datetime.now(timezone.utc)
        active_nodes: List[MemoryNode] = []
        dormant_nodes: List[MemoryNode] = []
        archived_nodes: List[MemoryNode] = []
        details: List[Dict[str, Any]] = []
        chars_recovered = 0

        for node in nodes:
            r = self.compute_retention(node, as_of=now_dt)
            node.retention_score = r

            if r >= self.active_threshold:
                node.status = "active"
                active_nodes.append(node)
            elif r >= self.archive_threshold:
                node.status = "dormant"
                dormant_nodes.append(node)
                details.append({
                    "id": node.id,
                    "action": "dormant_flagged",
                    "retention": r,
                    "summary": node.summary[:60],
                })
            else:
                node.status = "archived"
                archived_nodes.append(node)
                chars_recovered += len(node.summary)
                details.append({
                    "id": node.id,
                    "action": "archived_evicted",
                    "retention": r,
                    "summary": node.summary[:60],
                })

        # Save archived nodes to cold storage
        if archived_nodes:
            self._save_to_archive(archived_nodes, now_dt)

        remaining = active_nodes + dormant_nodes
        report = GCReport(
            run_at=now_dt.isoformat(),
            total_scanned=len(nodes),
            active_retained=len(active_nodes),
            dormant_flagged=len(dormant_nodes),
            archived_evicted=len(archived_nodes),
            tokens_recovered_est=chars_recovered // 4,
            details=details,
        )

        logger.info(
            f"[MemoryGC] Pass complete: {len(nodes)} scanned -> {len(active_nodes)} active, "
            f"{len(dormant_nodes)} dormant, {len(archived_nodes)} evicted (~{report.tokens_recovered_est} tokens saved)"
        )
        return remaining, report

    def _save_to_archive(self, evicted_nodes: List[MemoryNode], timestamp: datetime) -> None:
        """Appends evicted memory items to cold JSON archive file."""
        try:
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            archive_file = self.archive_dir / f"cold_archive_{timestamp.strftime('%Y%m')}.jsonl"
            with open(archive_file, "a", encoding="utf-8") as f:
                for n in evicted_nodes:
                    record = {
                        "id": n.id,
                        "category": n.category,
                        "summary": n.summary,
                        "created_at": n.created_at.isoformat(),
                        "last_retrieved_at": n.last_retrieved_at.isoformat(),
                        "retrieval_count": n.retrieval_count,
                        "importance_weight": n.importance_weight,
                        "retention_score": n.retention_score,
                        "archived_at": timestamp.isoformat(),
                    }
                    f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"[MemoryGC] Failed to persist cold archive: {e}")
