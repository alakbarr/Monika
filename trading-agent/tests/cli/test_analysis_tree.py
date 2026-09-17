# ==============================================================================
# File: tests/cli/test_analysis_tree.py
# Description: Unit Tests for AnalysisCycleTree Widget
# ==============================================================================

import pytest
from cli.analysis_tree import AnalysisCycleTree


def test_analysis_cycle_tree_init():
    """Initial state without cycle data renders standby text."""
    tree = AnalysisCycleTree()
    rendered = tree.render()
    assert "No active analysis cycle" in rendered


def test_analysis_cycle_tree_lifecycle():
    """Verify start_cycle, update_step, and complete_cycle state transitions."""
    tree = AnalysisCycleTree()

    # 1. Start cycle
    tree.start_cycle("cycle_101", "EURUSD")
    assert tree.cycle_data["id"] == "cycle_101"
    assert tree.cycle_data["symbol"] == "EURUSD"

    rendered = tree.render()
    assert "cycle_101" in rendered
    assert "EURUSD" in rendered
    assert "Fundamental Brief" in rendered

    # 2. Update step
    tree.update_step(
        "fundamental_brief",
        status="completed",
        duration_s=1.5,
        input_tokens=1500,
        output_tokens=300,
        token_history=[100, 200, 300],
    )
    step_data = tree.cycle_data["steps"]["fundamental_brief"]
    assert step_data["status"] == "completed"
    assert step_data["duration_s"] == 1.5
    assert step_data["input_tokens"] == 1500

    rendered_updated = tree.render()
    assert "1.5s" in rendered_updated

    # 3. Complete cycle (Q2: archived to history, max 3)
    tree.complete_cycle(decision="BUY 0.10 lots")
    assert tree.cycle_data == {}
    assert len(tree.history_cycles) == 1
    assert tree.history_cycles[0]["id"] == "cycle_101"
    assert tree.history_cycles[0]["decision"] == "BUY 0.10 lots"

    # History rendered
    rendered_history = tree.render()
    assert "Historical Execution Cycles" in rendered_history
    assert "cycle_101" in rendered_history
    assert "BUY 0.10 lots" in rendered_history


def test_analysis_cycle_tree_history_max_three():
    """History maintains only the last 3 completed cycles (Q2)."""
    tree = AnalysisCycleTree()
    for i in range(5):
        tree.start_cycle(f"c_{i}", f"SYM_{i}")
        tree.complete_cycle(decision=f"DECISION_{i}")

    assert len(tree.history_cycles) == 3
    # Most recent first
    assert tree.history_cycles[0]["id"] == "c_4"
    assert tree.history_cycles[1]["id"] == "c_3"
    assert tree.history_cycles[2]["id"] == "c_2"


def test_analysis_cycle_tree_history_toggle_expand():
    """Expanding history item shows step-level details."""
    tree = AnalysisCycleTree()
    tree.start_cycle("c_exp", "GBPUSD")
    tree.update_step("bull_advocate", status="completed", duration_s=2.4)
    tree.complete_cycle(decision="BUY")

    # Initially collapsed
    assert tree.expanded_cycle_id is None
    collapsed_text = tree.render()
    assert "bull_advocate (2.4s)" not in collapsed_text

    # Expand
    tree.toggle_history_expand("c_exp")
    assert tree.expanded_cycle_id == "c_exp"
    expanded_text = tree.render()
    assert "bull_advocate (2.4s)" in expanded_text

    # Collapse
    tree.toggle_history_expand("c_exp")
    assert tree.expanded_cycle_id is None


def test_analysis_cycle_tree_step_aliases():
    """Verify LangGraph stage node names map correctly to canonical pipeline steps."""
    tree = AnalysisCycleTree()
    tree.start_cycle("cycle_alias", "BTCUSD")

    # Pass LangGraph node names
    tree.update_step("fundamental_analysis", status="completed", duration_s=3.2)
    tree.update_step("data_gathering", status="completed", duration_s=1.1)

    steps = tree.cycle_data["steps"]
    assert steps["fundamental_brief"]["status"] == "completed"
    assert steps["fundamental_brief"]["duration_s"] == 3.2
    assert steps["prefetch_data"]["status"] == "completed"
    assert steps["prefetch_data"]["duration_s"] == 1.1
