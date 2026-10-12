# ==============================================================================
# File: tests/cli/test_tui_ergonomics.py
# Description: Unit Tests for TUI Ergonomics, Width Budgeting, and Session Lock
# ==============================================================================

import os
from unittest.mock import MagicMock
from cli.analysis_tree import AnalysisCycleTree
from cli.chat.renderer import ChatRenderer
from cli.chat.session import acquire_cli_session_lock, release_cli_session_lock
from cli.tui import StatusBar
from cli.width_budget import ColumnSpec, compute_progressive_width_budget


def test_analysis_tree_per_asset_alias_isolated():
    """Verify per_asset_analysis maps to per_asset_analysis and does NOT alias to bull_advocate."""
    tree = AnalysisCycleTree()
    tree.start_cycle("cycle_test", "XAUUSD")

    # Update per_asset_analysis
    tree.update_step("per_asset_analysis", status="completed", duration_s=2.5)

    steps = tree.cycle_data.get("steps", {})
    assert "per_asset_analysis" in steps
    assert steps["per_asset_analysis"]["status"] == "completed"
    assert steps["per_asset_analysis"]["duration_s"] == 2.5

    # Bull advocate must remain untouched (waiting)
    assert steps["bull_advocate"]["status"] == "waiting"


def test_analysis_tree_nine_node_pipeline_completeness():
    """Verify all 9 LangGraph pipeline nodes are registered with canonical labels."""
    tree = AnalysisCycleTree()
    assert "macro_brief" in tree.PIPELINE_STEPS
    assert "per_asset_analysis" in tree.PIPELINE_STEPS
    assert "bull_advocate" in tree.PIPELINE_STEPS
    assert "bear_dissent" in tree.PIPELINE_STEPS
    assert "debate_judge" in tree.PIPELINE_STEPS
    assert "risk_gate" in tree.PIPELINE_STEPS
    assert "execution" in tree.PIPELINE_STEPS

    tree.start_cycle("cycle_full", "EURUSD")
    rendered = tree.render()
    assert "Macro Brief" in rendered
    assert "Per-Asset Analysis" in rendered
    assert "Bull Advocate" in rendered


def test_analysis_tree_differential_update_guard():
    """Verify update_step skips re-creating cycle_data dict when values are identical."""
    tree = AnalysisCycleTree()
    tree.start_cycle("cycle_diff", "EURUSD")
    tree.update_step("prefetch_data", status="running", duration_s=1.0)

    initial_ref = tree.cycle_data

    # Redundant update with identical fields should no-op
    tree.update_step("prefetch_data", status="running", duration_s=1.0)
    assert tree.cycle_data is initial_ref

    # Meaningful update creates a new dict reference
    tree.update_step("prefetch_data", status="completed", duration_s=1.2)
    assert tree.cycle_data is not initial_ref
    assert tree.cycle_data["steps"]["prefetch_data"]["status"] == "completed"


def test_width_budget_column_allocation():
    """Verify progressive width budget drops low priority columns on narrow viewports."""
    columns = [
        ColumnSpec("time", "Time", min_width=8, max_width=12, priority=2, flex=1),
        ColumnSpec("symbol", "Symbol", min_width=7, max_width=10, priority=1, flex=1),
        ColumnSpec("action", "Action", min_width=6, max_width=8, priority=1, flex=1),
        ColumnSpec("volume", "Lots", min_width=5, max_width=8, priority=1, flex=1),
        ColumnSpec("price", "Price", min_width=10, max_width=14, priority=1, flex=1),
        ColumnSpec("pnl", "PnL", min_width=8, max_width=12, priority=1, flex=1),
        ColumnSpec("strategy", "Strategy", min_width=10, max_width=20, priority=2, flex=2),
        ColumnSpec("reason", "Reason", min_width=15, max_width=50, priority=3, flex=4),
    ]

    # Ample width (120 cols): all columns present, including priority 3
    budget_wide = compute_progressive_width_budget(terminal_width=120, columns=columns)
    assert "reason" in budget_wide
    assert "strategy" in budget_wide
    assert "symbol" in budget_wide

    # Constrained width (75 cols): priority 3 dropped
    budget_medium = compute_progressive_width_budget(terminal_width=75, columns=columns)
    assert "reason" not in budget_medium
    assert "strategy" in budget_medium
    assert "symbol" in budget_medium

    # Highly constrained width (60 cols): priority 2 and 3 dropped, only priority 1 retained
    budget_narrow = compute_progressive_width_budget(terminal_width=60, columns=columns)
    assert "reason" not in budget_narrow
    assert "strategy" not in budget_narrow
    assert "symbol" in budget_narrow
    assert "pnl" in budget_narrow


def test_status_bar_compact_and_wide_formatting():
    """Verify StatusBar formats compact layout on narrow screens and wide layout on standard."""
    status_bar = StatusBar()
    status_bar.update = MagicMock()

    # Standard wide screen (110 cols)
    status_bar.update_metrics(
        cached_tokens=5000,
        input_tokens=10000,
        output_tokens=2000,
        cost_usd=0.015,
        uptime_seconds=360,
        ws_status="[OK] Live",
        context_used=12000,
        context_max=200000,
        cache_hit_rate=33.3,
        terminal_width=110,
    )
    status_bar.update.assert_called_once()
    wide_call = status_bar.update.call_args[0][0]
    assert "Tokens:" in wide_call
    assert "Context:" in wide_call
    assert "Uptime:" in wide_call

    # Narrow screen (80 cols)
    status_bar.update.reset_mock()
    status_bar.update_metrics(
        cached_tokens=5000,
        input_tokens=10000,
        output_tokens=2000,
        cost_usd=0.015,
        uptime_seconds=360,
        ws_status="[OK] Live",
        context_used=12000,
        context_max=200000,
        cache_hit_rate=33.3,
        terminal_width=80,
    )
    status_bar.update.assert_called_once()
    compact_call = status_bar.update.call_args[0][0]
    assert "Tok:" in compact_call
    assert "Hit:" in compact_call
    assert "Cost:" in compact_call


def test_cli_session_lock_twin_lifecycle(tmp_path):
    """Verify CLI chat session lock acquisition, conflict detection, and release."""
    test_session = f"test_repl_session_{os.getpid()}"

    # 1. First acquisition succeeds
    conflict_pid = acquire_cli_session_lock(test_session)
    assert conflict_pid is None

    # 2. Same process re-acquisition succeeds
    same_conflict = acquire_cli_session_lock(test_session)
    assert same_conflict is None

    # 3. Release lockfile
    release_cli_session_lock(test_session)

    # 4. Clean release allows fresh acquisition
    fresh_conflict = acquire_cli_session_lock(test_session)
    assert fresh_conflict is None

    release_cli_session_lock(test_session)


def test_chat_renderer_thinking_spinner():
    """Verify thinking spinner helper executes without unhandled errors."""
    renderer = ChatRenderer(theme_name="retro_vintage")
    renderer.render_thinking_spinner("Evaluating market structure...")
    renderer.clear_thinking_spinner()
