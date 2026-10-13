"""
Package: agent
Decomposed agent core modules: startup checks, task registry, and background monitors.
"""

try:
    from monika.application.agent.startup_checks import StartupChecker, run_startup_checks
    from monika.application.agent.task_registry import (
        TaskDefinition,
        TaskRegistry,
        CORE_TRADING_TASKS,
        _run_with_restart,
    )
except ImportError:
    from monika.application.agent.startup_checks import StartupChecker, run_startup_checks
    from monika.application.agent.task_registry import (
        TaskDefinition,
        TaskRegistry,
        CORE_TRADING_TASKS,
        _run_with_restart,
    )

__all__ = [
    "StartupChecker",
    "run_startup_checks",
    "TaskDefinition",
    "TaskRegistry",
    "CORE_TRADING_TASKS",
    "_run_with_restart",
]
