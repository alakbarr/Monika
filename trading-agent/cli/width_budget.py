# ==============================================================================
# File: cli/width_budget.py
# ==============================================================================

"""
Progressive Terminal Width Budgeting & Adaptive Column Allocator.
Institutional-grade CLI layout and responsive terminal rendering.

Dynamically partitions terminal character width across data table columns,
progress indicators, and log sidebars:
  - Preserves critical high-priority columns (Symbol, Action, Lots, PnL)
  - Expands fluid narrative columns (Reason, Strategy, Notes) when width is ample (120+ cols)
  - Drops low-priority decorative columns on narrow displays (< 80 cols)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ColumnSpec:
    id: str
    title: str
    min_width: int
    max_width: int
    priority: int = 1  # 1 = Essential (never drop), 2 = Normal, 3 = Low (drop if narrow)
    flex: int = 1      # Relative weight for distributing extra width


def compute_progressive_width_budget(
    terminal_width: Optional[int] = None,
    columns: Optional[List[ColumnSpec]] = None,
    padding_per_col: int = 2,
) -> Dict[str, int]:
    """
    Computes exact character width allocations for each column based on available terminal width.
    """
    width = terminal_width or shutil.get_terminal_size((100, 24)).columns
    specs = columns or [
        ColumnSpec("time", "Time", min_width=8, max_width=12, priority=2, flex=1),
        ColumnSpec("symbol", "Symbol", min_width=7, max_width=10, priority=1, flex=1),
        ColumnSpec("action", "Action", min_width=6, max_width=8, priority=1, flex=1),
        ColumnSpec("volume", "Lots", min_width=5, max_width=8, priority=1, flex=1),
        ColumnSpec("price", "Entry/Curr", min_width=12, max_width=16, priority=1, flex=1),
        ColumnSpec("pnl", "PnL ($)", min_width=8, max_width=12, priority=1, flex=1),
        ColumnSpec("strategy", "Strategy", min_width=12, max_width=24, priority=2, flex=2),
        ColumnSpec("reason", "Thesis/Reason", min_width=15, max_width=60, priority=3, flex=4),
    ]

    # Step 1: Filter out priority 3 columns if terminal is narrow (< 85 cols)
    active_specs = list(specs)
    if width < 85:
        active_specs = [s for s in active_specs if s.priority <= 2]
    if width < 65:
        active_specs = [s for s in active_specs if s.priority <= 1]

    n_cols = len(active_specs)
    total_padding = n_cols * padding_per_col
    available = max(20, width - total_padding)

    # Step 2: Allocate minimum widths
    allocations = {s.id: s.min_width for s in active_specs}
    allocated_sum = sum(allocations.values())

    remaining = available - allocated_sum
    if remaining <= 0:
        return allocations

    # Step 3: Distribute extra width according to flex factor up to max_width
    total_flex = sum(s.flex for s in active_specs)
    if total_flex <= 0:
        total_flex = 1

    for s in active_specs:
        extra = int(remaining * (s.flex / total_flex))
        new_width = min(s.max_width, allocations[s.id] + extra)
        allocations[s.id] = new_width

    return allocations
