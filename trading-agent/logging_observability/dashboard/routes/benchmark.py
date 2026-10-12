"""
Compatibility facade shim for legacy benchmark.py.
Re-exports from canonical monika.interfaces.dashboard.routes.benchmark.
"""

from __future__ import annotations

import monika.interfaces.dashboard.routes.benchmark as _canonical

from monika.interfaces.dashboard.routes.benchmark import (
    BenchmarkRunRequest,
    benchmark_router,
    compare_task_benchmarks,
    get_benchmark_leaderboard,
    get_benchmark_quadrant_chart_data,
    get_benchmark_run_detail,
    list_benchmark_models,
    list_benchmark_runs,
    list_benchmark_tasks,
    logger,
    trigger_benchmark_run,
)

__all__ = ['BenchmarkRunRequest', 'benchmark_router', 'compare_task_benchmarks', 'get_benchmark_leaderboard', 'get_benchmark_quadrant_chart_data', 'get_benchmark_run_detail', 'list_benchmark_models', 'list_benchmark_runs', 'list_benchmark_tasks', 'logger', 'trigger_benchmark_run']


# Direct module reference forwarding
for _attr in dir(_canonical):
    if not _attr.startswith('__') and _attr not in globals():
        globals()[_attr] = getattr(_canonical, _attr)

import sys as _sys
_sys.modules[__name__] = _canonical
