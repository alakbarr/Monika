"""
Backward-compatibility facade for SymbolSegmentPlanner.
Canonical location: monika.application.agent.harness.symbol_segment_planner
"""

import sys
import monika.application.agent.harness.symbol_segment_planner as _canonical

from monika.application.agent.harness.symbol_segment_planner import SymbolSegmentPlanner

__all__ = ["SymbolSegmentPlanner"]

sys.modules[__name__] = _canonical
