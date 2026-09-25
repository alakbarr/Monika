# ==============================================================================
# File: graph/nodes/debate/debate_judge_node.py
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
from analysis.debate.investment_judge import evaluate_debate
from analysis.debate.adjustment_validator import validate_and_apply_judge_adjustments
from analysis.memory.decision_log import DecisionLogger
from graph.nodes.debate.helpers import sync_facade_patches

logger = logging.getLogger("TradingAgent.Graph.Debate.DebateJudgeNode")


async def debate_judge_node(state: TradingState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
    """
    Sub-agent node: Debate Judge.
    Mengevaluasi argumen bull vs bear, mengesahkan modifikasi SL/TP/Entry,
    dan menyaring trade yang ditolak ('avoid').
    """
    sync_facade_patches()
    actionable = state.get("actionable_trades", [])
    if not actionable:
        return {}

    configurable = (config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)) or {}
    scheduler = configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    settings = scheduler.settings if scheduler else {}
    debate_cfg = settings.get("agent_architecture", {})

    if not debate_cfg.get("enable_debate", True):
        return {}

    logger.info(f"[Debate:Judge] Adjudicating {len(actionable)} trades...")
    debate_states = dict(state.get("debate_states", {}))
    investment_verdicts = dict(state.get("investment_verdicts", {}))
    judge_client = get_client_for_task("debate_judge", settings)

    surviving_trades: List[Tuple[str, dict]] = []
    semaphore = asyncio.Semaphore(3)

    async def _process_single(sym: str, r: dict):
        deb = debate_states.get(sym, {})
        verified_bull_claim = deb.get("verified_bull_claim")
        bear_dissent = deb.get("bear_dissent") or {}
        bull_rebuttal = deb.get("bull_rebuttal")
        original_context = deb.get("original_context")
        analysis_id = r.get("analysis_id")

        if not original_context or not verified_bull_claim:
            return sym, (sym, r), None

        async with semaphore:
            try:
                verdict = await evaluate_debate(
                    judge_client, sym, original_context, verified_bull_claim, bear_dissent, bull_rebuttal=bull_rebuttal
                )

                async with get_session() as session:
                    ana = await session.get(AssetAnalysis, analysis_id)
                    if ana:
                        ana.debate_bull_thesis = json.dumps(verified_bull_claim) if verified_bull_claim else None
                        ana.debate_bear_dissent = json.dumps(bear_dissent) if bear_dissent else None
                        ana.debate_verdict = verdict.get('final_decision')
                        ana.debate_reason = verdict.get('reason') if verdict.get('reason') else None
                        ana.decision_source = "llm_debate"

                        entry_zone_data = json.loads(ana.entry_zone) if ana.entry_zone else {}
                        is_adj_valid, adj_error = await validate_and_apply_judge_adjustments(
                            session, ana, verdict, settings, entry_zone_data
                        )
                        has_adjustment = any(
                            verdict.get(k) is not None for k in ('adjusted_entry', 'adjusted_sl', 'adjusted_tp')
                        )
                        if has_adjustment and not is_adj_valid:
                            logger.warning(f"[{sym}] Judge SL/TP adjustment DITOLAK: {adj_error}. Level asli Stage 2 dipertahankan.")
                            ana.debate_reason = (ana.debate_reason or '') + f' [SYSTEM: Judge adjustment ditolak — {adj_error}. Level asli dipertahankan.]'
                        elif has_adjustment:
                            ana.was_debate_modified = True
                            adj_entry = verdict.get('adjusted_entry')
                            if adj_entry is not None:
                                entry_zone_data['price'] = float(adj_entry)
                                ana.entry_zone = json.dumps(entry_zone_data)
                                if isinstance(r, dict):
                                    r['entry_price'] = float(adj_entry)
                            adj_sl = verdict.get('adjusted_sl')
                            if adj_sl is not None:
                                ana.stop_loss = float(adj_sl)
                                if isinstance(r, dict):
                                    r['stop_loss'] = float(adj_sl)
                            adj_tp = verdict.get('adjusted_tp')
                            if adj_tp is not None:
                                ana.take_profit = float(adj_tp)
                                if isinstance(r, dict):
                                    r['take_profit'] = float(adj_tp)

                        adj_rm = verdict.get('risk_multiplier')
                        if adj_rm is not None:
                            new_rm = float(adj_rm)
                            if abs(new_rm - (ana.risk_multiplier or 1.0)) > 1e-4:
                                ana.was_debate_modified = True
                            ana.risk_multiplier = new_rm
                            if isinstance(r, dict):
                                r['risk_multiplier'] = new_rm

                        try:
                            from database.event_store import TradingEventStore
                            await TradingEventStore.emit(
                                session=session,
                                event_type="analysis.debate.verdict",
                                payload={
                                    "symbol": sym,
                                    "analysis_id": analysis_id,
                                    "final_decision": verdict.get("final_decision"),
                                    "verdict": verdict,
                                },
                                correlation_id=state.get("cycle_id", f"debate_{analysis_id}"),
                                actor="debate_judge",
                            )
                        except Exception:
                            pass

                        await session.commit()

                        if verdict.get("final_decision") == "avoid":
                            logger.warning(f"Investment Judge Rejected {sym}: {verdict.get('reason')}")
                            await DecisionLogger.log_paper_whatif(
                                session=session,
                                analysis_id=int(analysis_id or ana.id),
                                symbol=sym,
                                decision=original_context.get('decision', 'wait'),
                                confidence=ana.confidence or 0.0,
                                confluence_score=ana.confluence_score,
                                rationale=original_context.get('rationale', ''),
                                reason=f"Debate Judge Rejected: {verdict.get('reason')}"
                            )
                            ana.decision = 'wait'
                            await session.commit()
                            return sym, None, verdict

                    return sym, (sym, r), verdict
            except Exception as e:
                logger.error(f"[{sym}] Judge adjudication failed: {e}", exc_info=True)
                return sym, (sym, r), None

    tasks = [_process_single(sym, r) for sym, r in actionable]
    results = await asyncio.gather(*tasks)

    for sym, survived, verdict in results:
        if verdict:
            investment_verdicts[sym] = verdict
        if survived:
            surviving_trades.append(survived)

    summary = dict(state.get("summary", {}))
    rejected_by_judge = [sym for sym, survived, _ in results if not survived]
    raw_rejected = summary.get("debate_rejected")
    existing_rejected = list(raw_rejected) if isinstance(raw_rejected, list) else []
    summary["debate_rejected"] = existing_rejected + [s for s in rejected_by_judge if s not in existing_rejected]
    summary["debate_approved"] = [sym for sym, survived, _ in results if survived]

    return {
        "summary": summary,
        "actionable_trades": surviving_trades,
        "investment_verdicts": investment_verdicts,
        "debate_states": debate_states,
    }
