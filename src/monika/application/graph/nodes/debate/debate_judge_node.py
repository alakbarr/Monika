# ==============================================================================
# File: graph/nodes/debate/debate_judge_node.py
# ==============================================================================

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.runnables.config import RunnableConfig

from monika.application.analysis.debate.adjustment_validator import validate_and_apply_judge_adjustments
from monika.application.analysis.debate.investment_judge import evaluate_debate
from monika.application.analysis.memory.decision_log import DecisionLogger
from monika.application.graph.nodes.debate.helpers import (
    resolve_debate_timeout,
    sync_facade_patches,
)
from monika.application.graph.state import TradingState
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import AssetAnalysis
from monika.infrastructure.providers.llm_factory import get_client_for_task

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

    configurable = (
        config.get("configurable") if isinstance(config, dict) else getattr(config, "configurable", None)
    ) or {}
    scheduler = (
        configurable.get("scheduler") if isinstance(configurable, dict) else getattr(configurable, "scheduler", None)
    )
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
        bear_dissent = deb.get("bear_dissent")
        bull_rebuttal = (
            deb.get("bull_rebuttal") or deb.get("bear_rebuttal") or deb.get("rebuttal") or deb.get("pro_rebuttal")
        )
        original_context = deb.get("original_context")
        analysis_id = r.get("analysis_id")

        if not original_context or not verified_bull_claim or not bear_dissent:
            missing_reason = (
                "missing_bull_advocacy"
                if not verified_bull_claim
                else ("missing_bear_dissent" if not bear_dissent else "missing_original_context")
            )
            logger.warning(f"[{sym}] {missing_reason} — failing closed.")
            return (
                sym,
                None,
                {
                    "final_decision": "avoid",
                    "decision": "wait",
                    "reason": missing_reason,
                    "risk_multiplier": 0.0,
                },
            )

        fact_sheet = deb.get("fact_sheet") or {}

        turn_timeout = resolve_debate_timeout(settings, judge_client)
        async with semaphore:
            try:
                try:
                    async with asyncio.timeout(turn_timeout):
                        verdict = await evaluate_debate(
                            judge_client,
                            sym,
                            original_context,
                            verified_bull_claim,
                            bear_dissent,
                            bull_rebuttal=bull_rebuttal,
                            fact_sheet=fact_sheet,
                        )
                except Exception as judge_err:
                    logger.warning(
                        f"[{sym}] Judge adjudication attempt 1 failed ({judge_err}). Retrying with existing task_role client..."
                    )
                    async with asyncio.timeout(turn_timeout):
                        verdict = await evaluate_debate(
                            judge_client,
                            sym,
                            original_context,
                            verified_bull_claim,
                            bear_dissent,
                            bull_rebuttal=bull_rebuttal,
                            fact_sheet=fact_sheet,
                        )

                # Enforce Specialized Swarm Desk Risk Veto if triggered
                desk_verdict = deb.get("desk_specialist_verdict") or fact_sheet.get("desk_specialist_verdict", {})
                if desk_verdict.get("risk_veto"):
                    veto_reasons = "; ".join(
                        desk_verdict.get("veto_reasons") or ["Specialized desk risk veto enforced"]
                    )
                    logger.warning(f"[{sym}] Enforcing Swarm Desk Risk Veto: {veto_reasons}")
                    verdict["final_decision"] = "avoid"
                    verdict["recommended_multiplier"] = 0.0
                    verdict["reason"] = (verdict.get("reason") or "") + f" [DESK VETO: {veto_reasons}]"

                async with get_session() as session:
                    ana = await session.get(AssetAnalysis, analysis_id)
                    if ana:
                        ana.debate_bull_thesis = json.dumps(verified_bull_claim) if verified_bull_claim else None
                        ana.debate_bear_dissent = json.dumps(bear_dissent) if bear_dissent else None
                        ana.debate_verdict = verdict.get("final_decision")
                        ana.debate_reason = verdict.get("reason") if verdict.get("reason") else None
                        ana.decision_source = "llm_debate"

                        entry_zone_data = json.loads(ana.entry_zone) if ana.entry_zone else {}
                        is_adj_valid, adj_error = await validate_and_apply_judge_adjustments(
                            session, ana, verdict, settings, entry_zone_data
                        )
                        has_adjustment = any(
                            verdict.get(k) is not None for k in ("adjusted_entry", "adjusted_sl", "adjusted_tp")
                        )
                        if has_adjustment and not is_adj_valid:
                            logger.warning(
                                f"[{sym}] Judge SL/TP adjustment DITOLAK: {adj_error}. Level asli Stage 2 dipertahankan."
                            )
                            ana.debate_reason = (
                                ana.debate_reason or ""
                            ) + f" [SYSTEM: Judge adjustment ditolak — {adj_error}. Level asli dipertahankan.]"
                        elif has_adjustment:
                            ana.was_debate_modified = True
                            adj_entry = verdict.get("adjusted_entry")
                            if adj_entry is not None:
                                entry_zone_data["price"] = float(adj_entry)
                                ana.entry_zone = json.dumps(entry_zone_data)
                                if isinstance(r, dict):
                                    r["entry_price"] = float(adj_entry)
                            adj_sl = verdict.get("adjusted_sl")
                            if adj_sl is not None:
                                ana.stop_loss = float(adj_sl)
                                if isinstance(r, dict):
                                    r["stop_loss"] = float(adj_sl)
                            adj_tp = verdict.get("adjusted_tp")
                            if adj_tp is not None:
                                ana.take_profit = float(adj_tp)
                                if isinstance(r, dict):
                                    r["take_profit"] = float(adj_tp)

                        adj_rm = verdict.get("risk_multiplier")
                        if adj_rm is not None:
                            new_rm = float(adj_rm)
                            if abs(new_rm - (ana.risk_multiplier or 1.0)) > 1e-4:
                                ana.was_debate_modified = True
                            ana.risk_multiplier = new_rm
                            if isinstance(r, dict):
                                r["risk_multiplier"] = new_rm

                        try:
                            from monika.infrastructure.database.event_store import TradingEventStore

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

                        final_dec = str(verdict.get("final_decision", "")).strip().lower()
                        curr_conf_score = getattr(ana, "confluence_score", None)
                        if final_dec in ("buy", "sell") and (
                            not isinstance(curr_conf_score, (int, float)) or curr_conf_score < 5
                        ):
                            precomp_sources = [
                                state.get("precomputed_confluence"),
                                deb.get("precomputed_confluence"),
                                r.get("precomputed_confluence") if isinstance(r, dict) else None,
                                original_context.get("precomputed_confluence")
                                if isinstance(original_context, dict)
                                else None,
                                fact_sheet.get("precomputed_confluence") if isinstance(fact_sheet, dict) else None,
                            ]
                            hydrated_conf: Optional[int] = None
                            score_keys = (
                                ("buy_score", "long_score", "score", "total_score", "confluence_score")
                                if final_dec == "buy"
                                else ("sell_score", "short_score", "score", "total_score", "confluence_score")
                            )
                            for src in precomp_sources:
                                if not isinstance(src, dict):
                                    continue
                                target_dict = src.get(sym) if isinstance(src.get(sym), dict) else src
                                if not isinstance(target_dict, dict):
                                    continue
                                for sk in score_keys:
                                    val = target_dict.get(sk)
                                    if isinstance(val, (int, float)) and not isinstance(val, bool) and val >= 5:
                                        hydrated_conf = int(val)
                                        break
                                if hydrated_conf is not None:
                                    break
                            if hydrated_conf is None or hydrated_conf < 5:
                                bull_s = int(
                                    state.get("bull_strength")
                                    or deb.get("bull_strength")
                                    or (verified_bull_claim or {}).get("strength_score")
                                    or 0
                                )
                                bear_s = int(
                                    state.get("bear_strength")
                                    or deb.get("bear_strength")
                                    or (bear_dissent or {}).get("risk_severity")
                                    or (bear_dissent or {}).get("strength_score")
                                    or 0
                                )
                                hydrated_conf = max(bull_s, bear_s, 6)
                            ana.confluence_score = hydrated_conf
                            if isinstance(r, dict):
                                r["confluence_score"] = hydrated_conf
                            verdict["confluence_score"] = hydrated_conf

                        try:
                            from monika.infrastructure.database.models import DebateTranscript

                            c_id = str(state.get("cycle_id") or f"cycle_{analysis_id}")
                            transcript_rec = DebateTranscript(
                                cycle_id=c_id,
                                symbol=sym,
                                timeframe=str(getattr(ana, "timeframe", "H1") or "H1"),
                                bull_perspective=verified_bull_claim,
                                bear_perspective=bear_dissent,
                                judge_adjudication=verdict,
                                final_decision=str(verdict.get("final_decision", "avoid")).lower(),
                                confidence=float(verdict.get("confidence") or getattr(ana, "confidence", 0.0) or 0.0),
                                confluence_score=float(getattr(ana, "confluence_score", 0.0) or 0.0),
                                risk_multiplier=float(verdict.get("risk_multiplier") or 0.0),
                                meta={
                                    "analysis_id": analysis_id,
                                    "bull_rebuttal": bull_rebuttal,
                                    "was_modified": getattr(ana, "was_debate_modified", False),
                                },
                            )
                            session.add(transcript_rec)
                        except Exception as dt_err:
                            logger.debug(f"[{sym}] Non-fatal error persisting DebateTranscript: {dt_err}")

                        await session.commit()
                        if final_dec in ("avoid", "wait"):
                            logger.warning(f"Investment Judge Rejected {sym} ({final_dec}): {verdict.get('reason')}")
                            await DecisionLogger.log_paper_whatif(
                                session=session,
                                analysis_id=int(analysis_id or ana.id),
                                symbol=sym,
                                decision=original_context.get("decision", "wait"),
                                confidence=ana.confidence or 0.0,
                                confluence_score=ana.confluence_score,
                                rationale=original_context.get("rationale", ""),
                                reason=f"Debate Judge Rejected: {verdict.get('reason')}",
                            )
                            ana.decision = "wait"
                            if isinstance(r, dict):
                                r["decision"] = "wait"
                            await session.commit()
                            return sym, None, verdict

                        if final_dec in ("buy", "sell"):
                            if str(ana.decision).lower() != final_dec:
                                ana.decision = final_dec
                                ana.was_debate_modified = True
                            if isinstance(r, dict):
                                r["decision"] = final_dec
                                if verdict.get("confidence"):
                                    r["confidence"] = float(verdict["confidence"])
                                    ana.confidence = float(verdict["confidence"])

                            def _num(v: Any) -> Optional[float]:
                                if isinstance(v, (int, float)) and not isinstance(v, bool):
                                    return float(v)
                                if isinstance(v, str):
                                    try:
                                        return float(v)
                                    except ValueError, TypeError:
                                        return None
                                return None

                            entry_px = (
                                _num(entry_zone_data.get("price") if isinstance(entry_zone_data, dict) else None)
                                or _num(getattr(ana, "price_at_analysis", None))
                                or _num(r.get("price_at_analysis") if isinstance(r, dict) else None)
                                or _num(r.get("entry_price") if isinstance(r, dict) else None)
                                or _num(
                                    original_context.get("price_at_analysis")
                                    if isinstance(original_context, dict)
                                    else None
                                )
                                or _num(
                                    original_context.get("entry_price") if isinstance(original_context, dict) else None
                                )
                                or _num(deb.get("curr_p"))
                            )
                            curr_sl = _num(getattr(ana, "stop_loss", None))
                            curr_tp = _num(getattr(ana, "take_profit", None))

                            def _is_dir_valid(
                                sl_v: Optional[float], tp_v: Optional[float], ep_v: Optional[float]
                            ) -> bool:
                                if sl_v is None or tp_v is None:
                                    return False
                                if ep_v is not None:
                                    return (sl_v < ep_v < tp_v) if final_dec == "buy" else (tp_v < ep_v < sl_v)
                                return (sl_v < tp_v) if final_dec == "buy" else (tp_v < sl_v)

                            has_valid_geom = _is_dir_valid(curr_sl, curr_tp, entry_px)

                            if not has_valid_geom:
                                prop_source = verified_bull_claim if final_dec == "buy" else bear_dissent
                                if isinstance(prop_source, dict):
                                    p_ent = _num(prop_source.get("proposed_entry"))
                                    p_sl = _num(prop_source.get("proposed_sl"))
                                    p_tp = _num(prop_source.get("proposed_tp"))
                                    cand_ep = p_ent if p_ent is not None else entry_px
                                    if _is_dir_valid(p_sl, p_tp, cand_ep):
                                        curr_sl = p_sl
                                        curr_tp = p_tp
                                        if p_ent is not None:
                                            entry_px = p_ent
                                            entry_zone_data["price"] = p_ent
                                            ana.entry_zone = json.dumps(entry_zone_data)
                                            if isinstance(r, dict):
                                                r["entry_price"] = p_ent
                                        has_valid_geom = True
                                    elif curr_sl is None and p_sl is not None:
                                        curr_sl = p_sl
                                    elif curr_tp is None and p_tp is not None:
                                        curr_tp = p_tp

                            if not has_valid_geom:
                                bracket_opts = (
                                    (r.get("bracket_options") if isinstance(r, dict) else None)
                                    or (
                                        original_context.get("bracket_options")
                                        if isinstance(original_context, dict)
                                        else None
                                    )
                                    or (fact_sheet.get("bracket_options") if isinstance(fact_sheet, dict) else None)
                                )
                                target_keys = (
                                    ("long_option_a", "LONG_OPTION_A")
                                    if final_dec == "buy"
                                    else ("short_option_b", "SHORT_OPTION_B")
                                )
                                chosen_b = None
                                if isinstance(bracket_opts, dict):
                                    for tk in target_keys:
                                        if isinstance(bracket_opts.get(tk), dict):
                                            chosen_b = bracket_opts[tk]
                                            break
                                if chosen_b is None and isinstance(r, dict):
                                    for tk in target_keys:
                                        if isinstance(r.get(tk), dict):
                                            chosen_b = r[tk]
                                            break
                                if isinstance(chosen_b, dict):
                                    b_ent = _num(chosen_b.get("entry"))
                                    b_sl = _num(chosen_b.get("stop_loss"))
                                    b_tp = _num(chosen_b.get("take_profit"))
                                    cand_ep = b_ent if b_ent is not None else entry_px
                                    if _is_dir_valid(b_sl, b_tp, cand_ep):
                                        curr_sl = b_sl
                                        curr_tp = b_tp
                                        if b_ent is not None:
                                            entry_px = b_ent
                                            entry_zone_data["price"] = b_ent
                                            ana.entry_zone = json.dumps(entry_zone_data)
                                            if isinstance(r, dict):
                                                r["entry_price"] = b_ent
                                        has_valid_geom = True

                            if not has_valid_geom and entry_px is not None:
                                if curr_sl is not None and curr_tp is not None:
                                    d1 = abs(entry_px - curr_sl)
                                    d2 = abs(curr_tp - entry_px)
                                    sl_dist = min(d1, d2) if (d1 > 0 and d2 > 0) else max(d1, d2, entry_px * 0.005)
                                    tp_dist = max(d1, d2) if (d1 > 0 and d2 > 0) else sl_dist * 1.55
                                    if tp_dist < sl_dist * 1.5:
                                        tp_dist = sl_dist * 1.55
                                else:
                                    atr_est = _num(
                                        (fact_sheet.get("atr") or fact_sheet.get("atr_14_h4"))
                                        if isinstance(fact_sheet, dict)
                                        else None
                                    ) or (entry_px * 0.005)
                                    sl_dist = atr_est * 1.05
                                    tp_dist = sl_dist * 1.55
                                if final_dec == "buy":
                                    curr_sl = round(entry_px - sl_dist, 5)
                                    curr_tp = round(entry_px + tp_dist, 5)
                                else:
                                    curr_sl = round(entry_px + sl_dist, 5)
                                    curr_tp = round(entry_px - tp_dist, 5)
                                has_valid_geom = True

                            if curr_sl is not None:
                                ana.stop_loss = float(curr_sl)
                                if isinstance(r, dict):
                                    r["stop_loss"] = float(curr_sl)
                            if curr_tp is not None:
                                ana.take_profit = float(curr_tp)
                                if isinstance(r, dict):
                                    r["take_profit"] = float(curr_tp)
                            if entry_px is not None and not entry_zone_data.get("price"):
                                entry_zone_data["price"] = float(entry_px)
                                ana.entry_zone = json.dumps(entry_zone_data)
                                if isinstance(r, dict) and not r.get("entry_price"):
                                    r["entry_price"] = float(entry_px)

                            await session.commit()

                    return sym, (sym, r), verdict
            except Exception as e:
                logger.error(f"[{sym}] Judge adjudication failed (failing closed to avoid risk): {e}", exc_info=True)
                return (
                    sym,
                    None,
                    {"decision": "wait", "reason": f"Judge adjudication failed: {e}", "risk_multiplier": 0.0},
                )

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
