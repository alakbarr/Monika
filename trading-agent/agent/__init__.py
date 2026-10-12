"""Backward compatibility package for monika.application.agent."""
from agent.startup_checks import StartupChecker, run_startup_checks
from agent.task_registry import TaskDefinition, TaskRegistry, CORE_TRADING_TASKS, _run_with_restart

__all__ = [
    "StartupChecker",
    "run_startup_checks",
    "TaskDefinition",
    "TaskRegistry",
    "CORE_TRADING_TASKS",
    "_run_with_restart",
]
