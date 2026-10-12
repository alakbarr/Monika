# ==============================================================================
# File: execution/execution_service.py
# ==============================================================================

"""
Layanan Eksekusi (Execution Service) - Backward-Compatible Facade.

Refactored into modular components under `execution/service/`:
- `order_executor.py`: OrderExecutorMixin for order placement, preplanned orders, and DB tracking.
- `risk_evaluator.py`: RiskEvaluatorMixin for sizing, open position counting, and equity checks.
- `position_synchronizer.py`: PositionSynchronizerMixin for MT5 position syncing and SL/TP maintenance.
- `emergency_manager.py`: EmergencyManagerMixin for emergency ticket closure and kill-switch.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from monika.infrastructure.database.db import get_session, transactional_advisory_lock
from monika.infrastructure.brokers.mt5_client import MT5Client
from monika.infrastructure.brokers.broker_adapter import BrokerAdapter, MT5LiveAdapter
from monika.domain.risk.position_sizing import PositionSizer, SizingResult
from monika.domain.risk.risk_gate import RiskGate

from monika.application.execution.service.order_executor import (
    ExecutionResult,
    OrderExecutorMixin,
    _EXECUTION_LOCK,
    _EXECUTED_ANALYSIS_IDS,
    _LAST_CLEANUP_TIME,
)
from monika.application.execution.service.risk_evaluator import RiskEvaluatorMixin
from monika.application.execution.service.position_synchronizer import PositionSynchronizerMixin
from monika.application.execution.service.emergency_manager import EmergencyManagerMixin
from monika.infrastructure.brokers.rate_throttler import RateThrottler

logger = logging.getLogger("TradingAgent.ExecutionService")


# ---------------------------------------------------------------------------
# Layanan Eksekusi (Execution Service)
# ---------------------------------------------------------------------------


class ExecutionService(OrderExecutorMixin, RiskEvaluatorMixin, PositionSynchronizerMixin, EmergencyManagerMixin):
    """
    Mengorkestrasi seluruh jalur dari analisis AI hingga eksekusi MT5.
    Backward-compatible facade combining modular execution service mixins.
    """

    def __init__(
        self,
        settings: dict,
        mt5_client: Optional[MT5Client] = None,
        dry_run: bool = False,
        broker_adapter: Optional[BrokerAdapter] = None,
        risk_gate: Optional[RiskGate] = None,
    ):
        """
        Args:
            settings:       Full settings dict.
            mt5_client:     Shared MT5Client instance.
            dry_run:        If True, skips actual MT5 order placement.
            broker_adapter: Standardized broker adapter interface (defaults to MT5LiveAdapter).
            risk_gate:      Optional existing RiskGate instance.
        """
        self.settings = settings
        if mt5_client is not None:
            self.mt5 = mt5_client
        else:
            self.mt5 = MT5Client(settings=self.settings)
        self.mt5_client = self.mt5  # Parity attribute alias
        self.sizer = PositionSizer(settings, mt5_client=self.mt5)
        self.gate = risk_gate if risk_gate is not None else RiskGate(settings, mt5_client=self.mt5)
        self.risk_gate = self.gate  # Backward-compatible alias
        paper_cfg = self.settings.get("trading", {}).get("paper_trading", {})
        if "enabled" in paper_cfg:
            paper_enabled = bool(paper_cfg["enabled"])
        elif "paper_trading" in self.settings:
            paper_enabled = bool(self.settings.get("paper_trading", {}).get("enabled", True))
        else:
            paper_enabled = True
        self.dry_run = dry_run or paper_enabled

        if broker_adapter is not None:
            self.broker_adapter = broker_adapter
        else:
            self.broker_adapter = MT5LiveAdapter(self.mt5, settings=self.settings, dry_run=self.dry_run, service=self)

        from monika.domain.execution.verification_engine import EvidenceFirstVerifier
        from monika.application.benchmark.trade_trajectory_logger import TradeTrajectoryLogger
        from monika.application.execution.effect_gate import EffectGate
        from monika.infrastructure.brokers.idempotency_guard import get_idempotency_guard

        self.evidence_verifier = EvidenceFirstVerifier(settings)
        self.trajectory_logger = TradeTrajectoryLogger()
        self.rate_throttler = RateThrottler(settings=self.settings)
        self.effect_gate = EffectGate()
        self.idempotency_guard = get_idempotency_guard()


__all__ = [
    "ExecutionResult",
    "ExecutionService",
    "OrderExecutorMixin",
    "RiskEvaluatorMixin",
    "PositionSynchronizerMixin",
    "EmergencyManagerMixin",
    "RateThrottler",
    "_EXECUTION_LOCK",
    "_EXECUTED_ANALYSIS_IDS",
    "_LAST_CLEANUP_TIME",
    "get_session",
    "transactional_advisory_lock",
    "PositionSizer",
    "RiskGate",
]
