# ==============================================================================
# File: execution/service/order_executor.py
# ==============================================================================

"""
Order Executor Service Coordinator.
Orchestrates trade execution pipelines by composing modular executor mixins:
- ProposalOrderMixin: PR-14 Financial Fortress proposal validation & execution
- PreplannedOrderMixin: Sub-second conditional trigger execution
- PairedOrderMixin: Two-legged simultaneous & spread hedged order execution
- TrancheOrderMixin: Multi-target tranche scaling order execution
- AnalysisOrderMixin: Single AssetAnalysis preflight validation and locked broker execution
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import monika.infrastructure.database.db as _db_mod
from monika.application.execution.service.base import _ExecutionServiceMixinBase
from monika.domain.risk.position_sizing import SizingResult
from monika.infrastructure.database.safe_ops import safe_commit
from monika.infrastructure.infra.notifier import AgentNotifier

logger = logging.getLogger("TradingAgent.ExecutionService.OrderExecutor")


def get_session():
    import sys

    es = sys.modules.get("monika.application.execution.execution_service")
    fn = getattr(es, "get_session", None) if es else None
    if fn is not None:
        return fn()
    from monika.infrastructure.database.db import get_session as _real_get_session

    return _real_get_session()


def transactional_advisory_lock(*args, **kwargs):
    import sys

    es = sys.modules.get("monika.application.execution.execution_service")
    fn = getattr(es, "transactional_advisory_lock", None) if es else None
    if fn is not None:
        return fn(*args, **kwargs)
    from monika.infrastructure.database.db import transactional_advisory_lock as _real_lock

    return _real_lock(*args, **kwargs)


@dataclass
class ExecutionResult:
    """Hasil lengkap dari percobaan eksekusi, mulai dari sizing hingga MT5."""

    symbol: str
    analysis_id: Optional[int]
    decision: str  # buy | sell | avoid | wait

    # Sizing
    sizing: Optional[SizingResult]

    # Risk gate
    risk_approved: bool
    risk_checks_passed: list[str]
    risk_checks_failed: list[str]
    risk_rejection_reasons: list[str]

    # MT5 execution
    executed: bool
    mt5_ticket: Optional[int]
    executed_price: Optional[float]
    executed_lots: Optional[float]
    mt5_error: Optional[str]

    # DB
    position_id: Optional[int]

    # Metadata
    timestamp: datetime
    elapsed_ms: float

    def summary(self) -> str:
        if not self.risk_approved:
            return (
                f"BLOCKED [{self.symbol}] {self.decision.upper()} — RiskGate: {'; '.join(self.risk_rejection_reasons)}"
            )
        if self.executed:
            return (
                f"EXECUTED [{self.symbol}] {self.decision.upper()} "
                f"{self.executed_lots}lots @ {self.executed_price} | "
                f"ticket={self.mt5_ticket}"
            )
        return f"FAILED [{self.symbol}] {self.decision.upper()} — MT5: {self.mt5_error}"


_EXECUTED_ANALYSIS_IDS = {}
_LAST_CLEANUP_TIME = time.time()
_EXECUTION_LOCK = asyncio.Lock()


class AnalysisPrunerState:
    """Manages TTL prune state and timestamp tracking for executed analysis IDs."""

    last_cleanup_time: float = _LAST_CLEANUP_TIME

    @classmethod
    def get_last_cleanup_time(cls) -> float:
        mod = sys.modules.get(__name__)
        if mod and hasattr(mod, "_LAST_CLEANUP_TIME"):
            return float(getattr(mod, "_LAST_CLEANUP_TIME"))
        return cls.last_cleanup_time

    @classmethod
    def set_last_cleanup_time(cls, ts: float) -> None:
        cls.last_cleanup_time = ts
        mod = sys.modules.get(__name__)
        if mod:
            setattr(mod, "_LAST_CLEANUP_TIME", ts)

    @classmethod
    def reset(cls) -> None:
        now = time.time()
        cls.last_cleanup_time = now
        mod = sys.modules.get(__name__)
        if mod:
            setattr(mod, "_LAST_CLEANUP_TIME", now)


def _prune_executed_analysis_ids(ttl_seconds: float = 86400.0) -> None:
    """
    Prune entries in _EXECUTED_ANALYSIS_IDS older than ttl_seconds (default 24h / 86,400s)
    to prevent memory leak over weeks of 24/7 uptime (M-8).
    Mutates dictionary in-place to preserve reference identity across imports.
    """
    now = time.time()
    last_cleanup = AnalysisPrunerState.get_last_cleanup_time()
    if (now - last_cleanup) >= 60.0 or len(_EXECUTED_ANALYSIS_IDS) > 200:
        expired = []
        for aid, ts in list(_EXECUTED_ANALYSIS_IDS.items()):
            if not isinstance(ts, (int, float)) or isinstance(ts, bool) or (now - ts) >= ttl_seconds:
                expired.append(aid)
        for aid in expired:
            _EXECUTED_ANALYSIS_IDS.pop(aid, None)
        AnalysisPrunerState.set_last_cleanup_time(now)


from monika.application.execution.service.executors.analysis_executor import AnalysisOrderMixin
from monika.application.execution.service.executors.paired_executor import PairedOrderMixin
from monika.application.execution.service.executors.preplanned_executor import PreplannedOrderMixin
from monika.application.execution.service.executors.proposal_executor import ProposalOrderMixin
from monika.application.execution.service.executors.tranche_executor import TrancheOrderMixin


class OrderExecutorMixin(
    ProposalOrderMixin,
    PreplannedOrderMixin,
    PairedOrderMixin,
    TrancheOrderMixin,
    AnalysisOrderMixin,
    _ExecutionServiceMixinBase,
):
    """Mixin untuk alur eksekusi order (analisis tunggal, berpasangan, preplanned, tranche, proposal)."""


__all__ = [
    "ExecutionResult",
    "OrderExecutorMixin",
    "_EXECUTION_LOCK",
    "_EXECUTED_ANALYSIS_IDS",
    "_LAST_CLEANUP_TIME",
    "_prune_executed_analysis_ids",
    "get_session",
    "transactional_advisory_lock",
    "safe_commit",
    "AgentNotifier",
]
