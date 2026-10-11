# ==============================================================================
# File: graph/nodes/risk/quant_arbitration.py
# Monika Quant Alpha Opportunity Evaluation & Signal Arbitration Sub-Node
# ==============================================================================

"""
Evaluates algorithmic quant alphas from StrategyRegistry across candidate symbols
and executes signal arbitration to defend against LLM hallucination and promote valid setups.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from graph.nodes.risk.level_synthesizer import resolve_and_repair_levels

logger = logging.getLogger("TradingAgent.Graph.Risk.QuantArbitration")


async def run_quant_arbitration(
    scheduler: Any,
    actionable: List[Tuple[str, Dict[str, Any]]],
    asset_analyses: Dict[str, Any],
    state: Dict[str, Any],
) -> Tuple[List[Tuple[str, Dict[str, Any]]], List[Dict[str, Any]]]:
    """
    Applies SignalArbitrator defense, quant alpha opportunity evaluation,
    and market regime scaling to candidate trade proposals.
    """
    from analysis.arbitration.signal_arbitrator import SignalArbitrator
    from analysis.calculators.regime_classifier import classify_market_regime
    from analysis.strategies.decay_monitor import get_strategy_decay_monitor
    from analysis.strategies.registry import StrategyRegistry
    from database.db import get_session
    from database.models import AssetAnalysis, VIXData
    from sqlalchemy import select

    arbitrator = SignalArbitrator(scheduler.settings)
    decay_mon = get_strategy_decay_monitor()

    filtered_actionable: List[Tuple[str, Dict[str, Any]]] = []
    rejected_candidates: List[Dict[str, Any]] = []

    candidate_map: Dict[str, Tuple[Dict[str, Any], bool]] = {}
    for sym, r in actionable:
        candidate_map[sym] = (dict(r) if isinstance(r, dict) else r, True)
    for sym, r in asset_analyses.items():
        if sym not in candidate_map and isinstance(r, dict):
            candidate_map[sym] = (dict(r), False)

    async with get_session() as session:
        vix_val = 15.0
        try:
            vix_row = (await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(1))).scalar_one_or_none()
            if vix_row and vix_row.close:
                vix_val = float(vix_row.close)
        except Exception:
            pass

        for sym, (r, is_actionable_originally) in candidate_map.items():
            if r.get("arbitrated_by"):
                logger.info(f"[QuantArbitration] {sym} already arbitrated by {r.get('arbitrated_by')}, skipping duplicate arbitration.")
                if r.get("decision") in ("buy", "sell"):
                    filtered_actionable.append((sym, r))
                else:
                    if is_actionable_originally:
                        rejected_candidates.append({"symbol": sym, "trade": r, "reasons": [f"previously_arbitrated: {r.get('decision')}"]})
                continue

            try:
                regime_dict = await classify_market_regime(session, sym, scheduler.settings)
            except Exception:
                regime_dict = {}

            # Evaluate quant alphas from StrategyRegistry for this symbol & market regime
            active_quant_signal = None
            try:
                regime_str = regime_dict.get("regime") if isinstance(regime_dict, dict) else str(regime_dict or "")
                quant_signals = await StrategyRegistry.evaluate_all(
                    session=session,
                    symbol=sym,
                    settings=scheduler.settings,
                    current_regime=regime_str,
                )
                if quant_signals:
                    valid_sigs = [
                        s for s in quant_signals
                        if getattr(s, "valid", False) and getattr(s, "direction", None) in ("buy", "sell")
                    ]
                    if valid_sigs:
                        def _sig_prio(s):
                            strat_id = getattr(s, "strategy_id", "")
                            is_ready = decay_mon.is_live_ready(strat_id)
                            conf = float(getattr(s, "confidence", 0.0) or 0.0)
                            return (1 if is_ready else 0, conf)

                        valid_sigs.sort(key=_sig_prio, reverse=True)
                        active_quant_signal = valid_sigs[0]
                        strat_id = getattr(active_quant_signal, "strategy_id", "")
                        if not decay_mon.is_live_ready(strat_id):
                            active_quant_signal.meta = dict(getattr(active_quant_signal, "meta", {}))
                            active_quant_signal.meta["is_incubating"] = True
                            if not is_actionable_originally:
                                active_quant_signal = None
            except Exception as q_err:
                logger.debug(f"[QuantArbitration] Quant signal evaluation for {sym} non-fatal: {q_err}")

            llm_dec = {
                "decision": r.get("decision", "wait"),
                "confidence": float(r.get("confidence", 0.5) or 0.5),
                "risk_multiplier": float(r.get("risk_multiplier", 1.0) or 1.0),
                "entry_price": r.get("entry_price"),
                "stop_loss": r.get("stop_loss"),
                "take_profit": r.get("take_profit"),
                "rationale": r.get("rationale", ""),
                "decision_source": r.get("decision_source", "llm_debate" if is_actionable_originally else "stage2_per_asset"),
            }

            arb_res = await arbitrator.arbitrate(
                session=session,
                symbol=sym,
                quant_signal=active_quant_signal,
                llm_decision=llm_dec,
                vix_level=vix_val,
                regime_info=regime_dict,
            )

            if arb_res.decision in ("avoid", "wait"):
                if is_actionable_originally:
                    logger.info(f"[QuantArbitration] {sym} suppressed by SignalArbitrator: {arb_res.arbitration_reason}")
                    rejected_candidates.append({"symbol": sym, "trade": r, "reasons": [f"signal_arbitrator: {arb_res.arbitration_reason}"]})
            else:
                r["risk_multiplier"] = arb_res.risk_multiplier
                if arb_res.selected_source == "concordant":
                    r["confidence"] = arb_res.confidence
                    r["was_concordant"] = True
                    r["decision_source"] = "concordant"
                    if active_quant_signal and getattr(active_quant_signal, "strategy_id", None):
                        r["source_strategy_id"] = active_quant_signal.strategy_id
                elif arb_res.selected_source == "quant":
                    r["decision"] = arb_res.decision
                    r["confidence"] = arb_res.confidence
                    if arb_res.entry_price:
                        r["entry_price"] = arb_res.entry_price
                    if arb_res.stop_loss:
                        r["stop_loss"] = arb_res.stop_loss
                    if arb_res.take_profit:
                        r["take_profit"] = arb_res.take_profit
                    r["decision_source"] = f"quant_{arb_res.meta.get('strategy_id', 'alpha')}"
                    if active_quant_signal and getattr(active_quant_signal, "strategy_id", None):
                        r["source_strategy_id"] = active_quant_signal.strategy_id
                    if not is_actionable_originally:
                        logger.info(f"[QuantArbitration] Quant strategy {r.get('source_strategy_id')} promoted {sym} from WAIT to {arb_res.decision.upper()} via SignalArbitrator")

                analysis_id = r.get("analysis_id")
                ana = await session.get(AssetAnalysis, analysis_id) if analysis_id else None

                # Single-pass level resolution and geometry repair
                if str(r.get("decision", "")).upper() in ("BUY", "SELL"):
                    await resolve_and_repair_levels(
                        session=session,
                        scheduler=scheduler,
                        symbol=sym,
                        r=r,
                        ana=ana,
                        state_asset_analyses=state.get("asset_analyses"),
                    )

                # Persist arbitrated decision and levels to DB AssetAnalysis
                if ana:
                    ana.decision = r["decision"]
                    ana.confidence = r["confidence"]
                    ana.risk_multiplier = r["risk_multiplier"]
                    if r.get("entry_price") is not None:
                        ana.entry_price = r["entry_price"]
                    if r.get("stop_loss") is not None:
                        ana.stop_loss = r["stop_loss"]
                    if r.get("take_profit") is not None:
                        ana.take_profit = r["take_profit"]
                    if r.get("decision_source"):
                        ana.decision_source = r["decision_source"]
                    if r.get("arbitration_reason"):
                        ana.arbitration_reason = r["arbitration_reason"]
                    if r.get("source_strategy_id"):
                        ana.source_strategy_id = r["source_strategy_id"]
                    await session.commit()
                    logger.info(f"[QuantArbitration] Persisted arbitrated trade {sym} ({ana.decision.upper()}) to AssetAnalysis #{ana.id}")

                filtered_actionable.append((sym, r))
                if isinstance(state.get("asset_analyses"), dict) and sym in state["asset_analyses"]:
                    if isinstance(state["asset_analyses"][sym], dict):
                        state["asset_analyses"][sym].update(r)

    return filtered_actionable, rejected_candidates
