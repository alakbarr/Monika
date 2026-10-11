# ==============================================================================
# File: graph/nodes/risk/proposal_notifier.py
# Monika Telegram Proposal Notification Dispatcher Sub-Node
# ==============================================================================

"""
Formats and dispatches trade proposal notifications to Telegram operators
with /approve and /reject commands for human-in-the-loop validation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("TradingAgent.Graph.Risk.ProposalNotifier")


async def send_proposal_notifications(actionable: List[Tuple[str, Dict[str, Any]]]) -> None:
    """
    Constructs Telegram HTML cards and sends trade proposal alerts to operators.
    """
    if not actionable:
        return

    try:
        from database.db import get_session
        from database.models import AssetAnalysis
        from sqlalchemy import select
        from utils.infra.notifier import AgentNotifier

        notifier = AgentNotifier()
        for sym, r in actionable:
            analysis_id = r.get("analysis_id")
            decision = str(r.get("decision", "unknown")).upper()
            confidence = float(r.get("confidence", 0) or 0)

            async with get_session() as session:
                ana = (await session.execute(
                    select(AssetAnalysis).where(AssetAnalysis.id == analysis_id)
                )).scalar_one_or_none() if analysis_id else None

            if not ana:
                continue

            msg = (
                f"[LAPORAN] <b>Trade Proposal — {sym}</b>\n\n"
                f"Decision: <b>{decision}</b>\n"
                f"Confidence: {confidence:.0%}\n"
                f"Entry: {ana.entry_zone or 'market'}\n"
                f"SL: {ana.stop_loss}\n"
                f"TP: {ana.take_profit}\n\n"
                f"Rationale: {(ana.rationale or '')[:200]}...\n\n"
                f"<i>Use /approve {analysis_id} to execute or /reject {analysis_id} to skip.</i>"
            )
            await notifier.send_info(msg)
    except Exception as e:
        logger.error(f"[ProposalNotifier] Failed to send trade proposal notification: {e}")
