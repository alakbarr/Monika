import logging
from typing import Dict, Any, List, Optional
from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig
from database.db import get_session
from database.models import AssetAnalysis

logger = logging.getLogger("TradingAgent.Graph.PlanRefinementNode")


def _is_reason_negotiable(reason: str) -> bool:
    """Determine if a rejection reason can be resolved via parameter refinement."""
    r_lower = str(reason).lower()
    non_negotiable = [
        "calendar proximity", "high-impact", "crisis", "vix >=", "drawdown",
        "stale market data", "symbol wr <", "permanent_error", "blacklisted"
    ]
    if any(tok in r_lower for tok in non_negotiable):
        return False

    negotiable = [
        "geometry", "sl", "stop loss", "tp", "take profit", "lot", "heat",
        "sizing", "risk_multiplier", "drift", "staleness", "cone", "rr", "ratio"
    ]
    return any(tok in r_lower for tok in negotiable)


async def plan_refinement_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    LangGraph Plan Refinement Node (Phase 3: Bidirectional LangGraph Re-Planning Loop).

    When RiskGate rejects trade proposals for negotiable parameters (such as SL too tight,
    lot size exceeding portfolio heat, or entry price drift), this node acts as an
    Adjudicator to refine the proposal parameters and route back into RiskGate (up to 2 iterations).
    """
    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    settings = scheduler.settings if scheduler else {}

    refinement_count = state.get("refinement_count", 0) + 1
    rejection_feedback = state.get("rejection_feedback") or {}
    rejected_items = rejection_feedback.get("rejected_items", [])
    summary = dict(state.get("summary", {}))

    logger.info(f"[PlanRefinementNode] Running plan refinement iteration {refinement_count}/2 for {len(rejected_items)} rejected items")

    if refinement_count > 2 or not rejected_items:
        logger.warning(f"[PlanRefinementNode] Refinement limit reached ({refinement_count}) or empty items. Halting refinement.")
        return {
            "actionable_trades": [],
            "refinement_count": refinement_count,
            "is_negotiable_rejection": False,
            "rejection_feedback": None,
            "summary": summary,
        }

    refined_trades: List[tuple] = []

    async with get_session() as session:
        for item in rejected_items:
            sym = item.get("symbol")
            trade = dict(item.get("trade") or {})
            reasons = item.get("reasons") or []
            analysis_id = trade.get("analysis_id")

            if not _is_reason_negotiable(" ".join(reasons)):
                logger.info(f"[PlanRefinementNode] Trade {sym} rejection reasons are non-negotiable: {reasons}")
                continue

            entry = float(trade.get("entry_price") or trade.get("price") or 0.0)
            sl = float(trade.get("stop_loss") or trade.get("sl") or 0.0)
            tp = float(trade.get("take_profit") or trade.get("tp") or 0.0)
            risk_mult = float(trade.get("risk_multiplier") or 1.0)
            decision = str(trade.get("decision") or "").lower()

            adjusted = False
            adjustment_notes = []

            # 1. Adjust for portfolio heat / lot size / correlation reduction
            if any(tok in " ".join(reasons).lower() for tok in ["heat", "lot", "sizing", "risk_multiplier", "correlation"]):
                new_mult = round(max(0.1, risk_mult * 0.5), 3)
                trade["risk_multiplier"] = new_mult
                adjusted = True
                adjustment_notes.append(f"Risk multiplier scaled from {risk_mult} -> {new_mult} to satisfy portfolio heat.")

            # 2. Adjust for SL too tight, geometry, or noise cone
            if any(tok in " ".join(reasons).lower() for tok in ["sl", "stop loss", "geometry", "cone"]):
                risk_dist = abs(entry - sl) if entry > 0 and sl > 0 else 0.0
                if risk_dist <= 0:
                    risk_dist = entry * 0.0050  # 50 pips fallback

                # Widen SL by 30% to clear noise cone
                new_risk_dist = risk_dist * 1.30
                if decision == "buy":
                    new_sl = round(entry - new_risk_dist, 5)
                    new_tp = round(entry + (new_risk_dist * 2.0), 5)
                else:
                    new_sl = round(entry + new_risk_dist, 5)
                    new_tp = round(entry - (new_risk_dist * 2.0), 5)

                trade["stop_loss"] = new_sl
                trade["take_profit"] = new_tp
                adjusted = True
                adjustment_notes.append(f"SL widened to {new_sl} and TP adjusted to {new_tp} (R:R 2.0:1) to clear noise cone.")

            # 3. Adjust for entry price drift / staleness
            if any(tok in " ".join(reasons).lower() for tok in ["drift", "staleness"]):
                live_price = item.get("current_price")
                if live_price and float(live_price) > 0:
                    drift_offset = float(live_price) - entry
                    new_entry = float(live_price)
                    trade["entry_price"] = new_entry
                    trade["stop_loss"] = round(sl + drift_offset, 5)
                    trade["take_profit"] = round(tp + drift_offset, 5)
                    adjusted = True
                    adjustment_notes.append(f"Entry recalibrated to live price {new_entry} (offset {drift_offset:+.5f}).")

            if adjusted:
                # Update DB AssetAnalysis record
                if analysis_id:
                    try:
                        ana = await session.get(AssetAnalysis, analysis_id)
                        if ana:
                            ana.stop_loss = trade.get("stop_loss")
                            ana.take_profit = trade.get("take_profit")
                            ana.risk_multiplier = trade.get("risk_multiplier")
                            ana.was_debate_modified = True
                            curr_notes = ana.execution_notes or ""
                            ana.execution_notes = (curr_notes + f" | [Refined Iteration {refinement_count}]: {'; '.join(adjustment_notes)}").strip()
                            await session.commit()
                    except Exception as db_err:
                        logger.debug(f"[PlanRefinementNode] Failed to update AssetAnalysis {analysis_id}: {db_err}")

                refined_trades.append((sym, trade))
                logger.info(f"[PlanRefinementNode] Successfully refined {sym}: {'; '.join(adjustment_notes)}")

    summary["plan_refinements"] = {
        "iteration": refinement_count,
        "refined_count": len(refined_trades),
        "refined_symbols": [s for s, _ in refined_trades],
    }

    return {
        "actionable_trades": refined_trades,
        "refinement_count": refinement_count,
        "is_negotiable_rejection": False,
        "rejection_feedback": None,
        "summary": summary,
    }
