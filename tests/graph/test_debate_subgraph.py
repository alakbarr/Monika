# ==============================================================================
# File: tests/graph/test_debate_subgraph.py
# ==============================================================================

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from graph.state import TradingState
from graph.nodes.debate import (
    bull_advocate_node,
    bear_dissent_node,
    rebuttal_node,
    debate_judge_node,
    risk_evaluator_node,
    build_debate_subgraph,
)
from graph.nodes.debate.helpers import (
    _apply_deterministic_risk_clamp,
    _is_grounded,
)


@pytest.mark.asyncio
async def test_debate_subgraph_compilation():
    """Verify that the debate subgraph compiles with all decomposed nodes and edges."""
    subgraph = build_debate_subgraph()
    assert subgraph is not None
    node_keys = list(subgraph.nodes.keys())
    assert "bull_advocate" in node_keys
    assert "bear_dissent" in node_keys
    assert "rebuttal" in node_keys
    assert "debate_judge" in node_keys
    # Legacy monolithic risk_evaluator deliberately NOT in round-robin subgraph (CRITICAL-02);
    # it remains available via the debate_node facade.
    assert "risk_evaluator" not in node_keys


@pytest.mark.asyncio
async def test_debate_subgraph_empty_actionable():
    """Verify that the debate subgraph safely terminates when no actionable trades are present."""
    subgraph = build_debate_subgraph()
    state = {
        "symbols": ["EURUSD"],
        "actionable_trades": [],
        "debate_states": {},
        "risk_debate_states": {},
        "investment_verdicts": {},
        "portfolio_decisions": {},
        "summary": {},
    }
    config = {"configurable": {"scheduler": MagicMock(settings={"agent_architecture": {"enable_debate": True}})}}
    res = await subgraph.ainvoke(state, config)
    assert res.get("actionable_trades") == []


@pytest.mark.asyncio
async def test_sub_agent_nodes_modular_execution():
    """Verify each sub-agent node can execute in isolation and update state as expected."""
    # 1. Bull Advocate
    state = {
        "actionable_trades": [("EURUSD", {"analysis_id": 101, "decision": "buy", "confidence": 0.8})],
        "debate_states": {},
        "user_market_intel": [],
    }
    config = {
        "configurable": {
            "scheduler": MagicMock(
                settings={"agent_architecture": {"enable_debate": True, "debate_rounds": 2}}
            )
        }
    }

    mock_analysis = MagicMock()
    mock_analysis.rationale = "Strong SMC setup at OTE zone 1.0850"
    mock_analysis.decision = "BUY"
    mock_analysis.confluence_score = 10
    mock_analysis.confluence_factors_json = '["fvg", "ob"]'
    mock_analysis.entry_zone = '{"price": 1.0850}'
    mock_analysis.stop_loss = 1.0800
    mock_analysis.take_profit = 1.0950
    mock_analysis.invalidation = "1.0790"
    mock_analysis.price_at_analysis = 1.0850
    mock_analysis.risk_multiplier = 1.0

    class MockSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            pass
        async def get(self, *a):
            return mock_analysis
        async def execute(self, *a, **kw):
            m = MagicMock()
            m.scalars.return_value.all.return_value = []
            m.scalar_one_or_none.return_value = None
            return m
        async def commit(self):
            pass

    with patch("graph.nodes.debate.bull_advocate_node.get_session", side_effect=MockSession), \
         patch("graph.nodes.debate.bull_advocate_node.build_fact_sheet", return_value={"symbol": "EURUSD", "atr": 0.0050}), \
         patch("graph.nodes.debate.bull_advocate_node.generate_bull_advocacy", return_value={"thesis": "bull entry at 1.0850 target 1.0950", "strength_score": 9}):
        res_bull = await bull_advocate_node(state, config)
        assert "EURUSD" in res_bull["debate_states"]
        assert res_bull["debate_states"]["EURUSD"]["verified_bull_claim"]["strength_score"] == 9

    # 2. Bear Dissent with high disagreement (triggers rebuttal needed)
    state["debate_states"] = res_bull["debate_states"]
    with patch("graph.nodes.debate.bear_dissent_node.generate_bear_dissent", return_value={"dissent": "liquidity grab at 1.0850", "risk_severity": 9}):
        res_bear = await bear_dissent_node(state, config)
        deb = res_bear["debate_states"]["EURUSD"]
        assert deb["bear_dissent"]["risk_severity"] == 9
        # bull=9, bear=9 -> disagreement = abs(9 - (10 - 9)) = abs(9 - 1) = 8 >= 4
        assert deb["needs_rebuttal"] is True

    # 3. Rebuttal Node
    state["debate_states"] = res_bear["debate_states"]
    with patch("graph.nodes.debate.rebuttal_node.generate_bull_rebuttal", return_value={"rebuttal": "retested level 1.0850", "rebuttal_strength": 8}):
        res_reb = await rebuttal_node(state, config)
        assert res_reb["debate_states"]["EURUSD"]["bull_rebuttal"]["rebuttal_strength"] == 8

    # 4. Debate Judge Node (Approves)
    state["debate_states"] = res_reb["debate_states"]
    with patch("graph.nodes.debate.debate_judge_node.get_session", side_effect=MockSession), \
         patch("graph.nodes.debate.debate_judge_node.evaluate_debate", return_value={"final_decision": "buy", "reason": "strong confluence", "risk_multiplier": 1.2}), \
         patch("graph.nodes.debate.debate_judge_node.validate_and_apply_judge_adjustments", return_value=(True, None)):
        res_judge = await debate_judge_node(state, config)
        assert len(res_judge["actionable_trades"]) == 1
        assert res_judge["investment_verdicts"]["EURUSD"]["final_decision"] == "buy"

    # 5. Risk Evaluator Node (Applies clamp and approves)
    state["actionable_trades"] = res_judge["actionable_trades"]
    state["investment_verdicts"] = res_judge["investment_verdicts"]
    with patch("graph.nodes.debate.risk_evaluator_node.get_session", side_effect=MockSession), \
         patch("graph.nodes.debate.risk_evaluator_node.compute_actual_risk_state", return_value={"daily_pnl_pct": 0.5, "portfolio_heat_pct": 1.0, "risk_budget_remaining_pct": 95.0}), \
         patch("graph.nodes.debate.risk_evaluator_node.analyze_risk_conservative", return_value={"veto_trade": False}), \
         patch("graph.nodes.debate.risk_evaluator_node.analyze_risk_aggressive", return_value={"veto_trade": False}), \
         patch("graph.nodes.debate.risk_evaluator_node.analyze_risk_neutral", return_value={"veto_trade": False}), \
         patch("graph.nodes.debate.risk_evaluator_node.make_portfolio_decision_deterministic", return_value={"approval": True, "recommended_risk_multiplier": 1.0}):
        res_risk = await risk_evaluator_node(state, config)
        assert len(res_risk["actionable_trades"]) == 1
        assert res_risk["summary"]["debate_approved"] == ["EURUSD"]


def test_deterministic_risk_clamp_edge_cases():
    """Verify deterministic risk clamp behavior across extreme conditions."""
    # 3/3 Veto -> total reject (multiplier 0.0, approval False)
    pm_dec = {"approval": True, "recommended_risk_multiplier": 1.2}
    stances = {
        "conservative": {"veto_trade": True},
        "aggressive": {"veto_trade": True},
        "neutral": {"veto_trade": True},
    }
    res = _apply_deterministic_risk_clamp(pm_dec, stances, None)
    assert res["approval"] is False
    assert res["recommended_risk_multiplier"] == 0.0

    # 1/3 Veto -> dampened multiplier (capped at 0.75)
    pm_dec2 = {"approval": True, "recommended_risk_multiplier": 1.5}
    stances2 = {
        "conservative": {"veto_trade": True},
        "aggressive": {"veto_trade": False},
        "neutral": {"veto_trade": False},
    }
    res2 = _apply_deterministic_risk_clamp(pm_dec2, stances2, None)
    assert res2["approval"] is True
    assert res2["recommended_risk_multiplier"] <= 0.75

    # Daily PnL < -2.0% -> capped at 0.5
    pm_dec3 = {"approval": True, "recommended_risk_multiplier": 1.0}
    stances3 = {"conservative": {}, "aggressive": {}, "neutral": {}}
    actual_risk = {"daily_pnl_pct": -3.5, "portfolio_heat_pct": 1.0}
    res3 = _apply_deterministic_risk_clamp(pm_dec3, stances3, actual_risk)
    assert res3["recommended_risk_multiplier"] <= 0.5


def test_grounding_check():
    """Verify numerical grounding check logic."""
    assert _is_grounded({"price": 1.0850, "note": "target 1.0950"}, 1.0850) is True
    assert _is_grounded({"text": "no numbers here at all"}, 1.0850) is False
    assert _is_grounded({}, 1.0850) is False
    # Numbers far from price (e.g. 9999 and 8888 vs 1.0850) are rejected if no reference
    assert _is_grounded({"unrelated": 9999, "other": 8888}, 1.0850) is False
    # If reference contains that number, it is grounded
    assert _is_grounded({"unrelated": 9999}, 1.0850, reference={"key_level": 9999}) is True


@pytest.mark.asyncio
async def test_bear_dissent_round_2_evaluates_rebuttal():
    """Verify Bear Dissent node in round 2 incorporates rebuttal and stops infinite loop."""
    config = {
        "configurable": {
            "scheduler": MagicMock(
                settings={"agent_architecture": {"enable_debate": True, "debate_rounds": 2}}
            )
        }
    }
    state = {
        "actionable_trades": [("EURUSD", {"analysis_id": 101, "decision": "buy"})],
        "debate_states": {
            "EURUSD": {
                "verified_bull_claim": {"strength_score": 9},
                "original_context": {"decision": "buy", "entry_price": 1.0850},
                "bull_rebuttal": {"rebuttal": "OB absorption at 1.0850", "rebuttal_strength": 8},
                "turn": 2,
                "curr_p": 1.0850,
                "fact_sheet": {"symbol": "EURUSD"}
            }
        }
    }
    captured_context = {}
    async def mock_bear(client, sym, ctx, claim, fs):
        nonlocal captured_context
        captured_context = ctx
        return {"risk_severity": 4, "dissent": "conceding minor risk at 1.0850"}

    with patch("graph.nodes.debate.bear_dissent_node.generate_bear_dissent", side_effect=mock_bear):
        res = await bear_dissent_node(state, config)
        assert "bull_rebuttal" in captured_context
        deb = res["debate_states"]["EURUSD"]
        # In round 2, needs_rebuttal must be False to terminate cyclic loop
        assert deb["needs_rebuttal"] is False

