# ==============================================================================
# File: analysis/tools/handlers/intelligence.py
# ==============================================================================

"""
Market intelligence tool handlers: user market intel persistence and query.
Direct execution without circular trampolines.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

import utils.clock as clock
from database.models import UserMarketIntel, MarketChronicle, ActivityLog
from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool

logger = logging.getLogger("TradingAgent.Tools.Intelligence")


async def handle_save_market_intelligence(tool_input: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required to save market intelligence"}

    title = str(tool_input.get("title", "")).strip()
    summary = str(tool_input.get("summary", "")).strip()
    if not title or not summary:
        return {"error": "Parameters 'title' and 'summary' are required for save_market_intelligence"}

    full_content = tool_input.get("full_content")
    if full_content is not None:
        full_content = str(full_content)

    intel_type = str(tool_input.get("intel_type", "deep_research")).strip().lower()
    if intel_type not in ("deep_research", "breaking_news", "scenario_watch", "operator_directive", "tactical_directive", "pre_event_research", "flash_news", "macro_structural"):
        intel_type = "deep_research"

    raw_syms = tool_input.get("affected_symbols", "ALL")
    if isinstance(raw_syms, list):
        affected_symbols = ",".join([str(s).strip().upper().replace("/", "") for s in raw_syms])
    else:
        affected_symbols = str(raw_syms).strip().upper().replace("/", "")
    if not affected_symbols:
        affected_symbols = "ALL"

    directive = str(tool_input.get("directive", "caution")).strip().lower()
    if directive not in ("caution", "scenario_watch", "bias_override", "informational", "neutral", "favor_buy", "favor_sell", "avoid_trade"):
        directive = "caution"

    target_cycle = str(tool_input.get("target_cycle", "next_cycle_only")).strip().lower()
    if target_cycle not in ("next_cycle_only", "persistent", "continuous", "until_event"):
        target_cycle = "next_cycle_only"

    try:
        expires_in_hours = int(tool_input.get("expires_in_hours", 24))
    except (ValueError, TypeError):
        expires_in_hours = 24
    expires_in_hours = max(1, min(expires_in_hours, 168))

    telegram_user_id = str(tool_input.get("telegram_user_id") or "operator")
    metadata_json = tool_input.get("metadata_json")
    if isinstance(metadata_json, dict):
        metadata_json = json.dumps(metadata_json)
    elif metadata_json is not None:
        metadata_json = str(metadata_json)

    now_utc = clock.now()
    expires_at = now_utc + timedelta(hours=expires_in_hours)

    record = UserMarketIntel(
        telegram_user_id=telegram_user_id,
        intel_type=intel_type,
        title=title[:300],
        summary=summary,
        full_content=full_content,
        affected_symbols=affected_symbols[:100],
        directive=directive,
        target_cycle=target_cycle,
        is_active=True,
        created_at=now_utc,
        expires_at=expires_at,
        metadata_json=metadata_json,
    )
    effective_session.add(record)
    await effective_session.flush()

    if (intel_type in ("breaking_news", "deep_research", "macro_structural", "flash_news") and
        directive in ("caution", "bias_override", "favor_buy", "favor_sell", "avoid_trade")):
        is_geo = any(k in (title + " " + summary).lower() for k in ("war", "conflict", "strike", "iran", "attack", "sanction", "military", "shipping", "strait"))
        chronicle = MarketChronicle(
            event_date=now_utc,
            category="geopolitical" if is_geo else "data_shock",
            headline=title[:300],
            narrative=summary,
            currencies_affected=affected_symbols[:100] if affected_symbols != "ALL" else "USD,EUR,GBP,JPY,AUD,XAU,XTI",
            severity="high" if directive in ("bias_override", "avoid_trade") else "medium",
            is_ongoing=True,
            created_at=now_utc,
        )
        effective_session.add(chronicle)

    effective_session.add(ActivityLog(
        category="trading",
        description=f"User market intelligence saved: [{intel_type.upper()}] {title} (Directive: {directive})",
        actor="tool_executor",
        timestamp=now_utc,
    ))
    await effective_session.commit()

    return {
        "status": "success",
        "saved": True,
        "id": record.id,
        "intel_id": record.id,
        "title": record.title,
        "intel_type": record.intel_type,
        "directive": record.directive,
        "target_cycle": record.target_cycle,
        "affected_symbols": record.affected_symbols.split(",") if record.affected_symbols != "ALL" else ["ALL"],
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "message": f"Intelligence #{record.id} successfully saved and activated.",
    }


async def handle_list_active_intelligence(tool_input: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"status": "success", "count": 0, "active_intelligence": [], "items": []}

    affected_filter = tool_input.get("affected_symbol") or tool_input.get("symbol")
    if affected_filter:
        affected_filter = str(affected_filter).strip().upper().replace("/", "")

    now_utc = clock.now()
    stmt = (
        select(UserMarketIntel)
        .where(UserMarketIntel.is_active == True)
        .where(or_(UserMarketIntel.expires_at.is_(None), UserMarketIntel.expires_at >= now_utc))
        .order_by(UserMarketIntel.created_at.desc())
    )
    rows = (await effective_session.execute(stmt)).scalars().all()

    results = []
    for r in rows:
        if affected_filter:
            syms = [s.strip() for s in r.affected_symbols.split(",")]
            if r.affected_symbols != "ALL" and affected_filter not in syms:
                continue
        results.append({
            "id": r.id,
            "title": r.title,
            "summary": r.summary,
            "intel_type": r.intel_type,
            "affected_symbols": r.affected_symbols,
            "directive": r.directive,
            "target_cycle": r.target_cycle,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        })

    return {
        "status": "success",
        "count": len(results),
        "active_intelligence": results,
        "items": results,
    }


async def handle_archive_market_intelligence(tool_input: dict, session: Optional[AsyncSession] = None, executor: Optional[Any] = None, **kwargs) -> dict:
    effective_session = session or getattr(executor, "session", None)
    if not effective_session:
        return {"error": "Database session required to archive market intelligence"}

    raw_id = tool_input.get("intel_id")
    if raw_id is None:
        return {"error": "Missing parameter 'intel_id' for archive_market_intelligence"}

    try:
        intel_id = int(raw_id)
    except (ValueError, TypeError):
        return {"error": f"Invalid intel_id: {raw_id}"}

    reason = str(tool_input.get("reason", "archived by user")).strip()

    stmt = select(UserMarketIntel).where(UserMarketIntel.id == intel_id)
    record = (await effective_session.execute(stmt)).scalar_one_or_none()

    if not record:
        return {"status": "not_found", "id": intel_id, "message": f"Intelligence #{intel_id} not found."}

    record.is_active = False
    record.consumed_at = clock.now()
    effective_session.add(ActivityLog(
        category="trading",
        description=f"Market intelligence #{intel_id} archived: {reason}",
        actor="tool_executor",
        timestamp=clock.now(),
    ))
    await effective_session.commit()

    return {
        "status": "success",
        "archived": True,
        "id": intel_id,
        "intel_id": intel_id,
        "title": record.title,
        "reason": reason,
        "message": f"Intelligence #{intel_id} archived and deactivated.",
    }


@register_tool("save_market_intelligence", aliases=["save_intelligence", "save_intel"], category="GENERAL", parallel_safe=False)
class SaveMarketIntelligenceHandler(ToolHandler):
    name = "save_market_intelligence"
    category = "GENERAL"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_save_market_intelligence(args, session=session, executor=executor, **kwargs)


@register_tool("list_active_intelligence", aliases=["list_intelligence", "list_intel"], category="GENERAL", parallel_safe=True)
class ListActiveIntelligenceHandler(ToolHandler):
    name = "list_active_intelligence"
    category = "GENERAL"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_list_active_intelligence(args, session=session, executor=executor, **kwargs)


@register_tool("archive_market_intelligence", aliases=["archive_intel"], category="GENERAL", parallel_safe=False)
class ArchiveMarketIntelligenceHandler(ToolHandler):
    name = "archive_market_intelligence"
    category = "GENERAL"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_archive_market_intelligence(args, session=session, executor=executor, **kwargs)
