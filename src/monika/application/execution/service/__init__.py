"""Execution service orchestration mixins."""

from monika.application.execution.service.emergency_manager import EmergencyManagerMixin
from monika.application.execution.service.order_executor import (
    _EXECUTED_ANALYSIS_IDS,
    _EXECUTION_LOCK,
    _LAST_CLEANUP_TIME,
    ExecutionResult,
    OrderExecutorMixin,
)
from monika.application.execution.service.order_lifecycle_service import OrderLifecycleService
from monika.application.execution.service.position_synchronizer import PositionSynchronizerMixin
from monika.application.execution.service.reconciliation import ReconciliationHelper
from monika.application.execution.service.risk_evaluator import RiskEvaluatorMixin
from monika.application.execution.service.base import _ExecutionServiceMixinBase
from monika.domain.execution.order_creator import OrderCreator
from monika.domain.execution.sizing_calculator import SizingCalculator
from monika.domain.execution.state_machine import OrderStateMachine
from monika.infrastructure.brokers.audit_logger import TradeAuditLogger
from monika.infrastructure.database.models import Order

# Register ORM Order model and lifecycle transition handler for application execution service
OrderCreator.set_order_class(Order)
OrderStateMachine.set_lifecycle_handler(OrderLifecycleService.transition_order_state)

__all__ = [
    "ExecutionResult",
    "_ExecutionServiceMixinBase",
    "OrderExecutorMixin",
    "RiskEvaluatorMixin",
    "PositionSynchronizerMixin",
    "EmergencyManagerMixin",
    "OrderStateMachine",
    "OrderLifecycleService",
    "TradeAuditLogger",
    "ReconciliationHelper",
    "SizingCalculator",
    "OrderCreator",
    "_EXECUTION_LOCK",
    "_EXECUTED_ANALYSIS_IDS",
    "_LAST_CLEANUP_TIME",
]
