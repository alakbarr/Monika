# ==============================================================================
# File: graph/nodes/debate/subgraph.py
# ==============================================================================

import logging
from typing import Optional, Any

from graph.state import TradingState
from graph.nodes.debate.bull_advocate_node import bull_advocate_node
from graph.nodes.debate.bear_dissent_node import bear_dissent_node
from graph.nodes.debate.rebuttal_node import rebuttal_node
from graph.nodes.debate.debate_judge_node import debate_judge_node
from graph.nodes.debate.round_robin_risk_nodes import (
    conservative_risk_node,
    aggressive_risk_node,
    neutral_risk_node,
    portfolio_judge_node,
)

logger = logging.getLogger("TradingAgent.Graph.Debate.Subgraph")

try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
except ImportError:
    StateGraph = None
    END = "END"
    MemorySaver = None


def should_continue_debate(state: TradingState) -> str:
    """Evaluate whether cyclic dialectic debate should continue (CRITICAL-02)."""
    actionable = state.get("actionable_trades", [])
    if not actionable:
        return "END"
    deb_states = state.get("debate_states", {})
    for sym, _ in actionable:
        deb = deb_states.get(sym, {})
        turn = deb.get("turn", 1)
        disagreement = deb.get("disagreement", 0)
        divergence = deb.get("divergence", disagreement / 10.0)
        if (divergence > 0.40 or deb.get("needs_rebuttal", False)) and turn < 2:
            return "rebuttal"
    return "debate_judge"


def build_debate_subgraph(checkpointer: Optional[Any] = None, node_wrapper: Optional[Any] = None) -> Any:
    """
    Menyusun LangGraph multi-agent debate subgraph (CRITICAL-02):
    Bull Advocate -> Bear Dissent <-> [Cyclic Rebuttal if divergence > 0.40 & turn < 3]
    -> Debate Judge -> [Round-Robin Risk Consensus: Conservative -> Aggressive -> Neutral -> Portfolio Judge] -> END.
    """
    if StateGraph is None:
        raise RuntimeError("LangGraph is not installed. Cannot build debate subgraph.")

    wrap = node_wrapper if node_wrapper is not None else (lambda name, fn: fn)
    subgraph = StateGraph(TradingState)

    # 1. Add Sub-Agent Nodes
    subgraph.add_node("bull_advocate", wrap("bull_advocate", bull_advocate_node))
    subgraph.add_node("bear_dissent", wrap("bear_dissent", bear_dissent_node))
    subgraph.add_node("rebuttal", wrap("rebuttal", rebuttal_node))
    subgraph.add_node("debate_judge", wrap("debate_judge", debate_judge_node))
    subgraph.add_node("conservative_risk", wrap("conservative_risk", conservative_risk_node))
    subgraph.add_node("aggressive_risk", wrap("aggressive_risk", aggressive_risk_node))
    subgraph.add_node("neutral_risk", wrap("neutral_risk", neutral_risk_node))
    subgraph.add_node("portfolio_judge", wrap("portfolio_judge", portfolio_judge_node))

    # 2. Set Entry Point
    subgraph.set_entry_point("bull_advocate")

    # 3. Cyclic Dialectic Debate Loop (Bull <-> Bear)
    subgraph.add_edge("bull_advocate", "bear_dissent")

    subgraph.add_conditional_edges(
        "bear_dissent",
        should_continue_debate,
        {
            "rebuttal": "rebuttal",
            "debate_judge": "debate_judge",
            "END": END,
        }
    )

    # Cyclic edge: Rebuttal loops back to Bear Dissent for counter-evaluation
    subgraph.add_edge("rebuttal", "bear_dissent")

    # 4. Round-Robin Risk Consensus Sequence
    def judge_routing(state: TradingState) -> str:
        actionable = state.get("actionable_trades", [])
        if actionable and len(actionable) > 0:
            return "conservative_risk"
        return "END"

    subgraph.add_conditional_edges(
        "debate_judge",
        judge_routing,
        {
            "conservative_risk": "conservative_risk",
            "END": END,
        }
    )

    # Round-Robin chain: Conservative -> Aggressive -> Neutral -> Portfolio Judge -> END
    subgraph.add_edge("conservative_risk", "aggressive_risk")
    subgraph.add_edge("aggressive_risk", "neutral_risk")
    subgraph.add_edge("neutral_risk", "portfolio_judge")
    subgraph.add_edge("portfolio_judge", END)

    return subgraph.compile(checkpointer=checkpointer)
