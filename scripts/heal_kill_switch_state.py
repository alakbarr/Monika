# ==============================================================================
# File: scripts/heal_kill_switch_state.py
# ==============================================================================

"""
Healing script to resolve persistent kill switch latch and close dangling positions.
"""

import sys
import os
import asyncio
import logging

# Add project root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from database.db import get_session
from database.models import Position, PaperTradeRecord, SystemConfig, RiskState, ActivityLog
from sqlalchemy import select
import utils.clock as clock

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("HealKillSwitch")


async def heal():
    logger.info("Starting Kill Switch and Position Data Healing...")
    now = clock.now()
    async with get_session() as session:
        # 1. Close open positions
        open_positions = (await session.execute(
            select(Position).where(Position.status == "open")
        )).scalars().all()

        closed_pos_count = 0
        for pos in open_positions:
            logger.info(f"Closing lingering open position #{pos.id} ({pos.symbol} {pos.direction})")
            pos.status = "closed"
            pos.closed_at = now
            closed_pos_count += 1

        # 2. Close any open paper trade records
        open_papers = (await session.execute(
            select(PaperTradeRecord).where(PaperTradeRecord.status == "open")
        )).scalars().all()
        for paper in open_papers:
            logger.info(f"Closing lingering paper trade #{paper.id} ({paper.symbol})")
            paper.status = "closed"
            paper.closed_at = now
            paper.exit_reason = "data_healing"

        # 3. Clear SystemConfig kill_switch and pause flags
        for key in ("kill_switch", "manual_trading_paused", "trading_paused", "system_paused"):
            cfg = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == key)
            )).scalar_one_or_none()
            if cfg:
                logger.info(f"Resetting SystemConfig {key} from '{cfg.value}' to 'false'")
                cfg.value = "false"
            else:
                session.add(SystemConfig(key=key, value="false"))

        # 4. Clear RiskState trading_paused
        recent_states = (await session.execute(
            select(RiskState).order_by(RiskState.date.desc()).limit(5)
        )).scalars().all()
        for st in recent_states:
            if st.trading_paused:
                logger.info(f"Resetting RiskState ({st.date}) trading_paused to False")
                st.trading_paused = False
                st.reason = None

        # 5. Log audit trail
        session.add(ActivityLog(
            category="system",
            description=f"Data healing executed: closed {closed_pos_count} lingering positions, cleared kill_switch latch and pause flags.",
            actor="heal_script",
        ))

        await session.commit()
        logger.info(f"Data healing completed successfully. {closed_pos_count} positions closed, kill switch latch cleared.")


if __name__ == "__main__":
    asyncio.run(heal())
