"""
Backward-compatibility facade for ToolBatchPlanner.
Canonical location: monika.application.agent.harness.tool_batch_planner
"""

import sys
import monika.application.agent.harness.tool_batch_planner as _canonical

from monika.application.agent.harness.tool_batch_planner import ToolBatchPlanner

__all__ = ["ToolBatchPlanner"]

sys.modules[__name__] = _canonical
