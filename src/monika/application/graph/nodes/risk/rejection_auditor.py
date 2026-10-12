# ==============================================================================
# File: graph/nodes/risk/rejection_auditor.py
# Monika Forensic Rejection Auditor & Paper What-If Logger
# ==============================================================================

"""
Unified rejection logging and trajectory auditing for risk gate decisions.
Eliminates copy-paste boilerplate across correlation gates, synthesis downscaling,
risk gate checks, and pre-commit validations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.Graph.Risk.RejectionAuditor")


async def audit_trade_rejection(
    session: Any,
    symbol: str,
    trade_data: Dict[str, Any],
    reasons: List[str],
    stage: str,
    analysis_record: Any = None,
) -> None:
    """
    Records paper what-if simulation and benchmark trajectory for a suppressed trade.
    """
    analysis_id = trade_data.get("analysis_id")
    ana = analysis_record
    if not ana and analysis_id and session:
        try:
            from monika.infrastructure.database.models import AssetAnalysis
            ana = await session.get(AssetAnalysis, analysis_id)
        except Exception:
            ana = None

    ctx_id = getattr(ana, "context_snapshot_id", None) if ana else None
    cds = getattr(ana, "ssvp_cds_score_at_analysis", None) if ana else None

    # 1. Paper What-If Persistence
    if session and analysis_id:
        try:
            from monika.application.analysis.memory.decision_log import DecisionLogger
            reason_summary = "; ".join(reasons) if reasons else stage
            await DecisionLogger.log_paper_whatif(
                session,
                analysis_id=analysis_id,
                symbol=symbol,
                decision=trade_data.get("decision", "wait"),
                confidence=trade_data.get("confidence", 0),
                confluence_score=None,
                rationale=f"[{stage}] Blocked: {reason_summary}",
                reason=f"{stage}_rejected",
                context_snapshot_id=ctx_id,
                ssvp_cds_score=cds,
            )
        except Exception as whatif_err:
            logger.debug(f"[{symbol}] What-if log error during {stage}: {whatif_err}")

    # 2. Benchmark Trajectory Persistence
    try:
        from monika.application.benchmark.trade_trajectory_logger import TradeTrajectoryLogger
        TradeTrajectoryLogger().log_trajectory(
            symbol=symbol,
            decision="REJECTED",
            risk_decision={"approved": False, "reasons": reasons, "stage": stage},
            execution_details={"analysis_id": analysis_id, "decision": "REJECTED", "stage": stage},
        )
    except Exception as traj_err:
        logger.debug(f"[{symbol}] Trajectory log error during {stage}: {traj_err}")
