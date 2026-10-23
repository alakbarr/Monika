# ==============================================================================
# File: graph/nodes/risk_gate_node.py
# Monika Core Risk Gate Node & Orchestrator
# ==============================================================================

"""
Core LangGraph RiskGate Node Orchestrator.
Coordinates quant arbitration, structural level synthesis, portfolio correlation
gating, institutional RiskGate evaluation, pre-commit validation, and negotiable
re-planning feedback.

Decomposed into specialized sub-modules in `graph.nodes.risk.*`:
- level_synthesizer: Order entry/SL/TP single-pass derivation & repair
- quant_arbitration: Quant alpha evaluation & SignalArbitrator defense
- portfolio_synthesis: AI portfolio synthesis & correlation heat reduction
- rejection_auditor: Unified paper what-if & benchmark trajectory auditing
- proposal_notifier: Operator notification dispatch
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

from langchain_core.runnables.config import RunnableConfig

from monika.application.graph.nodes.risk.level_synthesizer import _safe_num, resolve_and_repair_levels
from monika.application.graph.nodes.risk.portfolio_synthesis import (
    ai_portfolio_synthesis as _ai_portfolio_synthesis,
)
from monika.application.graph.nodes.risk.portfolio_synthesis import (
    apply_portfolio_synthesis_reduction,
)
from monika.application.graph.nodes.risk.proposal_notifier import send_proposal_notifications
from monika.application.graph.nodes.risk.quant_arbitration import run_quant_arbitration
from monika.application.graph.nodes.risk.rejection_auditor import audit_trade_rejection
from monika.application.graph.state import TradingState

logger = logging.getLogger("TradingAgent.Graph.RiskGateNode")

__all__ = ["risk_gate_node", "_safe_num", "_ai_portfolio_synthesis"]


async def risk_gate_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    LangGraph execution node for evaluating trade proposals through
    Portfolio Synthesis, Correlation Filters, and Institutional RiskGate.
    """
    configurable = (
        config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)
    ) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    summary = state.get("summary", {})
    actionable = list(state.get("actionable_trades", []) or [])
    asset_analyses = dict(state.get("asset_analyses", {}) or {})

    if scheduler is None:
        logger.error("Scheduler not found in config")
        return {"summary": summary, "actionable_trades": [], "approved_trades": []}

    rejected_candidates: List[Dict[str, Any]] = []

    # 1. Quant Alpha Evaluation & Signal Arbitration (with single-pass level repair)
    try:
        actionable, arb_rejected = await run_quant_arbitration(
            scheduler=scheduler,
            actionable=actionable,
            asset_analyses=asset_analyses,
            state=state,
        )
        rejected_candidates.extend(arb_rejected)
    except Exception as e:
        logger.critical(
            f"[RiskGateNode] SignalArbitrator check failed with error: {e}. Failing closed -> stopping actionable trades.",
            exc_info=True,
        )
        actionable = []

    if not actionable:
        return {"summary": summary, "actionable_trades": [], "approved_trades": []}

    logger.info(f"[Step 7a] Stage 3 Portfolio Synthesis for {len(actionable)} trades...")

    # 2. Deterministic Portfolio Correlation Gating
    try:
        from monika.domain.risk.portfolio_correlation_gate import filter_correlated_proposals
        from monika.infrastructure.database.db import get_session

        async with get_session() as session:
            kept_actionable, rejected_actionable = await filter_correlated_proposals(session, actionable)

        if rejected_actionable:
            async with get_session() as rej_session:
                for sym, r, reason in rejected_actionable:
                    reasons = [f"correlation_gate: {reason}"]
                    rejected_candidates.append({"symbol": sym, "trade": r, "reasons": reasons})
                    await audit_trade_rejection(
                        rej_session,
                        symbol=sym,
                        trade_data=r,
                        reasons=reasons,
                        stage="correlation_gate",
                    )
        actionable = kept_actionable
    except Exception as e:
        logger.critical(
            f"[RiskGateNode] Correlation filter failed with error: {e}. Failing closed -> dropping unverified trades.",
            exc_info=True,
        )
        for sym, r in actionable:
            rejected_candidates.append({"symbol": sym, "trade": r, "reasons": [f"correlation_gate_exception: {e}"]})
        actionable = []

    # 3. AI Portfolio Synthesis & Correlation Heat Reduction (if >= 3 trades proposed)
    actionable, synth_rejected = await apply_portfolio_synthesis_reduction(actionable, scheduler, state)
    rejected_candidates.extend(synth_rejected)

    # 4. Institutional 22-Check Risk Gate Evaluation
    if actionable:
        try:
            from monika.domain.risk.risk_gate import RiskGate
            from monika.domain.risk.trade_proposal import TradeProposal
            from monika.infrastructure.database.db import get_session as _gs_rg
            from monika.infrastructure.database.models import AssetAnalysis

            risk_gate = getattr(scheduler, "risk_gate", None) or RiskGate(
                scheduler.settings, mt5_client=getattr(scheduler, "mt5", None)
            )
            gate_approved = []

            is_paper = bool(
                scheduler.settings.get("paper_trading", {}).get("enabled", True)
                if hasattr(scheduler, "settings") and isinstance(scheduler.settings, dict)
                else True
            )
            equity: Optional[float] = None
            if hasattr(scheduler, "mt5") and scheduler.mt5:
                try:
                    acc = await scheduler.mt5.get_account_info()
                    if isinstance(acc, dict):
                        raw_eq = acc.get("equity")
                        if raw_eq is not None:
                            val = float(raw_eq)
                            if val > 0 and not (math.isnan(val) or math.isinf(val)):
                                equity = val
                except Exception as eq_err:
                    logger.warning(f"[RiskGateNode] Failed to fetch MT5 account info: {eq_err}")

            if equity is None:
                if is_paper:
                    equity = float(
                        scheduler.settings.get("paper_trading", {}).get("initial_balance", 10000.0)
                        if hasattr(scheduler, "settings") and isinstance(scheduler.settings, dict)
                        else 10000.0
                    )
                else:
                    logger.critical(
                        "[RiskGateNode] Live trading active but account equity unavailable from MT5. "
                        "Enforcing FAIL-CLOSED: dropping all trade proposals."
                    )
                    actionable = []
                    summary["execution"] = {"status": "rejected_unverified_live_equity"}
                    return {
                        "summary": summary,
                        "asset_analyses": state.get("asset_analyses", {}),
                        "actionable_trades": [],
                        "approved_trades": [],
                        "is_negotiable_rejection": False,
                        "negotiable_rejections": [],
                        "rejection_feedback": None,
                    }

            async with _gs_rg() as rg_session:
                for sym, r in actionable:
                    analysis_id = r.get("analysis_id")
                    ana = await rg_session.get(AssetAnalysis, analysis_id) if analysis_id else None

                    dec = str(r.get("decision") or (ana.decision if ana else "WAIT")).upper()
                    if dec in ("BUY", "SELL"):
                        entry_price, sl, tp = await resolve_and_repair_levels(
                            session=rg_session,
                            scheduler=scheduler,
                            symbol=sym,
                            r=r,
                            ana=ana,
                            state_asset_analyses=state.get("asset_analyses"),
                        )
                    else:
                        entry_price = _safe_num(r.get("entry_price"))
                        sl = _safe_num(r.get("stop_loss"))
                        tp = _safe_num(r.get("take_profit"))
                        if r.get("entry_price") != entry_price:
                            r["entry_price"] = entry_price

                    conf = float(r.get("confidence", 0.5) or 0.5)
                    raw_conf_score = r.get("confluence_score")
                    if raw_conf_score is None and ana is not None:
                        raw_conf_score = getattr(ana, "confluence_score", None)
                    confluence_val = float(raw_conf_score) if raw_conf_score is not None else 0.0

                    reasoning_text = ""
                    if ana and isinstance(getattr(ana, "rationale", None), str):
                        reasoning_text = str(ana.rationale)

                    conf_override = r.get("confidence_override") or (
                        r.get("metadata", {}).get("confidence_override")
                        if isinstance(r.get("metadata"), dict)
                        else None
                    )

                    try:
                        proposal = TradeProposal.from_analysis(
                            symbol=sym,
                            decision=dec,
                            entry_price=entry_price,
                            stop_loss=sl,
                            take_profit=tp,
                            lot_size=float(r.get("lot_size", 0.01) or 0.01),
                            confluence_score=confluence_val,
                            confidence_override=conf_override if conf_override is not None else conf,
                            reasoning_text=reasoning_text,
                            provenance_verified=True,
                            account_equity=equity,
                            analysis=ana,
                        )
                        verdict = await risk_gate.evaluate_proposal(
                            rg_session, proposal, account_equity=equity, analysis=ana
                        )
                        if verdict.approved:
                            gate_approved.append((sym, r))
                        else:
                            reasons = verdict.rejection_reasons or verdict.checks_failed or ["risk_gate_rejected"]
                            logger.warning(f"[RiskGate] Suppressed {sym}: {reasons}")
                            rejected_candidates.append(
                                {"symbol": sym, "trade": r, "reasons": [f"risk_gate: {x}" for x in reasons]}
                            )
                            await audit_trade_rejection(
                                rg_session,
                                symbol=sym,
                                trade_data=r,
                                reasons=reasons,
                                stage="risk_gate",
                                analysis_record=ana,
                            )
                    except Exception as prop_err:
                        logger.warning(f"[RiskGate] Proposal error for {sym}: {prop_err}")
                        rejected_candidates.append(
                            {"symbol": sym, "trade": r, "reasons": [f"proposal_error: {prop_err}"]}
                        )
                        await audit_trade_rejection(
                            rg_session,
                            symbol=sym,
                            trade_data=r,
                            reasons=[f"proposal_error: {prop_err}"],
                            stage="proposal_error",
                            analysis_record=ana,
                        )

            # Invariant: If trades share a pair_group_id, ALL legs of the pair must be approved (atomic all-or-nothing).
            pair_groups_approved: dict[str, list[tuple[str, dict]]] = {}
            for sym, r in gate_approved:
                pgid = r.get("pair_group_id")
                if pgid:
                    pair_groups_approved.setdefault(pgid, []).append((sym, r))

            pair_groups_rejected: set[str] = set()
            for cand in rejected_candidates:
                pgid = cand.get("trade", {}).get("pair_group_id")
                if pgid:
                    pair_groups_rejected.add(pgid)

            filtered_gate_approved = []
            for sym, r in gate_approved:
                pgid = r.get("pair_group_id")
                if pgid and pgid in pair_groups_rejected:
                    logger.warning(
                        f"[RiskGate] Atomic pair violation: dropping {sym} because sibling leg in {pgid} was rejected."
                    )
                    rejected_candidates.append(
                        {"symbol": sym, "trade": r, "reasons": [f"paired_leg_rejected in pair_group {pgid}"]}
                    )
                elif pgid and len(pair_groups_approved.get(pgid, [])) < 2:
                    logger.warning(
                        f"[RiskGate] Incomplete pair: dropping {sym} because pair_group {pgid} has only 1 approved leg."
                    )
                    rejected_candidates.append(
                        {"symbol": sym, "trade": r, "reasons": [f"incomplete_pair_legs in pair_group {pgid}"]}
                    )
                else:
                    filtered_gate_approved.append((sym, r))

            actionable = filtered_gate_approved
        except Exception as e:
            logger.critical(f"[RiskGate] Evaluation failure - enforcing FAIL-CLOSED: {e}", exc_info=True)
            for sym, r in actionable:
                rejected_candidates.append(
                    {
                        "symbol": sym,
                        "trade": r,
                        "reasons": [f"risk_gate_system_exception: {e}"],
                    }
                )
            actionable = []

    # 5. Deterministic Trade Pre-Commit Gate
    if actionable:
        try:
            from monika.application.analysis.validators.precommit_gate import TradePreCommitGate
            from monika.infrastructure.database.db import get_session as _gs_pre

            precommit_gate = TradePreCommitGate(scheduler.settings)
            precommit_approved = []

            async with _gs_pre() as pre_session:
                for sym, r in actionable:
                    passed, failures = await precommit_gate.verify_precommit(pre_session, r, sym)
                    if passed:
                        precommit_approved.append((sym, r))
                    else:
                        logger.warning(f"[PreCommitGate] Suppressed {sym} from execution: {failures}")
                        rejected_candidates.append({"symbol": sym, "trade": r, "reasons": failures})
                        await audit_trade_rejection(
                            pre_session,
                            symbol=sym,
                            trade_data=r,
                            reasons=failures,
                            stage="precommit_gate",
                        )

            # Invariant: Precommit atomic pair check
            pc_pair_approved: dict[str, list[tuple[str, dict]]] = {}
            for sym, r in precommit_approved:
                pgid = r.get("pair_group_id")
                if pgid:
                    pc_pair_approved.setdefault(pgid, []).append((sym, r))

            pc_pair_rejected: set[str] = set()
            for cand in rejected_candidates:
                pgid = cand.get("trade", {}).get("pair_group_id")
                if pgid:
                    pc_pair_rejected.add(pgid)

            filtered_precommit = []
            for sym, r in precommit_approved:
                pgid = r.get("pair_group_id")
                if pgid and (pgid in pc_pair_rejected or len(pc_pair_approved.get(pgid, [])) < 2):
                    logger.warning(f"[PreCommitGate] Atomic pair violation: dropping {sym} in pair {pgid}.")
                    rejected_candidates.append(
                        {"symbol": sym, "trade": r, "reasons": [f"precommit_pair_broken in {pgid}"]}
                    )
                else:
                    filtered_precommit.append((sym, r))

            actionable = filtered_precommit
        except Exception as e:
            logger.critical(
                f"[RiskGateNode] TradePreCommitGate check failed with error: {e}. Failing closed -> clearing actionable trades.",
                exc_info=True,
            )
            actionable = []

    summary["portfolio_synthesis_approved"] = [sym for sym, r in actionable]

    # 6. Telegram Operator Proposal Notifications
    auto_execute = False
    if scheduler and hasattr(scheduler, "settings"):
        auto_execute = bool(scheduler.settings.get("trading", {}).get("auto_execute", False))

    if actionable:
        if not auto_execute:
            await send_proposal_notifications(actionable)
            summary["execution"] = {"status": "pending_approval", "count": len(actionable)}
        else:
            logger.info(
                f"[RiskGateNode] auto_execute=true: Routing {len(actionable)} trade(s) directly to execution node."
            )
            summary["execution"] = {"status": "auto_execute_pending", "count": len(actionable)}
    else:
        logger.info("[Step 7b] No actionable buy/sell decisions this cycle.")
        summary["execution"] = {"status": "no_actionable_decisions"}

    # 7. Check for negotiable rejections for bidirectional re-planning
    is_negotiable = False
    rejection_feedback = None
    negotiable_items = []
    current_refinement = state.get("refinement_count", 0)

    if rejected_candidates and current_refinement < 2:
        from monika.application.graph.nodes.plan_refinement_node import _is_reason_negotiable

        negotiable_items = [
            item for item in rejected_candidates if _is_reason_negotiable(" ".join(item.get("reasons", [])))
        ]
        if negotiable_items:
            is_negotiable = True
            rejection_feedback = {"rejected_items": negotiable_items}
            logger.info(
                f"[RiskGateNode] Detected {len(negotiable_items)} negotiable rejections. "
                f"Iteration {current_refinement + 1}/2."
            )
            if not actionable:
                summary["execution"] = {"status": "routing_to_plan_refinement", "rejected_count": len(negotiable_items)}

    return {
        "summary": summary,
        "asset_analyses": state.get("asset_analyses", {}),
        "actionable_trades": actionable,
        "approved_trades": actionable,
        "is_negotiable_rejection": is_negotiable and not actionable,
        "negotiable_rejections": negotiable_items,
        "rejection_feedback": rejection_feedback,
    }
