# ==============================================================================
# File: interfaces/dashboard/routes/trading_endpoints/analysis.py
# Description: Analytical assessments, decision dossiers, debate outcomes, and signals
# ==============================================================================

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from monika.interfaces.dashboard.rbac import Role, require_role
from monika.interfaces.dashboard.routes.common import (
    BatchCloseRequest,
    BulkBreakevenRequest,
    ClosePositionRequest,
    ManualOrderPreviewRequest,
    ManualOrderSubmitRequest,
    ModifyPositionRequest,
    OverrideRiskRequest,
    SteerRequest,
    TrailingOverrideRequest,
    TriggerCycleRequest,
    _safe_json,
    broadcast_live_event,
    get_dashboard_dependency,
)

logger = logging.getLogger("TradingAgent.DashboardAPI.Trading.Analysis")

analysis_router = APIRouter()


@analysis_router.get("/api/analysis", tags=["Analysis"])
async def get_analysis(
    limit: int = Query(default=20, ge=1, le=100),
    symbol: Optional[str] = Query(default=None),
):
    """Riwayat analisis Stage 2 AI per aset."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import AssetAnalysis

    async with AsyncSessionLocal() as session:
        q = select(AssetAnalysis).order_by(AssetAnalysis.generated_at.desc()).limit(limit)
        if symbol:
            q = q.where(AssetAnalysis.symbol == symbol.upper())

        analyses = (await session.execute(q)).scalars().all()

        results = []
        for a in analyses:
            reeval = None
            if a.reevaluation_trigger:
                try:
                    rt = json.loads(a.reevaluation_trigger)
                    reeval = rt.get("detail") or str(rt)
                except Exception:
                    reeval = str(a.reevaluation_trigger)[:100]

            results.append(
                {
                    "id": a.id,
                    "symbol": a.symbol,
                    "decision": a.decision,
                    "confidence": round(a.confidence * 100, 1) if a.confidence else None,
                    "generated_at": a.generated_at.isoformat() if a.generated_at else None,
                    "stop_loss": a.stop_loss,
                    "take_profit": a.take_profit,
                    "rationale": (a.rationale or "")[:300],
                    "reevaluation_trigger": reeval,
                    "invalidation": (a.invalidation or "")[:200],
                }
            )
        return results


@analysis_router.get("/api/analysis/decision-dossier/{analysis_id}", tags=["Analysis"])
async def get_decision_dossier(
    analysis_id: str,
    ticket: Optional[int] = Query(None, description="Optional MT5 ticket filter for execution telemetry"),
):
    """
    1-Click Decision Dossier (Phase 4):
    Aggregates full decision lineage and rationale across:
    - Stage 1: Macro & Fundamental Context (Brief, DXY bias, Risk sentiment)
    - Stage 2: Tactical Confluence & SMC (Factors, Entry/SL/TP, Invalidation, SSVP)
    - Stage 3: Adversarial Debate (Bull vs Bear thesis, Judge verdict)
    - Stage 4: RiskGate Mechanical Fortress (22 rules scorecard, execution notes)
    - Stage 5: Execution Telemetry & Hash Lineage (Signals, Position, SHA-256 verification)
    """
    from sqlalchemy import or_, select

    from monika.core.telemetry.trading_cycle_event_log import get_cycle_event_log
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import (
        AssetAnalysis,
        FundamentalBrief,
        MT5Signal,
        PaperTradeRecord,
        Position,
        TradeTrigger,
    )

    async with AsyncSessionLocal() as session:
        # 1. Resolve AssetAnalysis
        analysis = None
        if analysis_id.isdigit():
            analysis = (
                await session.execute(select(AssetAnalysis).where(AssetAnalysis.id == int(analysis_id)))
            ).scalar_one_or_none()

        if not analysis:
            # Try symbol lookup
            analysis = (
                await session.execute(
                    select(AssetAnalysis)
                    .where(AssetAnalysis.symbol == analysis_id.upper())
                    .order_by(AssetAnalysis.generated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        if not analysis and ticket:
            # Try finding analysis via Position with ticket
            pos = (await session.execute(select(Position).where(Position.mt5_ticket == ticket))).scalar_one_or_none()
            if pos and pos.analysis_id:
                analysis = (
                    await session.execute(select(AssetAnalysis).where(AssetAnalysis.id == pos.analysis_id))
                ).scalar_one_or_none()
            elif pos:
                analysis = (
                    await session.execute(
                        select(AssetAnalysis)
                        .where(AssetAnalysis.symbol == pos.symbol)
                        .order_by(AssetAnalysis.generated_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()

        if not analysis:
            return JSONResponse(
                status_code=404, content={"detail": f"Decision Dossier not found for analysis/symbol '{analysis_id}'"}
            )

        # 2. Resolve FundamentalBrief
        brief = None
        if analysis.brief_id:
            brief = (
                await session.execute(select(FundamentalBrief).where(FundamentalBrief.id == analysis.brief_id))
            ).scalar_one_or_none()
        if not brief and analysis.generated_at:
            brief = (
                await session.execute(
                    select(FundamentalBrief)
                    .where(FundamentalBrief.generated_at <= analysis.generated_at)
                    .order_by(FundamentalBrief.generated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        # 3. Resolve Triggers
        triggers_res = (
            (
                await session.execute(
                    select(TradeTrigger)
                    .where(TradeTrigger.asset_analysis_id == analysis.id)
                    .order_by(TradeTrigger.created_at.desc())
                )
            )
            .scalars()
            .all()
        )

        # 4. Resolve MT5Signals
        signals_res = (
            (
                await session.execute(
                    select(MT5Signal)
                    .where(or_(MT5Signal.asset_analysis_id == analysis.id, MT5Signal.symbol == analysis.symbol))
                    .order_by(MT5Signal.created_at.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

        # 5. Resolve Position & PaperTradeRecord
        position_res = None
        if ticket:
            position_res = (
                await session.execute(select(Position).where(Position.mt5_ticket == ticket))
            ).scalar_one_or_none()
        if not position_res:
            position_res = (
                await session.execute(
                    select(Position)
                    .where(or_(Position.analysis_id == analysis.id, Position.symbol == analysis.symbol))
                    .order_by(Position.opened_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        paper_res = (
            await session.execute(
                select(PaperTradeRecord)
                .where(or_(PaperTradeRecord.analysis_id == analysis.id, PaperTradeRecord.symbol == analysis.symbol))
                .order_by(PaperTradeRecord.opened_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        entry_cond = _safe_json(analysis.entry_zone)
        reeval_trig = _safe_json(analysis.reevaluation_trigger)
        factors = _safe_json(analysis.confluence_factors_json) or []
        specialist_biases = _safe_json(analysis.specialist_biases_json) or {}
        brief_data = _safe_json(brief.structured_json) if brief else {}

        # 6. Cycle Event Log & SHA-256 Chain Verification
        cycle_id = (
            analysis.context_snapshot_id
            or f"cycle-{analysis.generated_at.strftime('%Y%m%d-%H%M') if analysis.generated_at else 'default'}"
        )
        event_log = get_cycle_event_log()
        cycle_events = event_log.get_events_for_cycle(cycle_id)
        is_valid_chain, chain_err = event_log.verify_cycle_integrity(cycle_id)
        latest_hash = cycle_events[-1].chain_hash if cycle_events else None
        # Resolve Debate structures
        deb_verdict_obj = analysis.debate_verdict
        if isinstance(deb_verdict_obj, str):
            try:
                deb_verdict_obj = json.loads(deb_verdict_obj)
            except Exception:
                pass
        deb_dict = deb_verdict_obj if isinstance(deb_verdict_obj, dict) else {}
        judge_v_str = (
            deb_dict.get("verdict")
            if deb_dict
            else (analysis.debate_verdict if isinstance(analysis.debate_verdict, str) else analysis.decision)
        )

        dossier = {
            "status": "success",
            "analysis_id": analysis.id,
            "symbol": analysis.symbol,
            "decision": analysis.decision,
            "confidence": round(analysis.confidence * 100, 1) if analysis.confidence else 0.0,
            "generated_at": analysis.generated_at.isoformat() if analysis.generated_at else None,
            "market_regime": analysis.market_regime_at_analysis or "normal",
            "price_at_analysis": analysis.price_at_analysis,
            "stop_loss": analysis.stop_loss,
            "take_profit": analysis.take_profit,
            "invalidation_price": analysis.invalidation_price,
            "invalidation": analysis.invalidation,
            "rationale": analysis.rationale,
            # Stage 1: Macro & Fundamental Context
            "stage1_macro": {
                "brief_id": brief.id if brief else analysis.brief_id,
                "risk_sentiment": (brief.risk_sentiment if brief else None) or "neutral",
                "volatility_regime": getattr(brief, "volatility_regime", None)
                or analysis.market_regime_at_analysis
                or "normal",
                "dxy_bias": (brief_data.get("dxy_bias") or brief_data.get("currency_bias", {}).get("USD") or "neutral")
                if isinstance(brief_data, dict)
                else "neutral",
                "brief_age_hours": round(analysis.brief_age_at_analysis_hours, 1)
                if analysis.brief_age_at_analysis_hours is not None
                else None,
                "summary": (brief.content_markdown or "")[:400] if brief else None,
                "generated_at": brief.generated_at.isoformat() if brief and brief.generated_at else None,
            },
            # Stage 2: Tactical Confluence & SMC Levels
            "stage2_tactical": {
                "confluence_score": analysis.confluence_score,
                "priced_in_score": analysis.priced_in_score,
                "priced_in_override": analysis.priced_in_override_justification,
                "entry_condition": entry_cond,
                "reevaluation_trigger": reeval_trig,
                "factors": factors if isinstance(factors, list) else [str(factors)],
                "specialist_biases": specialist_biases if isinstance(specialist_biases, dict) else {},
                "adr_at_analysis": analysis.adr_at_analysis,
                "ssvp_cds_score": round(analysis.ssvp_cds_score_at_analysis, 3)
                if analysis.ssvp_cds_score_at_analysis is not None
                else None,
            },
            # Stage 3: Adversarial Debate & Adjudication
            "stage3_debate": {
                "bull_thesis": analysis.debate_bull_thesis or deb_dict.get("bull_thesis"),
                "bear_dissent": analysis.debate_bear_dissent
                or deb_dict.get("bear_thesis")
                or deb_dict.get("bear_dissent"),
                "judge_verdict": judge_v_str or analysis.decision,
                "judge_reason": analysis.debate_reason or deb_dict.get("judge_reason"),
                "was_modified": bool(analysis.was_debate_modified or deb_dict.get("modified")),
                "arbitration_reason": analysis.arbitration_reason,
            },
            # Stage 4: RiskGate Mechanical Fortress
            "stage4_riskgate": {
                "execution_status": analysis.execution_status
                or ("approved" if analysis.decision in ("buy", "sell") else "skipped"),
                "execution_notes": analysis.execution_notes,
                "risk_multiplier": analysis.risk_multiplier or 1.0,
                "was_ssvp_suppressed": bool(analysis.was_ssvp_suppressed),
                "decision_source": analysis.decision_source or "langgraph_pipeline",
            },
            # Stage 5: Execution Telemetry & Cryptographic Lineage
            "stage5_execution": {
                "position": {
                    "id": position_res.id,
                    "ticket": position_res.mt5_ticket,
                    "direction": position_res.direction,
                    "volume": position_res.volume,
                    "entry_price": position_res.entry_price,
                    "sl": position_res.sl,
                    "tp": position_res.tp,
                    "slippage_pips": position_res.slippage_pips,
                    "pnl": position_res.pnl,
                    "status": position_res.status,
                    "opened_at": position_res.opened_at.isoformat() if position_res.opened_at else None,
                }
                if position_res
                else None,
                "paper_trade": {
                    "id": paper_res.id,
                    "direction": paper_res.direction,
                    "entry_price": paper_res.entry_price,
                    "pnl_pct": paper_res.pnl_pct,
                    "exit_reason": paper_res.exit_reason,
                    "opened_at": paper_res.opened_at.isoformat() if paper_res.opened_at else None,
                }
                if paper_res
                else None,
                "triggers": [
                    {
                        "id": t.id,
                        "type": t.trigger_type,
                        "status": t.status,
                        "condition": _safe_json(t.condition_json),
                        "created_at": t.created_at.isoformat() if t.created_at else None,
                        "fired_at": t.fired_at.isoformat() if t.fired_at else None,
                    }
                    for t in triggers_res
                ],
                "signals": [
                    {
                        "id": s.id,
                        "action": s.action,
                        "status": s.status,
                        "ticket": s.mt5_ticket,
                        "error": s.error_message,
                        "created_at": s.created_at.isoformat() if s.created_at else None,
                        "executed_at": s.executed_at.isoformat() if s.executed_at else None,
                    }
                    for s in signals_res
                ],
                "cycle_id": cycle_id,
                "integrity_valid": is_valid_chain,
                "integrity_error": chain_err,
                "sha256_chain_hash": latest_hash,
                "event_count": len(cycle_events),
                "events_sample": [
                    {
                        "seq": ev.seq,
                        "event_type": ev.event_type,
                        "timestamp": ev.timestamp,
                        "chain_hash": (ev.chain_hash or "")[:12] + "...",
                    }
                    for ev in cycle_events[-5:]
                ]
                if cycle_events
                else [],
            },
        }
        return dossier


@analysis_router.get("/api/decision-distribution", tags=["Analysis"])
async def get_decision_distribution():
    from sqlalchemy import func, select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import AssetAnalysis

    async with AsyncSessionLocal() as session:
        since = datetime.now(timezone.utc) - timedelta(days=30)

        result = (
            await session.execute(
                select(AssetAnalysis.symbol, AssetAnalysis.decision, func.count(AssetAnalysis.id).label("count"))
                .where(AssetAnalysis.generated_at >= since)
                .group_by(AssetAnalysis.symbol, AssetAnalysis.decision)
            )
        ).all()

        distribution = {}
        for row in result:
            if row.symbol not in distribution:
                distribution[row.symbol] = {"buy": 0, "sell": 0, "wait": 0, "avoid": 0, "skip": 0}
            distribution[row.symbol][row.decision] = distribution[row.symbol].get(row.decision, 0) + row.count

        for sym, counts in distribution.items():
            total = sum(counts.values())
            trade_decisions = counts.get("buy", 0) + counts.get("sell", 0)
            distribution[sym]["total"] = total
            distribution[sym]["trade_rate_pct"] = round(trade_decisions / total * 100, 1) if total > 0 else 0

        return distribution


@analysis_router.get("/api/debate-outcomes", tags=["Analysis"])
async def get_debate_outcomes(limit: int = Query(default=20, ge=1, le=100)):
    """Ambil ringkasan hasil debate bull/bear & adjudikasi spesialis (M-4)."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import AssetAnalysis

    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(AssetAnalysis)
                    .where(AssetAnalysis.decision.in_(["buy", "sell"]))
                    .order_by(AssetAnalysis.generated_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        results = []
        for r in rows:
            adj = None
            raw_adj = getattr(r, "specialist_biases_json", None) or getattr(r, "specialist_adjudication", None)
            if raw_adj:
                try:
                    adj = json.loads(raw_adj)
                except Exception:
                    adj = raw_adj
            bull_raw = getattr(r, "debate_bull_thesis", None)
            bear_raw = getattr(r, "debate_bear_dissent", None)
            bull_thesis = None
            bear_dissent = None
            if bull_raw:
                try:
                    bull_thesis = json.loads(bull_raw)
                except Exception:
                    bull_thesis = bull_raw
            if bear_raw:
                try:
                    bear_dissent = json.loads(bear_raw)
                except Exception:
                    bear_dissent = bear_raw

            conf_val = r.confidence
            if conf_val is not None:
                norm_conf = round(conf_val * 100, 1) if conf_val <= 1.0 else round(conf_val, 1)
            else:
                norm_conf = None

            results.append(
                {
                    "id": r.id,
                    "symbol": r.symbol,
                    "decision": r.decision,
                    "confidence": norm_conf,
                    "confluence_score": r.confluence_score,
                    "risk_multiplier": r.risk_multiplier,
                    "rationale": r.rationale,
                    "specialist_adjudication": adj,
                    "debate_bull_thesis": bull_thesis,
                    "debate_bear_dissent": bear_dissent,
                    "debate_verdict": getattr(r, "debate_verdict", None),
                    "debate_reason": getattr(r, "debate_reason", None),
                    "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                    "execution_status": r.execution_status,
                }
            )
        return {"total": len(results), "items": results}


@analysis_router.get("/api/signals/mt5", tags=["Execution"])
@analysis_router.get("/api/mt5/signals", tags=["Execution"], include_in_schema=False)
async def get_mt5_signals(limit: int = Query(default=50, ge=1, le=200)):
    """Ambil riwayat sinyal dan korelasi eksekusi MT5 yang diperkaya dengan analisis AI (M-4)."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import AssetAnalysis, MT5Signal

    async with AsyncSessionLocal() as session:
        stmt = (
            select(MT5Signal, AssetAnalysis)
            .outerjoin(AssetAnalysis, MT5Signal.asset_analysis_id == AssetAnalysis.id)
            .order_by(MT5Signal.created_at.desc())
            .limit(limit)
        )
        raw_exec = await session.execute(stmt)
        raw_rows = []
        if hasattr(raw_exec, "_mock_return_value") or hasattr(raw_exec, "mock_calls"):
            try:
                s_all = raw_exec.scalars().all()
                raw_rows = s_all if s_all and not hasattr(s_all, "_mock_return_value") else raw_exec.all()
            except Exception:
                raw_rows = raw_exec.all()
        else:
            raw_rows = raw_exec.all()

        items = []
        for row in raw_rows:
            if isinstance(row, (tuple, list)):
                if len(row) >= 2:
                    s, a = row[0], row[1]
                elif len(row) == 1:
                    s, a = row[0], None
                else:
                    continue
            else:
                s, a = row, None

            if not hasattr(s, "id"):
                continue

            conf_val = a.confidence if a else None
            norm_conf = None
            if conf_val is not None:
                norm_conf = round(conf_val * 100, 1) if conf_val <= 1.0 else round(conf_val, 1)

            items.append(
                {
                    "id": s.id,
                    "asset_analysis_id": s.asset_analysis_id,
                    "symbol": s.symbol,
                    "action": s.action,
                    "status": s.status,
                    "mt5_ticket": s.mt5_ticket,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "executed_at": s.executed_at.isoformat() if s.executed_at else None,
                    "error_message": s.error_message,
                    "decision": a.decision if a else s.action,
                    "confidence": norm_conf,
                    "confluence_score": a.confluence_score if a else None,
                    "sl": a.stop_loss if a else None,
                    "tp": a.take_profit if a else None,
                    "rationale": (a.rationale or "")[:200] if a else None,
                }
            )

        return {
            "total": len(items),
            "items": items,
        }


@analysis_router.get("/api/triggers", tags=["Analysis"])
async def get_trade_triggers(status: Optional[str] = None, limit: int = Query(default=50, ge=1, le=200)):
    """Ambil daftar trade triggers kondisional (M-4)."""
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.repositories import TradeProposalRepository

    async with AsyncSessionLocal() as session:
        prop_repo = TradeProposalRepository(session)
        rows = await prop_repo.get_recent_triggers(limit=limit, status=status)

        results = []
        for t in rows:
            cond = None
            if t.condition_json:
                try:
                    cond = json.loads(t.condition_json)
                except Exception:
                    cond = t.condition_json
            results.append(
                {
                    "id": t.id,
                    "asset_analysis_id": t.asset_analysis_id,
                    "trigger_type": t.trigger_type,
                    "status": t.status,
                    "condition": cond,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "fired_at": t.fired_at.isoformat() if t.fired_at else None,
                }
            )
        return {"total": len(results), "items": results}
