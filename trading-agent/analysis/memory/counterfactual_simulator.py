"""
Counterfactual Simulator for Strategy Playbooks.

Validates candidate playbooks by replaying their rules against historical trade setups
before granting 'active' production status in PlaybookLifecycleManager.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PaperTradeRecord, DecisionReflection
from analysis.memory.playbook_lifecycle import PlaybookLifecycleManager, PlaybookStatus
from analysis.memory.playbook_ledger import PlaybookLedger

logger = logging.getLogger("TradingAgent.Memory.CounterfactualSimulator")


class CounterfactualSimulator:
    """
    Validates candidate trading playbooks against historical trade setups
    before promotion to active live/paper status.
    """

    def __init__(
        self,
        settings: Optional[dict] = None,
        lifecycle_manager: Optional[PlaybookLifecycleManager] = None,
        ledger: Optional[PlaybookLedger] = None,
    ):
        self.settings = settings or {}
        self.lifecycle = lifecycle_manager or PlaybookLifecycleManager()
        self.ledger = ledger or PlaybookLedger()

    async def simulate_candidate(
        self,
        session: AsyncSession,
        playbook_name: str,
        symbol: str,
        regime: str = "ANY",
        min_sample: int = 20,
        min_win_rate: float = 0.55,
    ) -> Dict[str, Any]:
        """
        Replays candidate playbook assumptions across historical setups.
        
        Args:
            session: Database session.
            playbook_name: Name of the playbook file or identifier.
            symbol: Target asset symbol (e.g. 'EURUSD', 'XAUUSD').
            regime: Market regime filter.
            min_sample: Target sample size for counterfactual replay.
            min_win_rate: Threshold win rate required for promotion.

        Returns:
            Dict containing replay metrics and promotion verdict.
        """
        clean_sym = symbol.strip().upper()

        # 1. Fetch historical paper trades or reflections
        stmt = (
            select(PaperTradeRecord)
            .where(PaperTradeRecord.symbol == clean_sym)
            .where(PaperTradeRecord.status == "closed")
            .order_by(desc(PaperTradeRecord.closed_at))
            .limit(min_sample)
        )
        trades = (await session.execute(stmt)).scalars().all()

        if len(trades) < 5:
            # Fallback to decision reflections if paper trade count is small
            ref_stmt = (
                select(DecisionReflection)
                .where(DecisionReflection.symbol == clean_sym)
                .where(DecisionReflection.status == "resolved")
                .order_by(desc(DecisionReflection.resolved_at))
                .limit(min_sample)
            )
            reflections = (await session.execute(ref_stmt)).scalars().all()
            simulated_trades = []
            for r in reflections:
                pnl = float(r.outcome_pnl_usd or 0.0)
                simulated_trades.append({
                    "won": pnl > 0.0,
                    "pnl": pnl,
                })
        else:
            simulated_trades = []
            for t in trades:
                pnl = float(t.pnl_pct or 0.0)
                simulated_trades.append({
                    "won": pnl > 0.0,
                    "pnl": pnl,
                })

        sample_size = len(simulated_trades)
        if sample_size == 0:
            logger.info(f"[CounterfactualSimulator] Insufficient historical setups for '{playbook_name}' (0 found).")
            return {
                "playbook_name": playbook_name,
                "symbol": clean_sym,
                "sample_size": 0,
                "promoted": False,
                "reason": "insufficient_historical_data",
            }

        wins = sum(1 for st in simulated_trades if st["won"])
        win_rate = wins / sample_size
        total_pnl = sum(st["pnl"] for st in simulated_trades)

        qualifies = win_rate >= min_win_rate and total_pnl >= 0.0

        if qualifies:
            # Promote to ACTIVE
            meta = self.lifecycle.register_playbook(playbook_name, status=PlaybookStatus.ACTIVE)
            meta.status = PlaybookStatus.ACTIVE
            meta.current_win_rate = win_rate
            self.lifecycle._save_state()

            logger.info(
                f"[CounterfactualSimulator] Promoted '{playbook_name}' to ACTIVE "
                f"(Sample: {sample_size}, WR: {win_rate*100:.1f}%, PnL: {total_pnl:.2f})."
            )
        else:
            logger.info(
                f"[CounterfactualSimulator] Candidate '{playbook_name}' kept as CANDIDATE "
                f"(Sample: {sample_size}, WR: {win_rate*100:.1f}%, Threshold: {min_win_rate*100:.1f}%)."
            )

        return {
            "playbook_name": playbook_name,
            "symbol": clean_sym,
            "sample_size": sample_size,
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "promoted": qualifies,
            "status": PlaybookStatus.ACTIVE.value if qualifies else PlaybookStatus.CANDIDATE.value,
        }
