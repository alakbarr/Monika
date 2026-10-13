# ==============================================================================
# File: application/orchestrator/__init__.py
# ==============================================================================

"""
Application orchestrator subpackage.
Provides process bootstrapping, lifecycle, subsystem mixins, and TradingAgent.
"""

from __future__ import annotations

from monika.application.orchestrator.agent import TradingAgent
from monika.application.orchestrator.builder import AgentBuilderMixin
from monika.application.orchestrator.entrypoints import (
    BANNER,
    PID_FILE,
    _EMERGENCY_EXIT_CODE,
    _amain,
    acquire_single_instance_lock,
    main,
    release_single_instance_lock,
    run_startup_checks,
)
from monika.application.orchestrator.lifecycle import AgentLifecycleMixin
from monika.application.orchestrator.monitors import AgentMonitorsMixin
from monika.application.orchestrator.recovery import AgentRecoveryMixin

__all__ = [
    "BANNER",
    "PID_FILE",
    "_EMERGENCY_EXIT_CODE",
    "_amain",
    "acquire_single_instance_lock",
    "main",
    "release_single_instance_lock",
    "run_startup_checks",
    "TradingAgent",
    "AgentBuilderMixin",
    "AgentRecoveryMixin",
    "AgentMonitorsMixin",
    "AgentLifecycleMixin",
]
