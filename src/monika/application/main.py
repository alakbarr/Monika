# ==============================================================================
# File: application/main.py
# ==============================================================================

"""
AI Trading Agent — Main Orchestrator Facade
===========================================

Backward-compatible facade for daemon runtime orchestrator, entrypoints, and subsystems.
All implementations have been refactored into `monika.application.orchestrator.*`.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import os
import signal
import sys
import types
from typing import Any, Optional

# Arm startup watchdog early before heavy application imports (skipped in test runner and child processes)
import multiprocessing

if (
    "pytest" not in sys.modules
    and "PYTEST_CURRENT_TEST" not in os.environ
    and multiprocessing.current_process().name == "MainProcess"
    and not any("--multiprocessing" in arg for arg in sys.argv)
):
    from monika.application.agent.monitors.startup_watchdog import arm_startup_watchdog

    arm_startup_watchdog(timeout_s=180.0)

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment Variable Security Fence (Phase 6.3)
# Protect host bootstrap variables against project-level .env hijacking
# ---------------------------------------------------------------------------
FORBIDDEN_ENV_OVERRIDES = {"PATH", "PYTHONPATH", "SYSTEMROOT", "COMSPEC"}
_initial_host_env = {k: os.environ[k] for k in FORBIDDEN_ENV_OVERRIDES if k in os.environ}

load_dotenv(override=False)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=False)

for _fence_key, _fence_val in _initial_host_env.items():
    if os.environ.get(_fence_key) != _fence_val:
        os.environ[_fence_key] = _fence_val

# ---------------------------------------------------------------------------
# Bootstrap application runtime hardening
# ---------------------------------------------------------------------------
from monika.application.bootstrap import bootstrap_runtime

bootstrap_runtime()

# ---------------------------------------------------------------------------
# Bootstrap logging immediately
# ---------------------------------------------------------------------------
from monika.core.telemetry.activity_logger import setup_logging

setup_logging(log_dir="logs", level=logging.INFO)
logger = logging.getLogger("TradingAgent.Main")

# ---------------------------------------------------------------------------
# Common re-exports
# ---------------------------------------------------------------------------
from monika.application.agent.task_registry import (
    CLEAN_SHUTDOWN_FLAG,
    CORE_TRADING_TASKS,
    LONG_RETRY_ERRORS,
    PERMANENT_ERRORS,
    TaskDefinition,
    TaskRegistry,
    _run_with_restart,
    _safe_notify_critical,
    _safe_notify_warning,
    get_emergency_exit_code,
    mark_clean_shutdown,
    set_emergency_exit_code,
)
from monika.core.config.settings import load_all_config, load_settings
from monika.core.telemetry.activity_logger import ActivityLogger
from monika.infrastructure.database.db import close_db, init_db

# ---------------------------------------------------------------------------
# Modular orchestrator components
# ---------------------------------------------------------------------------
import monika.application.orchestrator as _orchestrator_pkg
from monika.application.orchestrator import (
    BANNER,
    PID_FILE,
    _EMERGENCY_EXIT_CODE,
    AgentBuilderMixin,
    AgentLifecycleMixin,
    AgentMonitorsMixin,
    AgentRecoveryMixin,
    TradingAgent,
    _amain,
    acquire_single_instance_lock,
    agent as _agent_mod,
    builder as _builder_mod,
    entrypoints as _entrypoints_mod,
    lifecycle as _lifecycle_mod,
    main,
    monitors as _monitors_mod,
    recovery as _recovery_mod,
    release_single_instance_lock,
    run_startup_checks,
)

__all__ = [
    "BANNER",
    "PID_FILE",
    "_EMERGENCY_EXIT_CODE",
    "_amain",
    "_run_with_restart",
    "acquire_single_instance_lock",
    "main",
    "release_single_instance_lock",
    "run_startup_checks",
    "TradingAgent",
    "AgentBuilderMixin",
    "AgentRecoveryMixin",
    "AgentMonitorsMixin",
    "AgentLifecycleMixin",
    "close_db",
    "init_db",
    "load_all_config",
    "load_settings",
    "ActivityLogger",
    "CLEAN_SHUTDOWN_FLAG",
    "CORE_TRADING_TASKS",
    "LONG_RETRY_ERRORS",
    "PERMANENT_ERRORS",
    "TaskDefinition",
    "TaskRegistry",
]


class _ApplicationMainFacadeModule(types.ModuleType):
    """Module proxy forwarding attribute mutations to submodules for transparent monkeypatching."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        for submodule in (
            _orchestrator_pkg,
            _agent_mod,
            _builder_mod,
            _recovery_mod,
            _monitors_mod,
            _lifecycle_mod,
            _entrypoints_mod,
        ):
            if hasattr(submodule, name):
                setattr(submodule, name, value)


_current_mod = sys.modules[__name__]
_proxy_mod = _ApplicationMainFacadeModule(__name__, __doc__)
_proxy_mod.__dict__.update(_current_mod.__dict__)
sys.modules[__name__] = _proxy_mod

if __name__ == "__main__":
    main()
