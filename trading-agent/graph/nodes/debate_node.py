# ==============================================================================
# File: graph/nodes/debate_node.py
# ==============================================================================

import sys
import json
import logging
import asyncio
from typing import Dict, Any, Optional, cast

import utils.clock as clock
from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from database.db import get_session
from database.models import AssetAnalysis
from analysis.memory.decision_log import DecisionLogger
from analysis.providers.llm_factory import get_client_for_task

# Import decomposed sub-agent nodes & helpers
from graph.nodes.debate.helpers import (
    _get_recent_sl_streak,
    _get_correlated_exposure_summary,
    _apply_deterministic_risk_clamp,
    _is_grounded,
    compute_actual_risk_state,
    inject_coherence_and_intel,
    sync_facade_patches,
)
from graph.nodes.debate.bull_advocate_node import bull_advocate_node
from graph.nodes.debate.bear_dissent_node import bear_dissent_node
from graph.nodes.debate.rebuttal_node import rebuttal_node
from graph.nodes.debate.debate_judge_node import debate_judge_node
from graph.nodes.debate.risk_evaluator_node import risk_evaluator_node
from graph.nodes.debate.subgraph import build_debate_subgraph

# Re-export debate components for backward compatibility and test mock targeting
from analysis.debate.bull_analyst import generate_bull_advocacy, generate_bull_rebuttal
from analysis.debate.bear_analyst import generate_bear_dissent
from analysis.debate.investment_judge import evaluate_debate
from analysis.debate.fact_sheet import build_fact_sheet
from analysis.debate.conservative_risk_llm import analyze_risk_conservative_llm
from analysis.debate.aggressive_risk_llm import analyze_risk_aggressive_llm
from analysis.debate.neutral_risk_llm import analyze_risk_neutral_llm
from analysis.debate.portfolio_manager import make_portfolio_decision
from analysis.debate.deterministic_risk import (
    analyze_risk_conservative, analyze_risk_aggressive, analyze_risk_neutral,
    make_portfolio_decision_deterministic,
)
from analysis.debate.adjustment_validator import validate_and_apply_judge_adjustments

logger = logging.getLogger("TradingAgent.Graph.DebateNode")


async def debate_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Backward-compatible facade for Multi-Agent Debate.
    Orchestrates the decomposed debate sub-agents (Bull Advocate, Bear Dissent,
    Dialectic Rebuttal, Debate Judge, and Risk Evaluator).
    """
    actionable = state.get("actionable_trades", [])
    if not actionable:
        return {}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    settings = scheduler.settings if scheduler else {}
    debate_cfg = settings.get("agent_architecture", {})

    if not debate_cfg.get("enable_debate", True):
        logger.info("Debate is disabled in settings. Bypassing debate node.")
        return {}

    logger.info(f"[Step 5a] Multi-Agent Debate Architecture started for {len(actionable)} trades...")

    # Propagate any monkey-patched module attributes to sub-agent modules
    sync_facade_patches()

    # Step 1: Bull Advocate Sub-Agent
    res_bull = await bull_advocate_node(state, config)
    current_state = cast(TradingState, {**state, **res_bull})

    # Step 2: Bear Dissent Sub-Agent
    res_bear = await bear_dissent_node(current_state, config)
    current_state = cast(TradingState, {**current_state, **res_bear})

    # Step 3: Dialectic Rebuttal Sub-Agent (Conditional)
    deb_states = current_state.get("debate_states", {})
    needs_rebuttal = any(
        deb_states.get(sym, {}).get("needs_rebuttal", False)
        for sym, _ in current_state.get("actionable_trades", [])
    )
    if needs_rebuttal:
        res_rebuttal = await rebuttal_node(current_state, config)
        current_state = cast(TradingState, {**current_state, **res_rebuttal})

    # Step 4: Investment Judge Sub-Agent
    res_judge = await debate_judge_node(current_state, config)
    current_state = cast(TradingState, {**current_state, **res_judge})

    # Step 5: Risk Evaluator & Portfolio Manager Sub-Agent
    res_risk = await risk_evaluator_node(current_state, config)
    current_state = cast(TradingState, {**current_state, **res_risk})

    return {
        "summary": current_state.get("summary", {}),
        "actionable_trades": current_state.get("actionable_trades", []),
        "debate_states": current_state.get("debate_states", {}),
        "risk_debate_states": current_state.get("risk_debate_states", {}),
        "investment_verdicts": current_state.get("investment_verdicts", {}),
        "portfolio_decisions": current_state.get("portfolio_decisions", {}),
    }
