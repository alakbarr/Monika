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
from typing import Any, Dict, List, Optional
from langchain_core.runnables.config import RunnableConfig

from graph.state import TradingState
from graph.nodes.risk.level_synthesizer import _safe_num, resolve_and_repair_levels
from graph.nodes.risk.portfolio_synthesis import (
    ai_portfolio_synthesis as _ai_portfolio_synthesis,
    apply_portfolio_synthesis_reduction,
)
from graph.nodes.risk.proposal_notifier import send_proposal_notifications
from graph.nodes.risk.quant_arbitration import run_quant_arbitration
from graph.nodes.risk.rejection_auditor import audit_trade_rejection

logger = logging.getLogger("TradingAgent.Graph.RiskGateNode")

__all__ = ["risk_gate_node", "_safe_num", "_ai_portfolio_synthesis"]


async def risk_gate_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    LangGraph execution node for evaluating trade proposals through
    Portfolio Synthesis, Correlation Filters, and Institutional RiskGate.
    """
    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
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
        logger.debug(f"[RiskGateNode] SignalArbitrator check non-fatal error: {e}")

    if not actionable:
        return {"summary": summary, "actionable_trades": [], "approved_trades": []}

    logger.info(f"[Step 7a] Stage 3 Portfolio Synthesis for {len(actionable)} trades...")

    # 2. Deterministic Portfolio Correlation Gating
    try:
        from database.db import get_session
        from risk.portfolio_correlation_gate import filter_correlated_proposals

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
        logger.debug(f"[RiskGateNode] Correlation filter non-fatal error: {e}")

    # 3. AI Portfolio Synthesis & Correlation Heat Reduction (if >= 3 trades proposed)
    actionable, synth_rejected = await apply_portfolio_synthesis_reduction(actionable, scheduler, state)
    rejected_candidates.extend(synth_rejected)

    # 4. Institutional 22-Check Risk Gate Evaluation
    if actionable:
        try:
            from database.db import get_session as _gs_rg
            from database.models import AssetAnalysis
            from risk.risk_gate import RiskGate
            from risk.trade_proposal import TradeProposal

            risk_gate = getattr(scheduler, "risk_gate", None) or RiskGate(
                scheduler.settings, mt5_client=getattr(scheduler, "mt5", None)
            )
            gate_approved = []

            equity = 10000.0
            if hasattr(scheduler, "mt5") and scheduler.mt5:
                try:
                    acc = await scheduler.mt5.get_account_info()
                    if isinstance(acc, dict):
                        equity = float(acc.get("equity", 10000.0))
                except Exception:
                    equity = 10000.0

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

                    reasoning_text = ""
                    if ana and hasattr(ana, "rationale") and not hasattr(ana.rationale, "_mock_name"):
                        reasoning_text = str(ana.rationale or "")

                    conf_override = r.get("confidence_override") or (
                        r.get("metadata", {}).get("confidence_override") if isinstance(r.get("metadata"), dict) else None
                    )

                    try:
                        proposal = TradeProposal.from_analysis(
                            symbol=sym,
                            decision=dec,
                            entry_price=entry_price,
                            stop_loss=sl,
                            take_profit=tp,
                            lot_size=float(r.get("lot_size", 0.01) or 0.01),
                            confluence_score=conf,
                            confidence_override=conf_override,
                            reasoning_text=reasoning_text,
                            provenance_verified=True,
                            account_equity=equity,
                            analysis=ana,
                        )
                        verdict = await risk_gate.evaluate_proposal(rg_session, proposal, account_equity=equity, analysis=ana)
                        if verdict.approved:
                            gate_approved.append((sym, r))
                        else:
                            reasons = verdict.rejection_reasons or verdict.checks_failed or ["risk_gate_rejected"]
                            logger.warning(f"[RiskGate] Suppressed {sym}: {reasons}")
                            rejected_candidates.append({"symbol": sym, "trade": r, "reasons": [f"risk_gate: {x}" for x in reasons]})
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
                        rejected_candidates.append({"symbol": sym, "trade": r, "reasons": [f"proposal_error: {prop_err}"]})
                        await audit_trade_rejection(
                            rg_session,
                            symbol=sym,
                            trade_data=r,
                            reasons=[f"proposal_error: {prop_err}"],
                            stage="proposal_error",
                            analysis_record=ana,
                        )

            actionable = gate_approved
        except Exception as e:
            logger.critical(f"[RiskGate] Evaluation failure - enforcing FAIL-CLOSED: {e}", exc_info=True)
            for sym, r in actionable:
                rejected_candidates.append({
                    "symbol": sym,
                    "trade": r,
                    "reasons": [f"risk_gate_system_exception: {e}"],
                })
            actionable = []

    # 5. Deterministic Trade Pre-Commit Gate
    if actionable:
        try:
            from analysis.validators.precommit_gate import TradePreCommitGate
            from database.db import get_session as _gs_pre

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

            actionable = precommit_approved
        except Exception as e:
            logger.debug(f"[RiskGateNode] TradePreCommitGate check non-fatal error: {e}")

    summary["portfolio_synthesis_approved"] = [sym for sym, r in actionable]

    # 6. Telegram Operator Proposal Notifications
    if actionable:
        await send_proposal_notifications(actionable)
        summary["execution"] = {"status": "pending_approval", "count": len(actionable)}
    else:
        logger.info("[Step 7b] No actionable buy/sell decisions this cycle.")
        summary["execution"] = {"status": "no_actionable_decisions"}

    # 7. Check for negotiable rejections for bidirectional re-planning
    is_negotiable = False
    rejection_feedback = None
    negotiable_items = []
    current_refinement = state.get("refinement_count", 0)

    if rejected_candidates and current_refinement < 2:
        from graph.nodes.plan_refinement_node import _is_reason_negotiable

        negotiable_items = [
            item for item in rejected_candidates
            if _is_reason_negotiable(" ".join(item.get("reasons", [])))
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
        "actionable_trades": actionable,
        "approved_trades": actionable,
        "is_negotiable_rejection": is_negotiable and not actionable,
        "negotiable_rejections": negotiable_items,
        "rejection_feedback": rejection_feedback,
    }
