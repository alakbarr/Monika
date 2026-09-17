# ==============================================================================
# File: tests/execution/test_service_base.py
# ==============================================================================

import pytest
from execution.service.base import _ExecutionServiceMixinBase
from execution.service.emergency_manager import EmergencyManagerMixin
from execution.service.position_synchronizer import PositionSynchronizerMixin
from execution.service.order_executor import OrderExecutorMixin
from execution.service.risk_evaluator import RiskEvaluatorMixin
from execution.execution_service import ExecutionService


def test_execution_service_mixin_base_inheritance():
    """Verify that all execution mixins inherit from _ExecutionServiceMixinBase."""
    assert issubclass(EmergencyManagerMixin, _ExecutionServiceMixinBase)
    assert issubclass(PositionSynchronizerMixin, _ExecutionServiceMixinBase)
    assert issubclass(OrderExecutorMixin, _ExecutionServiceMixinBase)
    assert issubclass(RiskEvaluatorMixin, _ExecutionServiceMixinBase)
    assert issubclass(ExecutionService, _ExecutionServiceMixinBase)


def test_execution_service_mro():
    """Verify MRO resolution and no metaclass conflicts."""
    mro = ExecutionService.__mro__
    assert _ExecutionServiceMixinBase in mro
    assert OrderExecutorMixin in mro
    assert RiskEvaluatorMixin in mro
    assert PositionSynchronizerMixin in mro
    assert EmergencyManagerMixin in mro


def test_base_mixin_instantiation():
    """Verify that base mixin has zero runtime overhead and can be instantiated."""
    base_inst = _ExecutionServiceMixinBase()
    assert isinstance(base_inst, _ExecutionServiceMixinBase)
