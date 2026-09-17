# ==============================================================================
# File: logging_observability/dashboard/routes/tokens.py
# Description: Token Audit and Observability API Endpoints
# ==============================================================================

import logging
from fastapi import APIRouter, Query

logger = logging.getLogger("TradingAgent.DashboardAPI.Tokens")

router = APIRouter()
tokens_router = router


@router.get("/api/v1/tokens/summary", tags=["Token Audit"])
async def get_tokens_summary(hours: int = Query(24, description="Time window in hours")):
    """Get global summary of token consumption, prompt cache savings, and estimated USD cost."""
    from utils.analytics.token_auditor import TokenAuditor
    from utils.llm.context_tracker import get_context_tracker
    res = await TokenAuditor.get_summary(hours=hours)
    ctx_summary = get_context_tracker().get_summary()
    res["context_tracker"] = ctx_summary
    return res


@router.get("/api/v1/tokens/context-tracker", tags=["Token Audit"])
async def get_context_tracker_metrics():
    """Get active cycle and session context window utilization metrics (Q5)."""
    from utils.llm.context_tracker import get_context_tracker
    return get_context_tracker().get_summary()


@router.get("/api/v1/tokens/roles", tags=["Token Audit"])
async def get_tokens_by_role(hours: int = Query(24, description="Time window in hours")):
    """Get breakdown of token consumption by 32 AI task roles."""
    from utils.analytics.token_auditor import TokenAuditor
    roles = await TokenAuditor.get_role_breakdown(hours=hours)
    return {"total_roles": len(roles), "items": roles}


@router.get("/api/v1/tokens/subsystems", tags=["Token Audit"])
async def get_tokens_by_subsystem(hours: int = Query(24, description="Time window in hours")):
    """Get breakdown of token consumption by subsystem (stage1, stage2, debate, news, etc.)."""
    from utils.analytics.token_auditor import TokenAuditor
    subsystems = await TokenAuditor.get_subsystem_breakdown(hours=hours)
    return {"total_subsystems": len(subsystems), "items": subsystems}


@router.get("/api/v1/tokens/symbols", tags=["Token Audit"])
async def get_tokens_by_symbol(hours: int = Query(24, description="Time window in hours")):
    """Get breakdown of token consumption per currency symbol."""
    from utils.analytics.token_auditor import TokenAuditor
    symbols = await TokenAuditor.get_symbol_breakdown(hours=hours)
    return {"total_symbols": len(symbols), "items": symbols}


@router.get("/api/v1/tokens/recent", tags=["Token Audit"])
async def get_tokens_recent(limit: int = Query(default=50, ge=1, le=200, description="Max records to return")):
    """Get recent token log records with full audit metadata."""
    from utils.analytics.token_auditor import TokenAuditor
    logs = await TokenAuditor.get_recent_logs(limit=limit)
    return {"total": len(logs), "items": logs}
