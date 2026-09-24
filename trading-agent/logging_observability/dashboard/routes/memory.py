# ==============================================================================
# File: logging_observability/dashboard/routes/memory.py
# Description: Memory Browsing Endpoints (Reflections, Lessons, Playbooks, Search)
# ==============================================================================

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select, or_, desc

from database.db import AsyncSessionLocal
from database.models import DecisionReflection, CandidateLesson, PlaybookRuleAttribution
from logging_observability.dashboard.rbac import require_role, Role

logger = logging.getLogger("TradingAgent.DashboardAPI.Memory")

memory_router = APIRouter(prefix="/api/memory", tags=["Memory"])


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=200, description="Keyword or phrase to search across reflections and lessons")
    limit: int = Field(50, ge=1, le=200)
    symbol: Optional[str] = None


@memory_router.get("/reflections")
async def get_reflections(
    symbol: Optional[str] = Query(None, description="Filter by asset symbol (e.g. XAUUSD)"),
    limit: int = Query(50, ge=1, le=200),
    profitable_only: Optional[bool] = Query(None, description="Filter by profitable trades"),
    whatif_only: Optional[bool] = Query(None, description="Filter by paper what-if reflections"),
    search: Optional[str] = Query(None, description="Keyword search in reflection/lesson text"),
) -> List[Dict[str, Any]]:
    """Retrieve historical post-trade reflections, lessons learned, and what-if analyses."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(DecisionReflection).order_by(desc(DecisionReflection.id))

            if symbol:
                stmt = stmt.where(DecisionReflection.symbol.ilike(f"%{symbol.strip()}%"))
            if profitable_only is True:
                stmt = stmt.where(DecisionReflection.was_profitable.is_(True))
            elif profitable_only is False:
                stmt = stmt.where(DecisionReflection.was_profitable.is_(False))
            if whatif_only is True:
                stmt = stmt.where(DecisionReflection.is_paper_whatif.is_(True))
            elif whatif_only is False:
                stmt = stmt.where(DecisionReflection.is_paper_whatif.is_(False))
            if search and search.strip():
                term = f"%{search.strip()}%"
                stmt = stmt.where(
                    or_(
                        DecisionReflection.reflection_text.ilike(term),
                        DecisionReflection.specific_lesson.ilike(term),
                        DecisionReflection.rationale_summary.ilike(term),
                        DecisionReflection.next_trade_adjustment.ilike(term),
                    )
                )

            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            reflections = result.scalars().all()

            out = []
            for r in reflections:
                out.append({
                    "id": r.id,
                    "symbol": r.symbol,
                    "decision": r.decision,
                    "confidence": r.confidence,
                    "confluence_score": r.confluence_score,
                    "rationale_summary": r.rationale_summary,
                    "outcome_pnl_usd": r.outcome_pnl_usd,
                    "holding_hours": r.holding_hours,
                    "exit_reason": r.exit_reason,
                    "was_profitable": r.was_profitable,
                    "reflection_text": r.reflection_text,
                    "next_trade_adjustment": r.next_trade_adjustment,
                    "specific_lesson": r.specific_lesson,
                    "lesson_tags": r.lesson_tags,
                    "alpha_return": r.alpha_return,
                    "process_was_sound": r.process_was_sound,
                    "outcome_process_classification": r.outcome_process_classification,
                    "macro_thesis_correct": r.macro_thesis_correct,
                    "debate_verdict": r.debate_verdict,
                    "debate_summary": r.debate_summary,
                    "is_paper_whatif": r.is_paper_whatif,
                    "whatif_reason": r.whatif_reason,
                })
            return out
    except Exception as e:
        logger.error(f"Error fetching decision reflections: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch decision reflections.")


@memory_router.get("/lessons")
async def get_lessons(
    symbol: Optional[str] = Query(None, description="Filter by asset symbol"),
    status: Optional[str] = Query(None, description="Filter by status (shadow, promoted, rejected)"),
    limit: int = Query(50, ge=1, le=200),
) -> List[Dict[str, Any]]:
    """Retrieve candidate and promoted empirical trading lessons."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(CandidateLesson).order_by(desc(CandidateLesson.id))

            if symbol:
                stmt = stmt.where(CandidateLesson.symbol.ilike(f"%{symbol.strip()}%"))
            if status:
                stmt = stmt.where(CandidateLesson.status == status.strip().lower())

            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            lessons = result.scalars().all()

            out = []
            for item in lessons:
                out.append({
                    "id": item.id,
                    "symbol": item.symbol,
                    "lesson_text": item.lesson_text,
                    "status": item.status,
                    "proposed_at": item.proposed_at.isoformat() if item.proposed_at else None,
                    "evaluated_trades_count": item.evaluated_trades_count,
                    "win_rate_delta": item.win_rate_delta,
                    "sharpe_delta": item.sharpe_delta,
                    "promoted_at": item.promoted_at.isoformat() if item.promoted_at else None,
                    "rejection_reason": item.rejection_reason,
                    "condition_tags": item.condition_tags,
                })
            return out
    except Exception as e:
        logger.error(f"Error fetching candidate lessons: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch candidate lessons.")


@memory_router.get("/playbooks")
async def get_playbooks(limit: int = Query(50, ge=1, le=200)) -> List[Dict[str, Any]]:
    """Retrieve playbook rule attributions and performance evolutions."""
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(PlaybookRuleAttribution).order_by(desc(PlaybookRuleAttribution.id)).limit(limit)
            result = await session.execute(stmt)
            records = result.scalars().all()

            out = []
            for p in records:
                out.append({
                    "id": p.id,
                    "rule_hash": p.rule_hash,
                    "symbol": p.symbol,
                    "rule_text": p.rule_text,
                    "status": p.status,
                    "times_triggered": p.times_triggered,
                    "wins_count": p.wins_count,
                    "losses_count": p.losses_count,
                    "total_pnl": p.total_pnl,
                    "win_rate": p.win_rate,
                    "last_triggered_at": p.last_triggered_at.isoformat() if p.last_triggered_at else None,
                    "promoted_at": p.promoted_at.isoformat() if p.promoted_at else None,
                    "deprecated_at": p.deprecated_at.isoformat() if p.deprecated_at else None,
                    "deprecation_reason": p.deprecation_reason,
                })
            return out
    except Exception as e:
        logger.warning(f"Error fetching playbook attributions: {e}")
        return []


@memory_router.post("/search")
async def search_memory(payload: MemorySearchRequest) -> Dict[str, Any]:
    """Unified search over reflections and lessons learned."""
    term = f"%{payload.query.strip()}%"
    reflections_out = []
    lessons_out = []

    try:
        async with AsyncSessionLocal() as session:
            # Query reflections
            r_stmt = (
                select(DecisionReflection)
                .where(
                    or_(
                        DecisionReflection.reflection_text.ilike(term),
                        DecisionReflection.specific_lesson.ilike(term),
                        DecisionReflection.rationale_summary.ilike(term),
                        DecisionReflection.next_trade_adjustment.ilike(term),
                    )
                )
                .order_by(desc(DecisionReflection.id))
                .limit(payload.limit)
            )
            if payload.symbol:
                r_stmt = r_stmt.where(DecisionReflection.symbol.ilike(f"%{payload.symbol.strip()}%"))

            r_res = await session.execute(r_stmt)
            for r in r_res.scalars().all():
                reflections_out.append({
                    "id": r.id,
                    "symbol": r.symbol,
                    "decision": r.decision,
                    "outcome_pnl_usd": r.outcome_pnl_usd,
                    "reflection_text": r.reflection_text,
                    "specific_lesson": r.specific_lesson,
                    "next_trade_adjustment": r.next_trade_adjustment,
                    "was_profitable": r.was_profitable,
                })

            # Query lessons
            l_stmt = (
                select(CandidateLesson)
                .where(
                    or_(
                        CandidateLesson.lesson_text.ilike(term),
                        CandidateLesson.condition_tags.ilike(term),
                    )
                )
                .order_by(desc(CandidateLesson.id))
                .limit(payload.limit)
            )
            if payload.symbol:
                l_stmt = l_stmt.where(CandidateLesson.symbol.ilike(f"%{payload.symbol.strip()}%"))

            l_res = await session.execute(l_stmt)
            for l in l_res.scalars().all():
                lessons_out.append({
                    "id": l.id,
                    "symbol": l.symbol,
                    "lesson_text": l.lesson_text,
                    "status": l.status,
                    "win_rate_delta": l.win_rate_delta,
                })

        return {
            "query": payload.query,
            "total_matches": len(reflections_out) + len(lessons_out),
            "reflections": reflections_out,
            "lessons": lessons_out,
        }
    except Exception as e:
        logger.error(f"Error during memory search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Memory search failed.")


class PlaybookRollbackRequest(BaseModel):
    target_hash: Optional[str] = None
    reason: Optional[str] = "Manual operator rollback from dashboard"


@memory_router.get("/playbooks/{name}/history")
async def get_playbook_history(name: str) -> List[Dict[str, Any]]:
    """Retrieve version mutation history for a specific playbook."""
    from analysis.memory.playbook_ledger import PlaybookLedger
    ledger = PlaybookLedger()
    return ledger.list_history(playbook_name=name)


@memory_router.post("/playbooks/{name}/rollback")
@require_role(Role.ADMIN)
async def rollback_playbook(name: str, request: Request, payload: Optional[PlaybookRollbackRequest] = None) -> Dict[str, Any]:
    """Roll back a playbook rule to an immediate prior or specified SHA-256 target blob."""
    from analysis.memory.playbook_ledger import PlaybookLedger
    ledger = PlaybookLedger()
    target_hash = payload.target_hash if payload else None
    success = ledger.rollback(playbook_name=name, target_hash=target_hash)
    if not success:
        raise HTTPException(status_code=400, detail=f"Rollback failed for '{name}'. Verify history exists.")
    return {"status": "success", "message": f"Playbook '{name}' rolled back successfully.", "target_hash": target_hash}
