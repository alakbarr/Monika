# ==============================================================================
# File: graph/nodes/debate/risk_evaluator_node.py
# ==============================================================================

import json
import logging
import asyncio
from typing import Dict, Any, List, Tuple, Optional

from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from database.db import get_session
from database.models import AssetAnalysis
from analysis.providers.llm_factory import get_client_for_task
from analysis.memory.decision_log import DecisionLogger
from analysis.debate.conservative_risk_llm import analyze_risk_conservative_llm
from analysis.debate.aggressive_risk_llm import analyze_risk_aggressive_llm
from analysis.debate.neutral_risk_llm import analyze_risk_neutral_llm
from analysis.debate.portfolio_manager import make_portfolio_decision
from analysis.debate.deterministic_risk import (
    analyze_risk_conservative, analyze_risk_aggressive, analyze_risk_neutral,
    make_portfolio_decision_deterministic,
)
from graph.nodes.debate.helpers import (
    compute_actual_risk_state, _get_recent_sl_streak,
    _get_correlated_exposure_summary, _apply_deterministic_risk_clamp,
    sync_facade_patches
)

logger = logging.getLogger("TradingAgent.Graph.Debate.RiskEvaluatorNode")


async def risk_evaluator_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Sub-agent node: Risk Evaluator & Portfolio Manager.
    Mengevaluasi risiko dari perspektif multi-persona (Conservative, Aggressive, Neutral),
    menjalankan Portfolio Manager, dan menerapkan deterministic risk clamp.
    """
    sync_facade_patches()
    actionable = state.get("actionable_trades", [])
    summary = dict(state.get("summary", {}))
    risk_debate_states = dict(state.get("risk_debate_states", {}))
    portfolio_decisions = dict(state.get("portfolio_decisions", {}))
    debate_states = state.get("debate_states", {})
    investment_verdicts = state.get("investment_verdicts", {})

    if not actionable:
        return {
            "actionable_trades": [],
            "risk_debate_states": risk_debate_states,
            "portfolio_decisions": portfolio_decisions,
            "summary": summary,
        }

    if portfolio_decisions:
        logger.debug("[Debate:RiskEvaluator] Portfolio decisions already established via round-robin consensus.")
        return {
            "actionable_trades": actionable,
            "risk_debate_states": risk_debate_states,
            "portfolio_decisions": portfolio_decisions,
        }

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    settings = scheduler.settings if scheduler else {}
    debate_cfg = settings.get("agent_architecture", {})

    if not debate_cfg.get("enable_debate", True):
        return {}

    logger.info(f"[Debate:RiskEvaluator] Running multi-persona risk evaluation for {len(actionable)} trades...")

    mt5_client = getattr(scheduler, '_mt5', None) if scheduler else None

    async with get_session() as session:
        actual_risk_state = await compute_actual_risk_state(session, settings, mt5_client=mt5_client)

        user_market_intel = state.get("user_market_intel") or []
        use_deterministic = settings.get('agent_architecture', {}).get('deterministic_risk_gate', True)
        min_rr = settings.get('trading', {}).get('risk', {}).get('min_rr_ratio', 1.3)

        surviving_trades: List[Tuple[str, dict]] = []
        semaphore = asyncio.Semaphore(3)

        async def _process_single(sym: str, r: dict):
            analysis_id = r.get("analysis_id")
            deb = debate_states.get(sym, {})
            verdict = investment_verdicts.get(sym, {})
            fact_sheet = deb.get("fact_sheet")
            rel_intel = deb.get("rel_intel") or []
            bull_thesis = deb.get("bull_thesis", "")

            async with semaphore:
                try:
                    async with get_session() as s_inner:
                        ana = await s_inner.get(AssetAnalysis, analysis_id)
                        if not ana:
                            return sym, (sym, r), None, None

                        entry_zone_data = json.loads(ana.entry_zone) if ana.entry_zone else {}
                        entry_price = entry_zone_data.get('price') or ana.price_at_analysis
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

                        if use_deterministic:
                            cons_risk = analyze_risk_conservative(strict_context)
                            agg_risk = analyze_risk_aggressive(strict_context, min_rr_ratio=min_rr)
                            neu_risk = analyze_risk_neutral(strict_context, min_rr_ratio=min_rr)
                            single_risk_debate = {'conservative': cons_risk, 'aggressive': agg_risk, 'neutral': neu_risk}
                            pm_decision = make_portfolio_decision_deterministic(single_risk_debate)
                        else:
                            cons_risk = await analyze_risk_conservative_llm(get_client_for_task("risk_gate_conservative", settings), sym, strict_context)
                            agg_risk = await analyze_risk_aggressive_llm(get_client_for_task("risk_gate_aggressive", settings), sym, strict_context)
                            neu_risk = await analyze_risk_neutral_llm(get_client_for_task("risk_gate_neutral", settings), sym, strict_context)
                            single_risk_debate = {'conservative': cons_risk, 'aggressive': agg_risk, 'neutral': neu_risk}
                            pm_decision = await make_portfolio_decision(get_client_for_task("portfolio_manager_per_trade", settings), sym, single_risk_debate, actual_risk_state_with_intel)

                        pm_decision = _apply_deterministic_risk_clamp(pm_decision, single_risk_debate, actual_risk_state_with_intel)

                        survived_item = None
                        if pm_decision.get("approval") == True:
                            r["risk_multiplier"] = pm_decision.get("recommended_risk_multiplier", 1.0)
                            ana.risk_multiplier = r["risk_multiplier"]
                            await s_inner.commit()
                            survived_item = (sym, r)
                            logger.info(f"Portfolio Manager Approved {sym} (Multiplier: {r['risk_multiplier']})")
                        else:
                            logger.warning(f"Portfolio Manager Rejected {sym}: {pm_decision.get('reason')}")
                            await DecisionLogger.log_paper_whatif(
                                session=s_inner, analysis_id=int(analysis_id or ana.id), symbol=sym,
                                decision=r.get("decision", "wait"), confidence=r.get("confidence", 0),
                                confluence_score=ana.confluence_score, rationale=bull_thesis,
                                reason=f"Portfolio Manager Rejected: {pm_decision.get('reason')}",
                                context_snapshot_id=ana.context_snapshot_id,
                                ssvp_cds_score=ana.ssvp_cds_score_at_analysis
                            )

                        return sym, survived_item, single_risk_debate, pm_decision
                except Exception as e:
                    logger.error(f"[{sym}] Risk evaluation failed: {e}", exc_info=True)
                    return sym, (sym, r), None, None

        tasks = [_process_single(sym, r) for sym, r in actionable]
        results = await asyncio.gather(*tasks)

        for sym, survived, r_state, pm_dec in results:
            if r_state:
                risk_debate_states[sym] = r_state
            if pm_dec:
                portfolio_decisions[sym] = pm_dec
            if survived:
                surviving_trades.append(survived)

    pm_rejected = [sym for sym, r in actionable if sym not in [s for s, _ in surviving_trades]]
    raw_rejected = summary.get("debate_rejected")
    existing_rejected = list(raw_rejected) if isinstance(raw_rejected, list) else []
    summary["debate_rejected"] = existing_rejected + [s for s in pm_rejected if s not in existing_rejected]
    summary["debate_approved"] = [sym for sym, r in surviving_trades]

    return {
        "summary": summary,
        "actionable_trades": surviving_trades,
        "risk_debate_states": risk_debate_states,
        "portfolio_decisions": portfolio_decisions,
    }
