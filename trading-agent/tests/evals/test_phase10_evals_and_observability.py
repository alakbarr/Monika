# ==============================================================================
# File: tests/evals/test_phase10_evals_and_observability.py
# ==============================================================================

import asyncio
import time
import pytest
from pathlib import Path

from evals.hostile_market_probe import HostileMarketProbe, HostileTickScenario
from logging_observability.dashboard.pty_bridge import PtyBridgeManager, PtySession
from cli.width_budget import compute_progressive_width_budget, ColumnSpec


def test_hostile_market_probe_generation_and_resilience():
    probe = HostileMarketProbe(reference_price=1.0850, symbol="EURUSD")
    battery = probe.generate_battery()
    assert len(battery) >= 5

    # Mock RiskGate pre-trade validator
    def mock_risk_gate(payload):
        # Reject crossed book or zero price
        if payload["bid"] <= 0 or payload["ask"] <= 0:
            return False, "Price non-positive"
        if payload["bid"] >= payload["ask"]:
            return False, "Crossed book detected"
        # Reject extreme spreads > 5.0 pips
        if payload["spread_pips"] > 5.0:
            return False, "Spread blowout"
        # Reject flash crash / price plunge > 5%
        if abs(payload["bid"] - 1.0850) / 1.0850 > 0.05:
            return False, "Flash crash price discrepancy"
        # Reject stale feed > 300s
        if time.time() - payload["timestamp"] > 300.0:
            return False, "Stale feed"
        return True, "Permitted"

    res = probe.verify_resilience(mock_risk_gate)
    assert res["all_resilient"] is True
    assert res["passed_count"] == len(battery)


@pytest.mark.asyncio
async def test_pty_bridge_session_and_ansi_responder():
    bridge = PtyBridgeManager(default_idle_timeout_sec=1.0)
    session = await bridge.create_session("term_test_1")

    # Write output containing VT100 cursor query (ESC [ 6 n)
    responses = session.append_output("Loading dashboard...\x1b[6n")
    # PtyQueryResponder should have synthesized response
    assert len(responses) == 1
    assert responses[0] == b"\x1b[1;1R"

    # Drain output
    drained = session.drain_output()
    assert "Loading dashboard" in drained
    # Buffer is now empty
    assert session.drain_output() == ""

    # Test idle reap
    session.last_active = time.time() - 5.0
    reaped = await bridge.reap_stale_sessions(max_idle_sec=2.0)
    assert reaped == 1
    assert await bridge.get_session("term_test_1") is None


def test_progressive_width_budget_allocator():
    # 1. Narrow terminal (60 cols): only essential priority 1 columns
    narrow = compute_progressive_width_budget(terminal_width=60)
    assert "symbol" in narrow
    assert "action" in narrow
    assert "pnl" in narrow
    assert "reason" not in narrow  # Dropped due to priority 3

    # 2. Wide terminal (150 cols): all columns present with expanded reason budget
    wide = compute_progressive_width_budget(terminal_width=150)
    assert "reason" in wide
    assert wide["reason"] > narrow.get("reason", 0)
    assert "strategy" in wide
