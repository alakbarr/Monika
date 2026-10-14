# ==============================================================================
# File: execution/service/reconciliation.py
# ==============================================================================

"""
Broker and DB position reconciliation helpers.
Restores state on startup and matches local records with broker reality.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Set, Union

from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.ports import PositionRepositoryPort, TradeProposalRepositoryPort, UnitOfWorkPort
from monika.infrastructure.database.repositories import PositionRepository, TradeProposalRepository

logger = logging.getLogger("TradingAgent.ExecutionService.Reconciliation")


class ReconciliationHelper:
    """Helper for restoring executed analysis IDs and reconciling positions."""

    @staticmethod
    async def restore_executed_ids_from_db(
        session: Union[AsyncSession, UnitOfWorkPort],
        executed_ids_dict: Dict[int, float],
        limit: int = 500,
    ) -> int:
        """
        Populate the in-memory deduplication dictionary from recent DB records
        (Position, MT5Signal, Order) on startup or cache eviction.
        """
        restored = 0
        now_ts = time.time()
        try:
            if isinstance(session, UnitOfWorkPort):
                pos_repo: PositionRepositoryPort = session.positions
                trade_repo: TradeProposalRepositoryPort = session.trade_proposals
            else:
                pos_repo = PositionRepository(session)
                trade_repo = TradeProposalRepository(session)

            # 1. From Position
            for aid in await pos_repo.get_recent_executed_analysis_ids(limit=limit):
                if aid and aid not in executed_ids_dict:
                    executed_ids_dict[aid] = now_ts
                    restored += 1

            # 2. From MT5Signal
            for aid in await trade_repo.get_recent_executed_analysis_ids(limit=limit):
                if aid and aid not in executed_ids_dict:
                    executed_ids_dict[aid] = now_ts
                    restored += 1

            # 3. From Order
            for aid in await pos_repo.get_recent_order_executed_analysis_ids(limit=limit):
                if aid and aid not in executed_ids_dict:
                    executed_ids_dict[aid] = now_ts
                    restored += 1

            logger.info(f"[Reconciliation] Restored {restored} executed analysis IDs into memory deduplication cache.")
        except Exception as e:
            logger.warning(f"[Reconciliation] Failed to restore executed IDs from DB: {e}")
        return restored
