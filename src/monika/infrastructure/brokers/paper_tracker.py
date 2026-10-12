"""
Execution Paper Tracker Facade.
Re-exports PaperTracker from utils.analytics.paper_tracker for clean execution domain architecture.
"""
from utils.analytics.paper_tracker import (
    PaperTracker,
    _group_by_symbol,
    _group_by_symbol_direction,
)

__all__ = ["PaperTracker", "_group_by_symbol", "_group_by_symbol_direction"]
