import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List, Dict
from datetime import datetime, timezone
from database.models import DecisionReflection, AssetAnalysis

logger = logging.getLogger(__name__)

class DecisionLogger:
    """Mencatat keputusan AI (Real dan Paper What-Ifs) ke tabel DecisionReflection."""
    
    @staticmethod
    async def log_decision(
        session: AsyncSession,
        analysis_id: int,
        symbol: str,
        decision: str,
        confidence: float,
        confluence_score: Optional[int],
        rationale: str,
        context_snapshot_id: Optional[str] = None,
        ssvp_cds_score: Optional[float] = None
    ) -> Optional[int]:
        """Mencatat keputusan Real Trade yang akan/sedang dieksekusi."""
        try:
            new_log = DecisionReflection(
                analysis_id=analysis_id,
                symbol=symbol,
                decision=decision,
                confidence=confidence,
                confluence_score=confluence_score,
                rationale_summary=rationale,
                is_paper_whatif=False,
                status='pending',
                context_snapshot_id=context_snapshot_id,
                context_cds_score=ssvp_cds_score
            )
            session.add(new_log)
            from database.safe_ops import safe_commit
            await safe_commit(session, label="log_decision_real")
            return new_log.id
        except Exception as e:
            logger.error(f"Gagal log decision (Real): {e}")
            await session.rollback()
            return None

    @staticmethod
    async def log_paper_whatif(
        session: AsyncSession,
        analysis_id: int,
        symbol: str,
        decision: str,
        confidence: float,
        confluence_score: Optional[int],
        rationale: str,
        reason: str,
        context_snapshot_id: Optional[str] = None,
        ssvp_cds_score: Optional[float] = None
    ) -> Optional[int]:
        """Mencatat keputusan yang TIDAK dieksekusi (Paper What-If)."""
        try:
            # Ambil entry price dari AssetAnalysis
            analysis = await session.get(AssetAnalysis, analysis_id)
            entry_price = analysis.price_at_analysis if analysis else None

            new_log = DecisionReflection(
                analysis_id=analysis_id,
                symbol=symbol,
                decision=decision,
                confidence=confidence,
                confluence_score=confluence_score,
                rationale_summary=rationale,
                is_paper_whatif=True,
                whatif_reason=reason,
                whatif_entry_price=entry_price,
                status='pending_whatif',
                context_snapshot_id=context_snapshot_id,
                context_cds_score=ssvp_cds_score
            )
            session.add(new_log)
            from database.safe_ops import safe_commit
            await safe_commit(session, label="log_decision_whatif")
            return new_log.id
        except Exception as e:
            logger.error(f"Gagal log decision (What-If): {e}")
            await session.rollback()
            return None
            
    @staticmethod
    async def get_recent_lessons(session: AsyncSession, symbol: str, limit: int = 3) -> Dict:
        """Mengambil refleksi/lessons terbaru untuk di-inject ke prompt. Real diprioritaskan."""
        try:
            # Real trades (prioritas utama)
            stmt_real = select(DecisionReflection).where(
                DecisionReflection.symbol == symbol,
                DecisionReflection.status == 'resolved',
                DecisionReflection.is_paper_whatif == False
            ).order_by(DecisionReflection.resolved_at.desc()).limit(limit)
            
            # Paper what-ifs (prioritas kedua)
            stmt_whatif = select(DecisionReflection).where(
                DecisionReflection.symbol == symbol,
                DecisionReflection.status == 'resolved',
                DecisionReflection.is_paper_whatif == True
            ).order_by(DecisionReflection.resolved_at.desc()).limit(limit)
            
            real_results = (await session.execute(stmt_real)).scalars().all()
            whatif_results = (await session.execute(stmt_whatif)).scalars().all()
            
            return {
                "real_trades": [
                    {
                        "decision": r.decision,
                        "confidence": r.confidence,
                        "profitable": r.was_profitable,
                        "process_was_sound": r.process_was_sound,
                        "outcome_process_classification": r.outcome_process_classification,
                        "reflection": r.reflection_text if not (r.process_was_sound and not r.was_profitable) else "Loss occurred under sound process (normal market variance — maintain discipline, avoid ad-hoc curve fitting).",
                        "tags": r.lesson_tags,
                        "next_adjustment": getattr(r, 'next_trade_adjustment', None) if not (r.process_was_sound and not r.was_profitable) else None
                    } for r in real_results
                ],
                "paper_whatifs": [
                    {
                        "decision": r.decision,
                        "reason_rejected": r.whatif_reason,
                        "direction_correct": r.whatif_direction_correct,
                        "process_was_sound": r.process_was_sound,
                        "outcome_process_classification": r.outcome_process_classification,
                        "reflection": r.reflection_text,
                        "tags": r.lesson_tags,
                        "next_adjustment": getattr(r, 'next_trade_adjustment', None)
                    } for r in whatif_results
                ]
            }
        except Exception as e:
            logger.error(f"Gagal get lessons: {e}")
            return {"real_trades": [], "paper_whatifs": []}

    @staticmethod
    async def get_global_lessons(session: AsyncSession, exclude_symbol: str, limit: int = 3) -> list[dict]:
        import json
        HIGH_VALUE_TAGS = ['sl_too_tight', 'premature_entry', 'late_entry', 'news_spike_sl_hit',
                            'spread_widening_sl_hit', 'tp_too_greedy']
        stmt = select(DecisionReflection).where(
            DecisionReflection.symbol != exclude_symbol, DecisionReflection.status == 'resolved',
            DecisionReflection.lesson_tags.isnot(None),
        ).order_by(DecisionReflection.resolved_at.desc()).limit(30)
        rows = (await session.execute(stmt)).scalars().all()
        out = []
        for r in rows:
            try:
                tags = json.loads(r.lesson_tags) if r.lesson_tags else []
            except Exception:
                tags = []
            if any(t in HIGH_VALUE_TAGS for t in tags):
                out.append({'symbol': r.symbol, 'tags': tags, 'lesson': r.specific_lesson or r.reflection_text})
            if len(out) >= limit:
                break
        return out

