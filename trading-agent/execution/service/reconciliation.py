# ==============================================================================
# File: execution/service/reconciliation.py
# ==============================================================================

"""
Broker and DB position reconciliation helpers.
Restores state on startup and matches local records with broker reality.
"""

import logging
import time
from typing import Set, Dict, Any, List
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Position, MT5Signal, Order

logger = logging.getLogger("TradingAgent.ExecutionService.Reconciliation")


class ReconciliationHelper:
    """Helper for restoring executed analysis IDs and reconciling positions."""

    @staticmethod
    async def restore_executed_ids_from_db(
        session: AsyncSession,
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
            # 1. From Position
            pos_stmt = (
                select(Position.analysis_id)
                .where(Position.analysis_id.isnot(None))
                .order_by(desc(Position.id))
                .limit(limit)
            )
            for aid in (await session.execute(pos_stmt)).scalars().all():
                if aid and aid not in executed_ids_dict:
                    executed_ids_dict[aid] = now_ts
                    restored += 1

            # 2. From MT5Signal
            sig_stmt = (
                select(MT5Signal.asset_analysis_id)
                .where(MT5Signal.asset_analysis_id.isnot(None))
                .order_by(desc(MT5Signal.id))
                .limit(limit)
            )
            for aid in (await session.execute(sig_stmt)).scalars().all():
                if aid and aid not in executed_ids_dict:
                    executed_ids_dict[aid] = now_ts
                    restored += 1

            # 3. From Order
            ord_stmt = (
                select(Order.analysis_id)
                .where(Order.analysis_id.isnot(None))
                .order_by(desc(Order.id))
                .limit(limit)
            )
            for aid in (await session.execute(ord_stmt)).scalars().all():
                if aid and aid not in executed_ids_dict:
                    executed_ids_dict[aid] = now_ts
                    restored += 1

            logger.info(f"[Reconciliation] Restored {restored} executed analysis IDs into memory deduplication cache.")
        except Exception as e:
            logger.warning(f"[Reconciliation] Failed to restore executed IDs from DB: {e}")
        return restored
