# ==============================================================================
# File: graph/nodes/debate/round_robin_risk_nodes.py
# ==============================================================================

"""
Round-Robin Risk Persona Nodes for AI Trading Agent (CRITICAL-02).

Menerapkan musyawarah konsensus berantai (round-robin) antar persona risiko:
1. Conservative Risk Node: Menilai proteksi downside, tail risk, & invalidasi SL.
2. Aggressive Risk Node: Merespons kekhawatiran conservative dengan argumen upside & opportunity cost.
3. Neutral Risk Node: Menyelaraskan probabilitas risk-reward secara obyektif.
4. Portfolio Judge Node: Mengadili konsensus ketiga persona & menetapkan risk clamp final.
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple

from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from database.db import get_session
from database.models import AssetAnalysis
from analysis.providers.llm_factory import get_client_for_task
from analysis.debate.conservative_risk_llm import analyze_risk_conservative_llm
from analysis.debate.aggressive_risk_llm import analyze_risk_aggressive_llm
from analysis.debate.neutral_risk_llm import analyze_risk_neutral_llm
from analysis.debate.portfolio_manager import make_portfolio_decision
from analysis.debate.deterministic_risk import (
    analyze_risk_conservative,
    analyze_risk_aggressive,
    analyze_risk_neutral,
    make_portfolio_decision_deterministic,
)
from analysis.memory.decision_log import DecisionLogger
from graph.nodes.debate.helpers import (
    compute_actual_risk_state,
    _get_recent_sl_streak,
    _get_correlated_exposure_summary,
    _apply_deterministic_risk_clamp,
    sync_facade_patches,
)

logger = logging.getLogger("TradingAgent.Graph.Debate.RoundRobinRisk")


async def _build_strict_context(s_inner, sym: str, r: dict, state: TradingState, scheduler) -> Tuple[Optional[AssetAnalysis], Optional[dict], Optional[dict]]:
    """Helper untuk membangun strict risk context per simbol."""
    analysis_id = r.get("analysis_id")
    deb = state.get("debate_states", {}).get(sym, {})
    verdict = state.get("investment_verdicts", {}).get(sym, {})
    fact_sheet = deb.get("fact_sheet")
    rel_intel = deb.get("rel_intel") or []
    settings = scheduler.settings if scheduler else {}
    mt5_client = getattr(scheduler, "_mt5", None) if scheduler else None

    ana = await s_inner.get(AssetAnalysis, analysis_id)
    if not ana:
        return None, None, None

    actual_risk_state = await compute_actual_risk_state(s_inner, settings, mt5_client=mt5_client)
    entry_zone_data = json.loads(ana.entry_zone) if ana.entry_zone else {}
    entry_price = entry_zone_data.get("price") or ana.price_at_analysis
    rr_ratio = None
    if entry_price and ana.stop_loss and ana.take_profit:
        sl_dist = abs(entry_price - ana.stop_loss)
        tp_dist = abs(entry_price - ana.take_profit)
        if sl_dist > 0:
            rr_ratio = tp_dist / sl_dist

    strict_context = {
        "symbol": sym,
        "decision": ana.decision.upper(),
        "confluence_score": ana.confluence_score,
        "priced_in_score": ana.priced_in_score,
        "judge_approval": verdict.get("final_decision"),
        "judge_risk_multiplier": verdict.get("risk_multiplier"),
        "fact_sheet": fact_sheet,
        "actual_risk_state": actual_risk_state,
        "recent_sl_streak_this_symbol": await _get_recent_sl_streak(s_inner, sym),
        "correlated_open_positions": await _get_correlated_exposure_summary(s_inner, sym),
        "rr_ratio": rr_ratio,
        "sl_beyond_structure": True,
        "user_market_intel": rel_intel,
    }

    actual_risk_state_with_intel = dict(actual_risk_state or {})
    if rel_intel:
        actual_risk_state_with_intel["user_market_intel"] = rel_intel

    return ana, strict_context, actual_risk_state_with_intel


async def conservative_risk_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Turn 1: Conservative Risk Persona (Worst-Case Downside Protection)."""
    sync_facade_patches()
    actionable = state.get("actionable_trades", [])
    if not actionable:
        return {}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    settings = scheduler.settings if scheduler else {}
    use_deterministic = settings.get("agent_architecture", {}).get("deterministic_risk_gate", True)

    risk_debate_states = dict(state.get("risk_debate_states", {}))
    semaphore = asyncio.Semaphore(3)

    async def _process_single(sym: str, r: dict):
        async with semaphore:
            try:
                async with get_session() as session:
                    ana, strict_context, _ = await _build_strict_context(session, sym, r, state, scheduler)
                    if not strict_context:
                        return sym, None

                    if use_deterministic:
                        cons_risk = analyze_risk_conservative(strict_context)
                    else:
                        client = get_client_for_task("risk_gate_conservative", settings)
                        cons_risk = await analyze_risk_conservative_llm(client, sym, strict_context)

                    return sym, cons_risk
            except Exception as e:
                logger.error(f"[{sym}] Conservative risk analysis failed: {e}", exc_info=True)
                return sym, None

    results = await asyncio.gather(*[_process_single(sym, r) for sym, r in actionable])
    for sym, cons_risk in results:
        if cons_risk:
            existing = risk_debate_states.get(sym, {})
            existing["conservative"] = cons_risk
            risk_debate_states[sym] = existing

    return {"risk_debate_states": risk_debate_states}


async def aggressive_risk_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Turn 2: Aggressive Risk Persona (Upside Reward & Opportunity Cost Justification)."""
    sync_facade_patches()
    actionable = state.get("actionable_trades", [])
    if not actionable:
        return {}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    settings = scheduler.settings if scheduler else {}
    use_deterministic = settings.get("agent_architecture", {}).get("deterministic_risk_gate", True)
    min_rr = settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3)

    risk_debate_states = dict(state.get("risk_debate_states", {}))
    semaphore = asyncio.Semaphore(3)

    async def _process_single(sym: str, r: dict):
        async with semaphore:
            try:
                async with get_session() as session:
                    ana, strict_context, _ = await _build_strict_context(session, sym, r, state, scheduler)
                    if not strict_context:
                        return sym, None

                    # Inject conservative concerns for round-robin dialetics
                    cons_prior = risk_debate_states.get(sym, {}).get("conservative", {})
                    strict_context["conservative_concerns"] = cons_prior.get("concerns", [])
                    strict_context["conservative_approval"] = cons_prior.get("approval", True)

                    if use_deterministic:
                        agg_risk = analyze_risk_aggressive(strict_context, min_rr_ratio=min_rr)
                    else:
                        client = get_client_for_task("risk_gate_aggressive", settings)
                        agg_risk = await analyze_risk_aggressive_llm(client, sym, strict_context)

                    return sym, agg_risk
            except Exception as e:
                logger.error(f"[{sym}] Aggressive risk analysis failed: {e}", exc_info=True)
                return sym, None

    results = await asyncio.gather(*[_process_single(sym, r) for sym, r in actionable])
    for sym, agg_risk in results:
        if agg_risk:
            existing = risk_debate_states.get(sym, {})
            existing["aggressive"] = agg_risk
            risk_debate_states[sym] = existing

    return {"risk_debate_states": risk_debate_states}


async def neutral_risk_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Turn 3: Neutral Risk Persona (Objective Expected Value Synthesis)."""
    sync_facade_patches()
    actionable = state.get("actionable_trades", [])
    if not actionable:
        return {}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    settings = scheduler.settings if scheduler else {}
    use_deterministic = settings.get("agent_architecture", {}).get("deterministic_risk_gate", True)
    min_rr = settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3)

    risk_debate_states = dict(state.get("risk_debate_states", {}))
    semaphore = asyncio.Semaphore(3)

    async def _process_single(sym: str, r: dict):
        async with semaphore:
            try:
                async with get_session() as session:
                    ana, strict_context, _ = await _build_strict_context(session, sym, r, state, scheduler)
                    if not strict_context:
                        return sym, None

                    # Inject both conservative and aggressive perspectives for round-robin consensus
                    sym_debate = risk_debate_states.get(sym, {})
                    strict_context["conservative_assessment"] = sym_debate.get("conservative", {})
                    strict_context["aggressive_assessment"] = sym_debate.get("aggressive", {})

                    if use_deterministic:
                        neu_risk = analyze_risk_neutral(strict_context, min_rr_ratio=min_rr)
                    else:
                        client = get_client_for_task("risk_gate_neutral", settings)
                        neu_risk = await analyze_risk_neutral_llm(client, sym, strict_context)

                    return sym, neu_risk
            except Exception as e:
                logger.error(f"[{sym}] Neutral risk analysis failed: {e}", exc_info=True)
                return sym, None

    results = await asyncio.gather(*[_process_single(sym, r) for sym, r in actionable])
    for sym, neu_risk in results:
        if neu_risk:
            existing = risk_debate_states.get(sym, {})
            existing["neutral"] = neu_risk
            risk_debate_states[sym] = existing

    return {"risk_debate_states": risk_debate_states}


async def portfolio_judge_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """Turn 4: Portfolio Judge (Consensus Adjudication & Deterministic Risk Clamping)."""
    sync_facade_patches()
    actionable = state.get("actionable_trades", [])
    if not actionable:
        return {"actionable_trades": []}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    settings = scheduler.settings if scheduler else {}
    use_deterministic = settings.get("agent_architecture", {}).get("deterministic_risk_gate", True)

    risk_debate_states = dict(state.get("risk_debate_states", {}))
    portfolio_decisions = dict(state.get("portfolio_decisions", {}))
    surviving_trades: List[Tuple[str, dict]] = []
    semaphore = asyncio.Semaphore(3)

    async def _process_single(sym: str, r: dict):
        async with semaphore:
            try:
                async with get_session() as session:
                    ana, strict_context, actual_risk_state_with_intel = await _build_strict_context(session, sym, r, state, scheduler)
                    if not strict_context or not ana:
                        return sym, (sym, r), None

                    single_risk_debate = risk_debate_states.get(sym, {})
                    if use_deterministic:
                        pm_decision = make_portfolio_decision_deterministic(single_risk_debate)
                    else:
                        client = get_client_for_task("portfolio_manager_per_trade", settings)
                        pm_decision = await make_portfolio_decision(client, sym, single_risk_debate, actual_risk_state_with_intel)

                    pm_decision = _apply_deterministic_risk_clamp(pm_decision, single_risk_debate, actual_risk_state_with_intel)

                    survived_item = None
                    if pm_decision.get("approval") == True:
                        r["risk_multiplier"] = pm_decision.get("recommended_risk_multiplier", 1.0)
                        ana.risk_multiplier = r["risk_multiplier"]
                        await session.commit()
                        survived_item = (sym, r)
                        logger.info(f"[PortfolioJudge] Approved {sym} (Multiplier: {r['risk_multiplier']})")
                    else:
                        logger.warning(f"[PortfolioJudge] Rejected {sym}: {pm_decision.get('reason')}")
                        await DecisionLogger.log_paper_whatif(
                            session=session,
                            analysis_id=ana.id,
                            symbol=sym,
                            decision=r.get("decision", "wait"),
                            confidence=r.get("confidence", 0),
                            confluence_score=ana.confluence_score,
                            rationale=ana.rationale or "",
                            reason=f"Portfolio Judge Rejected: {pm_decision.get('reason')}",
                            context_snapshot_id=ana.context_snapshot_id,
                            ssvp_cds_score=ana.ssvp_cds_score_at_analysis
                        )

                    return sym, survived_item, pm_decision
            except Exception as e:
                logger.error(f"[{sym}] Portfolio judge evaluation failed: {e}", exc_info=True)
                return sym, (sym, r), None

    results = await asyncio.gather(*[_process_single(sym, r) for sym, r in actionable])
    for sym, survived_item, pm_decision in results:
        if pm_decision:
            portfolio_decisions[sym] = pm_decision
        if survived_item:
            surviving_trades.append(survived_item)

    return {
        "actionable_trades": surviving_trades,
        "portfolio_decisions": portfolio_decisions,
        "risk_debate_states": risk_debate_states,
        "summary": {
            "debate_approved": [sym for sym, r in surviving_trades],
        },
    }
