# ==============================================================================
# File: logging_observability/dashboard/routes/intelligence.py
# Description: Market Intelligence, Calendar, COT, Skills, Plugins & Tearsheet API
# ==============================================================================

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select, desc

from database.db import AsyncSessionLocal
from database.models import EconomicCalendar, COTReport, NewsItem, PaperTradeRecord, TradeOutcome
from logging_observability.dashboard.rbac import require_role, Role
from skills.loader import list_skills, get_skill_metadata
from plugins.loader import load_manifest_file
from logging_observability.reporting.tearsheet_generator import QuantTearsheetGenerator

logger = logging.getLogger("TradingAgent.DashboardAPI.Intelligence")

intelligence_router = APIRouter(tags=["Intelligence & Market Data"])


@intelligence_router.get("/api/calendar/events", tags=["Calendar"])
@require_role(Role.VIEWER)
async def get_calendar_events(
    currency: Optional[str] = Query(default=None, description="Currency filter, e.g. USD, EUR, XAU"),
    impact: Optional[str] = Query(default=None, description="Impact filter: high, medium, low"),
    days_ahead: int = Query(default=7, ge=1, le=30, description="Window in days ahead"),
    limit: int = Query(default=50, ge=1, le=200, description="Max items to return"),
):
    """Retrieve scheduled macroeconomic calendar events."""
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        until = now + timedelta(days=days_ahead)
        q = select(EconomicCalendar).where(
            EconomicCalendar.event_time >= now - timedelta(hours=12),
            EconomicCalendar.event_time <= until,
        )
        if currency:
            q = q.where(EconomicCalendar.currency == currency.upper())
        if impact:
            q = q.where(EconomicCalendar.impact.ilike(impact))
        q = q.order_by(EconomicCalendar.event_time.asc()).limit(limit)

        events = (await session.execute(q)).scalars().all()
        return [
            {
                "id": e.id,
                "event_name": e.event_name,
                "country": e.country,
                "currency": e.currency,
                "impact": e.impact,
                "actual": e.actual,
                "forecast": e.forecast,
                "previous": e.previous,
                "event_time": e.event_time.isoformat() if e.event_time else None,
                "surprise_score": e.surprise_score,
            }
            for e in events
        ]


@intelligence_router.get("/api/calendar/upcoming", tags=["Calendar"])
@require_role(Role.VIEWER)
async def get_upcoming_high_impact_events():
    """Retrieve high impact macroeconomic events scheduled within next 24 hours."""
    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        next_24h = now + timedelta(hours=24)
        q = (
            select(EconomicCalendar)
            .where(
                EconomicCalendar.event_time >= now,
                EconomicCalendar.event_time <= next_24h,
                EconomicCalendar.impact.ilike("high"),
            )
            .order_by(EconomicCalendar.event_time.asc())
            .limit(20)
        )
        events = (await session.execute(q)).scalars().all()
        return [
            {
                "id": e.id,
                "event_name": e.event_name,
                "country": e.country,
                "currency": e.currency,
                "impact": e.impact,
                "actual": e.actual,
                "forecast": e.forecast,
                "previous": e.previous,
                "event_time": e.event_time.isoformat() if e.event_time else None,
                "surprise_score": e.surprise_score,
            }
            for e in events
        ]


@intelligence_router.get("/api/market/cot", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_cot_reports(
    market_code: Optional[str] = Query(default=None, description="CFTC market code, e.g. 099741 (EUR)"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Retrieve historical CFTC Commitments of Traders (COT) institutional positioning."""
    async with AsyncSessionLocal() as session:
        q = select(COTReport)
        if market_code:
            q = q.where(COTReport.market_code == market_code.upper())
        q = q.order_by(COTReport.report_date.desc()).limit(limit)

        records = (await session.execute(q)).scalars().all()
        return [
            {
                "id": r.id,
                "report_date": r.report_date.date().isoformat() if r.report_date else None,
                "market_code": r.market_code,
                "dealer_long": r.dealer_long,
                "dealer_short": r.dealer_short,
                "asset_mgr_long": r.asset_mgr_long,
                "asset_mgr_short": r.asset_mgr_short,
                "leveraged_long": r.leveraged_long,
                "leveraged_short": r.leveraged_short,
                "net_position": (r.asset_mgr_long + r.leveraged_long) - (r.asset_mgr_short + r.leveraged_short),
            }
            for r in records
        ]


@intelligence_router.get("/api/news/classified", tags=["News"])
@require_role(Role.VIEWER)
async def get_classified_news(
    symbol: Optional[str] = Query(default=None, description="Currency or asset tag, e.g. USD, EUR, XAU"),
    sentiment: Optional[str] = Query(default=None, description="Sentiment filter, e.g. bullish, bearish, neutral"),
    impact: Optional[str] = Query(default=None, description="Impact filter: BREAKING, HIGH, MEDIUM, LOW"),
    hours: int = Query(default=24, ge=1, le=168, description="Time window in hours"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Retrieve intelligence-classified news items with sentiment and impact tags."""
    async with AsyncSessionLocal() as session:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        q = select(NewsItem).where(NewsItem.fetched_at >= since)
        if symbol:
            q = q.where(NewsItem.currency_tags.contains(symbol.upper()))
        if sentiment:
            q = q.where(NewsItem.sentiment.ilike(f"%{sentiment}%"))
        if impact:
            q = q.where(NewsItem.impact.ilike(impact))
        q = q.order_by(NewsItem.fetched_at.desc()).limit(limit)

        items = (await session.execute(q)).scalars().all()
        return [
            {
                "id": n.id,
                "source": n.source,
                "title": n.title,
                "summary": n.summary,
                "url": n.url,
                "published_at": n.published_at.isoformat() if n.published_at else None,
                "currency_tags": n.currency_tags,
                "fetched_at": n.fetched_at.isoformat() if n.fetched_at else None,
                "impact": n.impact,
                "sentiment": n.sentiment,
                "key_data_point": n.key_data_point,
            }
            for n in items
        ]


@intelligence_router.get("/api/news/sentiment", tags=["News"])
@require_role(Role.VIEWER)
async def get_aggregated_sentiment():
    """Aggregate 24-hour sentiment scores across tracked currencies."""
    async with AsyncSessionLocal() as session:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        items = (
            await session.execute(
                select(NewsItem).where(
                    NewsItem.fetched_at >= since,
                    NewsItem.sentiment.isnot(None),
                )
            )
        ).scalars().all()

        summary: Dict[str, Dict[str, int]] = {}
        for item in items:
            tags = [t.strip().upper() for t in (item.currency_tags or "").split(",") if t.strip()]
            sent = (item.sentiment or "").lower()
            for tag in tags:
                if tag not in summary:
                    summary[tag] = {"bullish": 0, "bearish": 0, "neutral": 0, "total": 0}
                summary[tag]["total"] += 1
                if "bull" in sent or "positive" in sent:
                    summary[tag]["bullish"] += 1
                elif "bear" in sent or "negative" in sent:
                    summary[tag]["bearish"] += 1
                else:
                    summary[tag]["neutral"] += 1

        return {
            "period_hours": 24,
            "total_articles": len(items),
            "currencies": summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@intelligence_router.get("/api/skills", tags=["Skills"])
@require_role(Role.VIEWER)
async def get_skills_catalog():
    """List all registered autonomous skills and playbooks with frontmatter metadata."""
    skills_names = list_skills()
    skills_list = []
    for s in skills_names:
        meta = get_skill_metadata(s)
        skills_list.append({
            "name": s,
            "description": meta.get("description", ""),
            "markets": meta.get("markets", []),
            "requires_tools": meta.get("requires_tools", []),
            "fallback_for_tools": meta.get("fallback_for_tools", []),
            "is_playbook": "playbook" in s.lower(),
        })
    return {"skills": skills_list, "total": len(skills_list)}


@intelligence_router.get("/api/plugins", tags=["Plugins"])
@require_role(Role.VIEWER)
async def get_plugins_catalog():
    """List all installed plugins with manifests."""
    plugins_dir = Path(__file__).resolve().parents[3] / "plugins"
    plugins_list = []
    if plugins_dir.exists():
        for manifest_path in plugins_dir.rglob("plugin.yaml"):
            try:
                manifest = load_manifest_file(str(manifest_path))
                plugins_list.append(manifest.model_dump() if hasattr(manifest, "model_dump") else manifest.dict())
            except Exception as e:
                logger.debug(f"Error loading manifest {manifest_path}: {e}")
    return {"plugins": plugins_list, "total": len(plugins_list)}


@intelligence_router.get("/api/reports/tearsheet/latest", tags=["Observability"])
@require_role(Role.VIEWER)
async def get_latest_tearsheet():
    """Generate institutional quant tearsheet metrics from closed trading performance."""
    async with AsyncSessionLocal() as session:
        # Prioritize closed PaperTradeRecords, fallback to TradeOutcome
        paper_trades = (
            await session.execute(
                select(PaperTradeRecord)
                .where(PaperTradeRecord.status == "closed")
                .order_by(PaperTradeRecord.closed_at.desc())
                .limit(200)
            )
        ).scalars().all()

        if paper_trades:
            trade_objs: List[Any] = list(paper_trades)
        else:
            trade_objs = list(
                (
                    await session.execute(
                        select(TradeOutcome).order_by(TradeOutcome.closed_at.desc()).limit(200)
                    )
                ).scalars().all()
            )

        result = QuantTearsheetGenerator.generate_from_trades(trade_objs, initial_equity=10000.0)

        return {
            "initial_equity": result.initial_equity,
            "final_equity": result.final_equity,
            "total_net_pnl": result.total_net_pnl,
            "total_return_pct": result.total_return_pct,
            "annualized_return_pct": result.annualized_return_pct,
            "annualized_sharpe": result.annualized_sharpe,
            "annualized_sortino": result.annualized_sortino,
            "calmar_ratio": result.calmar_ratio,
            "gain_to_pain_ratio": result.gain_to_pain_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "current_drawdown_pct": result.current_drawdown_pct,
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate_pct": result.win_rate_pct,
            "profit_factor": result.profit_factor,
            "payoff_ratio": result.payoff_ratio,
            "expectancy_r": result.expectancy_r,
            "expectancy_usd": result.expectancy_usd,
            "generated_at": result.generated_at,
        }
