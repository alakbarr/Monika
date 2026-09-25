import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from graph.state import TradingState
from langchain_core.runnables.config import RunnableConfig

logger = logging.getLogger("TradingAgent.Graph.RiskGateNode")

async def _ai_portfolio_synthesis(actionable: list, session, settings, market_regime: str = 'normal', as_of: Optional[datetime] = None, user_market_intel: Optional[list] = None) -> dict:
    """
    Use cheap AI to do portfolio-level synthesis when multiple trades proposed.
    """
    from analysis.providers.llm_factory import get_client_for_task
    from database.models import FundamentalBrief, VIXData
    from sqlalchemy import select
    from datetime import datetime
    
    # Build summary
    trade_summaries = []
    proposed_trades = []
    for sym, r in actionable:
        trade_summaries.append(
            f"- {sym} {r.get('decision','?').upper()}: "
            f"confidence={r.get('confidence',0):.0%}, "
            f"analysis_id={r.get('analysis_id','?')}"
        )
        proposed_trades.append({'symbol': sym, 'decision': r.get('decision', 'unknown')})

    # [NEW] Inject Pairwise Correlations (Dynamic)
    from utils.market.dynamic_correlation import get_rolling_correlation
    corr_context = []
    for i in range(len(proposed_trades)):
        for j in range(i+1, len(proposed_trades)):
            sym1, sym2 = proposed_trades[i]['symbol'], proposed_trades[j]['symbol']
            try:
                corr, source = await get_rolling_correlation(session, sym1, sym2)
                d1, d2 = proposed_trades[i]['decision'], proposed_trades[j]['decision']
                aligned = (d1 == d2 and corr > 0) or (d1 != d2 and corr < 0)
                if abs(corr) >= 0.3:
                    corr_context.append(f"{sym1}({d1}) & {sym2}({d2}): Correlation={corr:.2f}[{source}] -> "
                                        f"{'MULTIPLYING RISK' if aligned else 'HEDGING'}")
            except Exception as e:
                pass

    # Operator Market Intelligence & Directives Context
    intel_context = []
    if user_market_intel:
        for item in user_market_intel:
            raw_syms = item.get("affected_symbols")
            if isinstance(raw_syms, list):
                syms = ", ".join(raw_syms) or "ALL"
            else:
                syms = str(raw_syms or "ALL")
            intel_context.append(
                f"- ID #{item.get('id')} [{item.get('intel_type', '').upper()}]: {item.get('title')}\n"
                f"  Directive: {item.get('directive', 'neutral')} | Scope: {syms} | Target Cycle: {item.get('target_cycle', 'continuous')}\n"
                f"  Summary: {item.get('summary')}"
            )
    
    # Get brief and VIX for context
    brief_stmt = select(FundamentalBrief)
    if as_of:
        brief_stmt = brief_stmt.where(FundamentalBrief.generated_at <= as_of)
    brief = (await session.execute(
        brief_stmt.order_by(FundamentalBrief.generated_at.desc()).limit(1)
    )).scalar_one_or_none()
    
    vix_stmt = select(VIXData)
    if as_of:
        vix_stmt = vix_stmt.where(VIXData.date <= as_of)
    vix = (await session.execute(
        vix_stmt.order_by(VIXData.date.desc()).limit(1)
    )).scalar_one_or_none()
    
    prompt = f"""Portfolio Review: {len(actionable)} trades proposed simultaneously.

Proposed Trades:
{chr(10).join(trade_summaries)}

Macro Context:
- Market Regime (from early cycle check): {market_regime}
- Risk sentiment: {brief.risk_sentiment if brief else 'unknown'}
- Brief confidence: {brief.confidence if brief else 'unknown'}
- VIX: {vix.close if vix else 'unknown'}

Operator Market Intelligence & Directives:
{chr(10).join(intel_context) if intel_context else '- (No active operator directives)'}

Pairwise Correlation Assessment:
{chr(10).join(corr_context) if corr_context else '- (No relevant pairs found or only 1 trade)'}

Question: Should we execute ALL these trades simultaneously, or REDUCE the portfolio?

Consider:
1. Correlation between assets
2. Overall portfolio risk
3. Macro conditions and Operator directives (e.g. avoid_trade, favor_buy/sell)

Respond in JSON:
{{
  "recommendation": "execute_all" or "reduce",
  "keep": ["SYMBOL1", "SYMBOL2"],
  "reasoning": "brief explanation"
}}
"""
    PORTFOLIO_SYNTHESIS_SCHEMA = {
        'type': 'object',
        'properties': {
            'recommendation': {'type': 'string', 'enum': ['execute_all', 'reduce']},
            'keep': {'type': 'array', 'items': {'type': 'string'}},
            'size_adjustments': {
                'type': 'object',
                'description': 'Optional per-symbol risk multiplier (0.1-1.0) as an alternative '
                                'to fully dropping a trade — prefer this over hard exclusion when '
                                'the correlation risk is moderate rather than severe.',
                'additionalProperties': {'type': 'number'}
            },
            'reasoning': {'type': 'string'},
        },
        'required': ['recommendation', 'keep', 'reasoning'],
    }

    client = get_client_for_task("portfolio_synthesis", settings)
    result = await client.classify_json(prompt=prompt, schema=PORTFOLIO_SYNTHESIS_SCHEMA, temperature=0.0)
    return result or {'recommendation': 'execute_all',
                       'keep': [t['symbol'] for t in proposed_trades],
                       'size_adjustments': {}, 'reasoning': 'fallback: synthesis call failed'}

async def risk_gate_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Node untuk mengevaluasi trade melalui Portfolio Synthesis dan Risk Gate.
    Mengirim notifikasi Telegram untuk trade yang lolos.
    
    NOTE: Task role 'risk_gate_check' di settings.yaml digunakan untuk LLM 
    risk-debate analysts (conservative/aggressive/neutral), BUKAN untuk 
    class/node ini yang lebih bersifat deterministik dan mensintesis portfolio.
    """
    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else None
    summary = state.get("summary", {})
    summary = state.get("summary", {})
    actionable = list(state.get("actionable_trades", []) or [])
    asset_analyses = dict(state.get("asset_analyses", {}) or {})

    if scheduler is None:
        logger.error("Scheduler not found in config")
        return {"summary": summary, "actionable_trades": [], "approved_trades": []}
    
    rejected_candidates: List[Dict[str, Any]] = []

    # Apply SignalArbitrator defense, quant alpha opportunity evaluation, and regime scaling
    try:
        from analysis.arbitration.signal_arbitrator import SignalArbitrator
        from database.models import VIXData, AssetAnalysis
        from analysis.calculators.regime_classifier import classify_market_regime
        from database.db import get_session
        from sqlalchemy import select
        
        arbitrator = SignalArbitrator(scheduler.settings)
        filtered_actionable = []

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

            from analysis.strategies.registry import StrategyRegistry
            from analysis.strategies.decay_monitor import get_strategy_decay_monitor

            decay_mon = get_strategy_decay_monitor()

            for sym, (r, is_actionable_originally) in candidate_map.items():
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
                except Exception as q_err:
                    logger.debug(f"[RiskGateNode] Quant signal evaluation for {sym} non-fatal: {q_err}")

                llm_dec = {
                    "decision": r.get("decision", "wait"),
                    "confidence": float(r.get("confidence", 0.5) or 0.5),
                    "risk_multiplier": float(r.get("risk_multiplier", 1.0) or 1.0),
                    "entry_price": r.get("entry_price"),
                    "stop_loss": r.get("stop_loss"),
                    "take_profit": r.get("take_profit"),
                    "rationale": r.get("rationale", ""),
                    "decision_source": r.get("decision_source", "llm_debate" if is_actionable_originally else "stage2_per_asset")
                }

                arb_res = await arbitrator.arbitrate(
                    session=session,
                    symbol=sym,
                    quant_signal=active_quant_signal,
                    llm_decision=llm_dec,
                    vix_level=vix_val,
                    regime_info=regime_dict
                )

                if arb_res.decision in ("avoid", "wait"):
                    if is_actionable_originally:
                        logger.info(f"[RiskGateNode] {sym} suppressed by SignalArbitrator: {arb_res.arbitration_reason}")
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
                            logger.info(f"[RiskGateNode] Quant strategy {r.get('source_strategy_id')} promoted {sym} from WAIT to {arb_res.decision.upper()} via SignalArbitrator")

                    # Persist arbitrated decision and levels to DB AssetAnalysis
                    analysis_id = r.get("analysis_id")
                    if analysis_id:
                        ana = await session.get(AssetAnalysis, analysis_id)
                        if ana:
                            ana.decision = r["decision"]
                            ana.confidence = r["confidence"]
                            ana.risk_multiplier = r["risk_multiplier"]
                            if r.get("entry_price") is not None:
                                try:
                                    ez = json.loads(ana.entry_zone) if ana.entry_zone else {}
                                except Exception:
                                    ez = {}
                                ez["price"] = r["entry_price"]
                                ana.entry_zone = json.dumps(ez)
                            if r.get("stop_loss") is not None:
                                ana.stop_loss = r["stop_loss"]
                            if r.get("take_profit") is not None:
                                ana.take_profit = r["take_profit"]
                            if r.get("decision_source"):
                                ana.decision_source = r["decision_source"]
                            if r.get("source_strategy_id"):
                                ana.source_strategy_id = r["source_strategy_id"]
                            await session.commit()
                            logger.info(f"[RiskGateNode] Persisted arbitrated trade {sym} ({ana.decision.upper()}) to AssetAnalysis #{ana.id}")

                    filtered_actionable.append((sym, r))
                    
        actionable = filtered_actionable
    except Exception as e:
        logger.debug(f"SignalArbitrator check in RiskGateNode non-fatal error: {e}")

    if not actionable:
        return {"summary": summary, "actionable_trades": [], "approved_trades": []}

    logger.info(f"[Step 7a] Stage 3 Portfolio Synthesis for {len(actionable)} trades...")
    
    # Apply deterministic correlation filter
    try:
        from risk.portfolio_correlation_gate import filter_correlated_proposals
        from database.db import get_session
        from analysis.memory.decision_log import DecisionLogger
        from database.models import AssetAnalysis
        
        async with get_session() as session:
            kept_actionable, rejected_actionable = await filter_correlated_proposals(session, actionable)
        
        if rejected_actionable:
            for sym, r, reason in rejected_actionable:
                rejected_candidates.append({"symbol": sym, "trade": r, "reasons": [f"correlation_gate: {reason}"]})
            async with get_session() as session:
                for sym, r, reason in rejected_actionable:
                    try:
                        ana = await session.get(AssetAnalysis, r["analysis_id"])
                        ctx_id = ana.context_snapshot_id if ana else None
                        cds = ana.ssvp_cds_score_at_analysis if ana else None
                        
                        await DecisionLogger.log_paper_whatif(
                            session,
                            analysis_id=r["analysis_id"],
                            symbol=sym,
                            decision=r.get("decision", "wait"),
                            confidence=r.get("confidence", 0),
                            confluence_score=None,
                            rationale=reason,
                            reason="correlation_gate_rejected",
                            context_snapshot_id=ctx_id,
                            ssvp_cds_score=cds
                        )
                    except Exception as e:
                        logger.error(f"Failed to log whatif for {sym}: {e}")
        actionable = kept_actionable
    except Exception as e:
        logger.debug(f'Correlation filter failed (non-fatal): {e}')

        # Determine if we should synthesize or just keep them
        if len(actionable) >= 3:
            try:
                from database.db import get_session
                async with get_session() as session:
                    portfolio_summary = await _ai_portfolio_synthesis(
                        actionable, session, scheduler.settings,
                        market_regime=state.get('market_regime', 'normal'),
                        user_market_intel=state.get('user_market_intel'),
                    )
                if portfolio_summary.get('recommendation') == 'reduce':
                    size_adj = portfolio_summary.get('size_adjustments', {})
                    keep_symbols = portfolio_summary.get('keep', [sym for sym, _ in actionable])

                    if size_adj:
                        from database.db import get_session as _gs_adj
                        from database.models import AssetAnalysis as _AA
                        async with _gs_adj() as adj_session:
                            for sym, r in actionable:
                                if sym in size_adj and sym in keep_symbols:
                                    try:
                                        mult = max(0.1, min(1.0, float(size_adj[sym])))  # clamp defensively
                                    except (TypeError, ValueError):
                                        continue
                                    ana = await adj_session.get(_AA, r['analysis_id'])
                                    if ana:
                                        new_mult = round((ana.risk_multiplier or 1.0) * mult, 3)
                                        ana.risk_multiplier = new_mult
                                        r['risk_multiplier'] = new_mult
                                        logger.info(f'[PortfolioSynthesis] {sym} risk_multiplier -> {new_mult} (persisted)')
                            await adj_session.commit()
                    
                    # Log removed trades as paper what-ifs
                    removed_trades = [(sym, r) for sym, r in actionable if sym not in keep_symbols]
                    if removed_trades:
                        for sym, r in removed_trades:
                            rejected_candidates.append({"symbol": sym, "trade": r, "reasons": ["portfolio_synthesis: heat reduced"]})
                        try:
                            from analysis.memory.decision_log import DecisionLogger
                            from database.models import AssetAnalysis
                            async with get_session() as session:
                                for sym, r in removed_trades:
                                    ana = await session.get(AssetAnalysis, r["analysis_id"])
                                    ctx_id = ana.context_snapshot_id if ana else None
                                    cds = ana.ssvp_cds_score_at_analysis if ana else None
                                    
                                    await DecisionLogger.log_paper_whatif(
                                        session,
                                        analysis_id=r["analysis_id"],
                                        symbol=sym,
                                        decision=r.get("decision", "wait"),
                                        confidence=r.get("confidence", 0),
                                        confluence_score=None,
                                        rationale="Portfolio synthesis reduced trade.",
                                        reason="portfolio_synthesis_rejected",
                                        context_snapshot_id=ctx_id,
                                        ssvp_cds_score=cds
                                    )
                        except Exception as e:
                            logger.error(f"Failed to log whatif for removed trades: {e}")

                    actionable = [(sym, r) for sym, r in actionable if sym in keep_symbols]
                    logger.info(f'AI portfolio synthesis reduced trades to: {[s for s,_ in actionable]}')
            except Exception as e:
                logger.debug(f'AI portfolio synthesis failed (non-fatal): {e}')

        # Deterministic Trade Pre-Commit Gate
        try:
            from analysis.validators.precommit_gate import TradePreCommitGate
            precommit_gate = TradePreCommitGate(scheduler.settings)
            precommit_approved = []
            
            from database.db import get_session as _gs_pre
            async with _gs_pre() as pre_session:
                for sym, r in actionable:
                    passed, failures = await precommit_gate.verify_precommit(pre_session, r, sym)
                    if passed:
                        precommit_approved.append((sym, r))
                    else:
                        logger.warning(f"[PreCommitGate] Suppressed {sym} from execution: {failures}")
                        rejected_candidates.append({"symbol": sym, "trade": r, "reasons": failures})
                        try:
                            from analysis.memory.decision_log import DecisionLogger
                            from database.models import AssetAnalysis as _AA_pre
                            ana = await pre_session.get(_AA_pre, r.get("analysis_id"))
                            ctx_id = ana.context_snapshot_id if ana else None
                            cds = ana.ssvp_cds_score_at_analysis if ana else None
                            await DecisionLogger.log_paper_whatif(
                                pre_session,
                                analysis_id=r["analysis_id"],
                                symbol=sym,
                                decision=r.get("decision", "wait"),
                                confidence=r.get("confidence", 0),
                                confluence_score=None,
                                rationale=f"PreCommit Gate blocked: {'; '.join(failures)}",
                                reason="precommit_gate_rejected",
                                context_snapshot_id=ctx_id,
                                ssvp_cds_score=cds
                            )
                        except Exception as whatif_err:
                            logger.debug(f"Precommit whatif log error: {whatif_err}")
                            
            actionable = precommit_approved
        except Exception as e:
            logger.debug(f"TradePreCommitGate check non-fatal error: {e}")
                
        summary["portfolio_synthesis_approved"] = [sym for sym, r in actionable]
        
        try:
            from utils.infra.notifier import AgentNotifier
            notifier = AgentNotifier()
            for sym, r in actionable:
                analysis_id = r["analysis_id"]
                decision = r.get("decision", "unknown").upper()
                confidence = r.get("confidence", 0)
                
                from database.db import get_session as _gs
                async with _gs() as session:
                    from database.models import AssetAnalysis
                    from sqlalchemy import select as _sel
                    ana = (await session.execute(_sel(AssetAnalysis).where(AssetAnalysis.id == analysis_id))).scalar_one_or_none()
                    
                if not ana: continue
                    
                msg = (
                    f"📊 <b>Trade Proposal — {sym}</b>\n\n"
                    f"Decision: <b>{decision}</b>\n"
                    f"Confidence: {confidence:.0%}\n"
                    f"Entry: {ana.entry_zone or 'market'}\n"
                    f"SL: {ana.stop_loss}\n"
                    f"TP: {ana.take_profit}\n\n"
                    f"Rationale: {(ana.rationale or '')[:200]}...\n\n"
                    f"<i>Use /approve {analysis_id} to execute or /reject {analysis_id} to skip.</i>"
                )
                await notifier.send_info(msg)
        except Exception as e:
            logger.error(f"Failed to send trade proposal notification: {e}")
            
        summary["execution"] = {"status": "pending_approval", "count": len(actionable)}
    else:
        logger.info("[Step 7b] No actionable buy/sell decisions this cycle.")
        summary["execution"] = {"status": "no_actionable_decisions"}

    # Phase 3: Check for negotiable rejections for bidirectional re-planning
    is_negotiable = False
    rejection_feedback = None
    current_refinement = state.get("refinement_count", 0)

    if not actionable and rejected_candidates and current_refinement < 2:
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
                f"Routing to plan_refinement_node (iteration {current_refinement + 1}/2)."
            )
            summary["execution"] = {"status": "routing_to_plan_refinement", "rejected_count": len(negotiable_items)}

    return {
        "summary": summary,
        "actionable_trades": actionable,
        "approved_trades": actionable,
        "is_negotiable_rejection": is_negotiable,
        "rejection_feedback": rejection_feedback,
    }
