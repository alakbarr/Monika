# ==============================================================================
# File: tests/graph/test_debate_convergence.py
# ==============================================================================

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from graph.state import TradingState
from graph.nodes.debate.subgraph import build_debate_subgraph
from graph.nodes.debate.round_robin_risk_nodes import (
    conservative_risk_node,
    aggressive_risk_node,
    neutral_risk_node,
    portfolio_judge_node,
)


@pytest.mark.asyncio
async def test_debate_subgraph_nodes_presence():
    """Verify that the debate subgraph compiles with all cyclic and round-robin nodes."""
    subgraph = build_debate_subgraph()
    assert subgraph is not None
    node_keys = list(subgraph.nodes.keys())
    assert "bull_advocate" in node_keys
    assert "bear_dissent" in node_keys
    assert "rebuttal" in node_keys
    assert "debate_judge" in node_keys
    assert "conservative_risk" in node_keys
    assert "aggressive_risk" in node_keys
    assert "neutral_risk" in node_keys
    assert "portfolio_judge" in node_keys
    # Legacy monolithic risk_evaluator deliberately NOT in round-robin subgraph (CRITICAL-02);
    # it remains available via the debate_node facade.
    assert "risk_evaluator" not in node_keys


@pytest.mark.asyncio
async def test_debate_convergence_conditions():
    """Verify should_continue_debate logic: divergence > 0.40 & turn < 3."""
    from graph.nodes.debate.subgraph import should_continue_debate

    # Case 1: High divergence, turn 1 -> needs rebuttal
    state_divergent = {
        "actionable_trades": [("EURUSD", {"analysis_id": 1})],
        "debate_states": {
            "EURUSD": {"turn": 1, "divergence": 0.55, "disagreement": 6, "needs_rebuttal": True}
        }
    }
    decision = should_continue_debate(state_divergent)
    assert decision == "rebuttal"

    # Case 2: Low divergence (converged <= 0.40) -> goes to judge
    state_converged = {
        "actionable_trades": [("EURUSD", {"analysis_id": 1})],
        "debate_states": {
            "EURUSD": {"turn": 2, "divergence": 0.20, "disagreement": 2, "needs_rebuttal": False}
        }
    }
    decision = should_continue_debate(state_converged)
    assert decision == "debate_judge"

    # Case 3: Turn >= 3 (max rounds reached) -> goes to judge even if divergence high
    state_max_turns = {
        "actionable_trades": [("EURUSD", {"analysis_id": 1})],
        "debate_states": {
            "EURUSD": {"turn": 3, "divergence": 0.60, "disagreement": 6, "needs_rebuttal": True}
        }
    }
    decision = should_continue_debate(state_max_turns)
    assert decision == "debate_judge"


@pytest.mark.asyncio
async def test_round_robin_risk_consensus_chain():
    """Verify the sequential information flow: Conservative -> Aggressive -> Neutral -> Portfolio Judge."""
    mock_ana = MagicMock()
    mock_ana.decision = "BUY"
    mock_ana.confluence_score = 9
    mock_ana.priced_in_score = 3
    mock_ana.stop_loss = 1.0800
    mock_ana.take_profit = 1.0950
    mock_ana.price_at_analysis = 1.0850
    mock_ana.entry_zone = '{"price": 1.0850}'
    mock_ana.rationale = "Strong confluence setup"
    mock_ana.risk_multiplier = 1.0
    mock_ana.context_snapshot_id = "test_snapshot"

    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass
        async def get(self, model, pk):
            return mock_ana
        async def execute(self, *a, **kw):
            m = MagicMock()
            m.scalars.return_value.all.return_value = []
            m.scalar_one_or_none.return_value = None
            return m
        async def commit(self):
            pass

    state = {
        "actionable_trades": [("EURUSD", {"analysis_id": 101, "decision": "buy"})],
        "debate_states": {"EURUSD": {"fact_sheet": {"symbol": "EURUSD", "atr": 0.0050}}},
        "investment_verdicts": {"EURUSD": {"final_decision": "approve", "risk_multiplier": 1.0}},
        "risk_debate_states": {},
        "portfolio_decisions": {},
    }
    config = {
        "configurable": {
            "scheduler": MagicMock(
                settings={"agent_architecture": {"enable_debate": True, "deterministic_risk_gate": True}}
            )
        }
    }

    with patch("graph.nodes.debate.round_robin_risk_nodes.get_session", side_effect=MockSession), \
         patch("graph.nodes.debate.round_robin_risk_nodes.compute_actual_risk_state", AsyncMock(return_value={"current_drawdown_pct": 0.2})):

        # Turn 1: Conservative
        res_cons = await conservative_risk_node(state, config=config)
        state["risk_debate_states"].update(res_cons["risk_debate_states"])
        assert "conservative" in state["risk_debate_states"]["EURUSD"]

        # Turn 2: Aggressive receives Conservative concerns
        res_agg = await aggressive_risk_node(state, config=config)
        state["risk_debate_states"].update(res_agg["risk_debate_states"])
        assert "aggressive" in state["risk_debate_states"]["EURUSD"]

        # Turn 3: Neutral receives both Conservative and Aggressive assessments
        res_neu = await neutral_risk_node(state, config=config)
        state["risk_debate_states"].update(res_neu["risk_debate_states"])
        assert "neutral" in state["risk_debate_states"]["EURUSD"]

        # Turn 4: Portfolio Judge resolves consensus
        res_pm = await portfolio_judge_node(state, config=config)
        assert "portfolio_decisions" in res_pm
        assert "EURUSD" in res_pm["portfolio_decisions"]
        assert len(res_pm["actionable_trades"]) == 1
