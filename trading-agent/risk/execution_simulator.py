# ==============================================================================
# File: risk/execution_simulator.py
# Description: Backward-compatibility shim for monika.domain.risk.execution_simulator
# ==============================================================================

"""
Backward-compatibility shim.
Canonical implementation: monika.domain.risk.execution_simulator
"""

import sys
import monika.domain.risk.execution_simulator as _canonical

from monika.domain.risk.execution_simulator import (
    ExecutionSimulationResult,
    ExecutionSimulator,
    PriceOHLCV,
    SlippageScenario,
    logger,
)

sys.modules[__name__] = _canonical

__all__ = [
    "ExecutionSimulationResult",
    "ExecutionSimulator",
    "PriceOHLCV",
    "SlippageScenario",
    "logger",
]
