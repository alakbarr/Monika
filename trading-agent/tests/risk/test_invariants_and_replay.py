"""
Unit tests for Runtime Invariants (Phase 5.6) and Keyless Session Replay (Phase 5.1).
"""

import pytest
from risk.invariants.risk_gate_invariant import (
    assert_risk_gate_invariants,
    InvariantViolationError,
)
from risk.invariants.state_immutability_invariant import (
    assert_state_immutability,
    StateFreezeGuard,
)
from tests.support.replay_provider import ReplayLLMProvider


def test_risk_gate_invariant_drawdown_ceiling():
    """Drawdown beyond ceiling must raise InvariantViolationError."""
    proposal = {"action": "buy", "entry_price": 2000.0, "stop_loss": 1990.0, "take_profit": 2020.0}
    # Pass within limit
    assert_risk_gate_invariants(proposal, current_drawdown_pct=2.5, max_drawdown_limit=3.0)

    # Fail beyond limit
    with pytest.raises(InvariantViolationError) as exc:
        assert_risk_gate_invariants(proposal, current_drawdown_pct=3.5, max_drawdown_limit=3.0)
    assert "drawdown ceiling breach" in str(exc.value).lower()


def test_risk_gate_invariant_order_geometry():
    """Geometry violations must immediately raise InvariantViolationError."""
    # Invalid BUY geometry (SL higher than entry)
    bad_buy = {"action": "buy", "entry_price": 2000.0, "stop_loss": 2010.0, "take_profit": 2030.0}
    with pytest.raises(InvariantViolationError) as exc:
        assert_risk_gate_invariants(bad_buy, current_drawdown_pct=1.0)
    assert "geometry breach for buy" in str(exc.value).lower()

    # Invalid SELL geometry (TP higher than entry)
    bad_sell = {"action": "sell", "entry_price": 2000.0, "stop_loss": 2010.0, "take_profit": 2020.0}
    with pytest.raises(InvariantViolationError) as exc:
        assert_risk_gate_invariants(bad_sell, current_drawdown_pct=1.0)
    assert "geometry breach for sell" in str(exc.value).lower()

    # Sub-par Risk:Reward ratio
    low_rr = {"action": "buy", "entry_price": 2000.0, "stop_loss": 1980.0, "take_profit": 2010.0}  # risk=20, reward=10 -> RR=0.5
    with pytest.raises(InvariantViolationError) as exc:
        assert_risk_gate_invariants(low_rr, current_drawdown_pct=1.0, min_rr_ratio=1.0)
    assert "r:r invariant breach" in str(exc.value).lower()


def test_state_immutability_guard():
    """StateFreezeGuard detects in-place mutation of protected state fields."""
    state = {
        "symbol": "XAUUSD",
        "cycle_id": "cycle-101",
        "macro_brief": "Hawkish bias",
        "local_scratchpad": "Initial notes",
    }

    # 1. Unprotected field mutation is permitted
    with StateFreezeGuard(state, protected_keys=("symbol", "cycle_id", "macro_brief")):
        state["local_scratchpad"] = "Updated notes"

    # 2. Protected field mutation must raise InvariantViolationError
    with pytest.raises(InvariantViolationError) as exc:
        with StateFreezeGuard(state, protected_keys=("symbol", "cycle_id", "macro_brief")):
            state["macro_brief"] = "Mutated illegally!"
    assert "state immutability breach" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_keyless_replay_llm_provider():
    """ReplayLLMProvider returns recorded steps sequentially without network requests."""
    provider = ReplayLLMProvider(model="mock-fast")
    provider.add_recording(content="Market structure indicates bullish expansion.")
    provider.add_recording(
        content="Submitting order...",
        tool_calls=[{"name": "submit_order", "arguments": {"symbol": "EURUSD", "action": "buy"}}]
    )

    # Step 1: Text generation
    gen_text = await provider.generate("Analyze EURUSD")
    assert "Market structure indicates bullish expansion" in gen_text

    # Step 2: Agent run with tool call
    resp = await provider.run_agent("Execute order")
    assert resp.stop_reason == "tool_use"
    assert len(resp.content) == 2
    assert resp.content[1]["name"] == "submit_order"
    assert resp.content[1]["input"] == {"symbol": "EURUSD", "action": "buy"}
