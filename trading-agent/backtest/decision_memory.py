"""
Decision Memory Log — untuk learning dari past decisions.
Disimpan di tabel decision_memory_backtest.
"""
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from database.db import get_session
from database.models import DecisionMemory
from analysis.providers.llm_factory import get_client_for_task
from config.settings import load_all_config

logger = logging.getLogger(__name__)

class DecisionMemoryManager:
    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or load_all_config()
        self.client = get_client_for_task("trade_reflection", self.settings)

    async def log_decision(self, symbol: str, decision: str, confidence: float, rationale: str, date: datetime, run_id: Optional[int] = None):
        """Mencatat keputusan awal sebelum ada outcome."""
        async with get_session() as session:
            memory = DecisionMemory(
                run_id=run_id,
                symbol=symbol,
                decision_date=date,
                decision=decision,
                confidence=confidence,
                rationale_summary=rationale[:1000] if rationale else None
            )
            session.add(memory)
            await session.commit()
            return memory.id

    async def update_outcome_and_reflect(self, memory_id: int, pnl_pct: float, holding_hours: float, reason: str, end_date: datetime):
        """Update outcome dan generate refleksi AI."""
        async with get_session() as session:
            memory = await session.get(DecisionMemory, memory_id)
            if not memory:
                logger.error(f"DecisionMemory {memory_id} not found.")
                return

            memory.raw_return = pnl_pct
            memory.holding_days = int(holding_hours // 24)
            memory.outcome_status = reason
            memory.resolved_at = end_date

            # Generate reflection if client is available
            if self.client:
                prompt = (
                    f"You made a {memory.decision.upper()} decision on {memory.symbol} with {memory.confidence} confidence.\n"
                    f"Rationale: {memory.rationale_summary}\n"
                    f"Outcome: {reason} with {pnl_pct:.2f}% return over {holding_hours} hours.\n"
                    "Write a 2-4 sentence reflection on what went right or wrong, and what to learn."
                )
                system = "You are a trading AI reviewing your past performance."
                
                reflection = await self.client.generate_content(system_prompt=system, user_message=prompt)
                memory.reflection = reflection

            await session.commit()

    async def get_past_decisions_context(self, symbol: str, limit: int = 5, run_id: Optional[int] = None) -> str:
        """Mengambil riwayat keputusan untuk konteks Stage 2."""
        import utils.clock as clock
        async with get_session() as session:
            stmt = (
                select(DecisionMemory)
                .where(DecisionMemory.symbol == symbol)
                .where(DecisionMemory.outcome_status != "pending")
                .where(DecisionMemory.resolved_at <= clock.now())
            )
            if run_id is not None:
                stmt = stmt.where(DecisionMemory.run_id == run_id)
            stmt = stmt.order_by(DecisionMemory.resolved_at.desc()).limit(limit)
            past = (await session.execute(stmt)).scalars().all()

        if not past:
            return ""

        context = "PAST DECISIONS HISTORY:\n"
        for p in past:
            ret_str = f"{p.raw_return:.2f}%" if p.raw_return is not None else "N/A"
            context += (
                f"- {p.decision_date.strftime('%Y-%m-%d')}: {p.decision.upper()} "
                f"({p.outcome_status}, {ret_str}).\n"
                f"  Reflection: {p.reflection}\n"
            )
        return context
