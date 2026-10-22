"""Regression tests for session-scoped planning mechanism (Wave 3)."""

import pytest

from monika.application.planning.session_plan import SessionPlan


def test_session_plan_lifecycle():
    sp = SessionPlan.get_or_create("test_session_1", goal="Analyze EURUSD macro setup")
    assert sp.get_plan()["goal"] == "Analyze EURUSD macro setup"
    assert sp.get_plan()["status"] == "ACTIVE"

    task = sp.add_task("Check FVG zones", priority="HIGH")
    assert task["status"] == "PENDING"
    assert len(sp.get_plan()["tasks"]) == 1

    sp.update_task(0, "DONE", note="Verified H4 FVG unmitigated")
    assert sp.get_plan()["tasks"][0]["status"] == "DONE"
    assert "Verified" in sp.get_plan()["tasks"][0].get("note", "")

    summary = sp.summary_text()
    assert "Analyze EURUSD macro setup" in summary
    assert "FVG zones" in summary

    sp.clear()
    assert "test_session_1" not in SessionPlan._store


def test_session_plan_isolated_per_session():
    a = SessionPlan.get_or_create("sess_a")
    b = SessionPlan.get_or_create("sess_b", goal="Backtest strategy")
    a.add_task("Task A")
    assert len(b.get_plan()["tasks"]) == 0
    assert b.get_plan()["goal"] == "Backtest strategy"
