# ==============================================================================
# File: logging_observability/dashboard/routes/intelligence.py
# Description: Market Intelligence, Calendar, COT, Skills, Plugins & Tearsheet API
# ==============================================================================

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select, desc

from database.db import AsyncSessionLocal
from database.models import (
    EconomicCalendar,
    COTReport,
    NewsItem,
    PaperTradeRecord,
    TradeOutcome,
    FedWatchProbability,
    TreasuryYield,
    BondYieldData,
    CentralBankRateExpectation,
    SystemConfig,
)
from logging_observability.dashboard.rbac import require_role, Role
from logging_observability.dashboard.routes.common import (
    broadcast_live_event,
    DeprecateSkillRequest,
    CrystallizeSkillRequest,
)
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


@intelligence_router.get("/api/market/fedwatch", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_market_fedwatch():
    """Retrieve CME FedWatch probabilities and central bank rate expectations."""
    async with AsyncSessionLocal() as session:
        fedwatch_rows = (
            await session.execute(
                select(FedWatchProbability).order_by(FedWatchProbability.fetched_at.desc()).limit(10)
            )
        ).scalars().all()

        cb_rows = (
            await session.execute(
                select(CentralBankRateExpectation).order_by(CentralBankRateExpectation.fetched_at.desc()).limit(15)
            )
        ).scalars().all()

        fedwatch_data = []
        for p in fedwatch_rows:
            probs = p.probabilities_json
            if isinstance(probs, str):
                try:
                    probs = json.loads(probs)
                except Exception:
                    probs = {}
            fedwatch_data.append({
                "id": p.id,
                "meeting_date": p.meeting_date,
                "probabilities": probs,
                "fetched_at": p.fetched_at.isoformat() if p.fetched_at else None,
            })

        cb_data = [
            {
                "id": cb.id,
                "bank": cb.bank,
                "meeting_date": cb.meeting_date,
                "current_rate": cb.current_rate,
                "prob_hike": cb.prob_hike,
                "prob_hold": cb.prob_hold,
                "prob_cut": cb.prob_cut,
                "source": cb.source,
                "fetched_at": cb.fetched_at.isoformat() if cb.fetched_at else None,
            }
            for cb in cb_rows
        ]

        return {
            "fedwatch": fedwatch_data,
            "central_banks": cb_data,
            "total_fedwatch": len(fedwatch_data),
            "total_central_banks": len(cb_data),
        }


@intelligence_router.get("/api/market/yields", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_market_yields():
    """Retrieve US Treasury yields, 2s10s yield curve spread, and international sovereign bond yields."""
    async with AsyncSessionLocal() as session:
        yield_rows = (
            await session.execute(
                select(TreasuryYield).order_by(TreasuryYield.date.desc()).limit(50)
            )
        ).scalars().all()

        bond_rows = (
            await session.execute(
                select(BondYieldData).order_by(BondYieldData.date.desc()).limit(30)
            )
        ).scalars().all()

        # Group latest per tenor for US Treasury
        latest_tenors: Dict[str, TreasuryYield] = {}
        for y in yield_rows:
            if y.tenor not in latest_tenors:
                latest_tenors[y.tenor] = y

        tenor_list = [
            {
                "tenor": y.tenor,
                "yield_percent": y.yield_percent,
                "date": y.date.isoformat() if y.date else None,
            }
            for y in sorted(latest_tenors.values(), key=lambda x: x.tenor)
        ]

        # 2s10s spread
        y2 = latest_tenors.get("2Y")
        y10 = latest_tenors.get("10Y")
        spread_2s10s = None
        is_inverted = False
        if y2 and y10:
            spread_2s10s = round(y10.yield_percent - y2.yield_percent, 3)
            is_inverted = spread_2s10s < 0.0

        global_bonds = [
            {
                "country_tenor": b.country_tenor,
                "yield_percent": b.yield_percent,
                "date": b.date.isoformat() if b.date else None,
            }
            for b in bond_rows
        ]

        return {
            "treasury_yields": tenor_list,
            "spread_2s10s": spread_2s10s,
            "is_inverted": is_inverted,
            "global_bonds": global_bonds,
        }


@intelligence_router.get("/api/market/fear-greed", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_market_fear_greed():
    """Retrieve market Fear & Greed index."""
    async with AsyncSessionLocal() as session:
        cfg = (
            await session.execute(
                select(SystemConfig).where(SystemConfig.key == "fear_greed_latest").limit(1)
            )
        ).scalar_one_or_none()

        if cfg and cfg.value:
            try:
                return json.loads(cfg.value)
            except Exception as e:
                logger.warning(f"Error parsing fear_greed_latest: {e}")

        # Graceful fallback default
        return {
            "current_value": 50,
            "classification": "Neutral",
            "wow_change": 0,
            "history_7d": [],
            "interpretation": "Neutral — market sentiment balanced",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


@intelligence_router.get("/api/market/sentiment-composite", tags=["Market Data"])
@require_role(Role.VIEWER)
async def get_market_sentiment_composite():
    """Retrieve multi-asset sentiment composite (Crypto, Forex, and Institutional COT)."""
    async with AsyncSessionLocal() as session:
        cfgs = (
            await session.execute(
                select(SystemConfig).where(
                    SystemConfig.key.in_([
                        "binance_sentiment_latest",
                        "myfxbook_sentiment_latest",
                        "fxssi_sentiment_latest",
                    ])
                )
            )
        ).scalars().all()

        cfg_map = {c.key: c.value for c in cfgs if c.value}

        def _safe_json(val: Optional[str]) -> Any:
            if not val:
                return None
            try:
                return json.loads(val)
            except Exception:
                return None

        crypto_sentiment = _safe_json(cfg_map.get("binance_sentiment_latest"))
        forex_sentiment = _safe_json(cfg_map.get("myfxbook_sentiment_latest"))
        fxssi_sentiment = _safe_json(cfg_map.get("fxssi_sentiment_latest"))

        cot_rows = (
            await session.execute(
                select(COTReport).order_by(COTReport.report_date.desc()).limit(15)
            )
        ).scalars().all()

        cot_summary = [
            {
                "market_code": r.market_code,
                "report_date": r.report_date.date().isoformat() if r.report_date else None,
                "dealer_long": r.dealer_long,
                "dealer_short": r.dealer_short,
                "asset_mgr_long": r.asset_mgr_long,
                "asset_mgr_short": r.asset_mgr_short,
                "leveraged_long": r.leveraged_long,
                "leveraged_short": r.leveraged_short,
                "net_position": (r.asset_mgr_long + r.leveraged_long) - (r.asset_mgr_short + r.leveraged_short),
            }
            for r in cot_rows
        ]

        return {
            "crypto": crypto_sentiment,
            "forex_myfxbook": forex_sentiment,
            "forex_fxssi": fxssi_sentiment,
            "institutional_cot": cot_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# Skill Crystallizer & Lifecycle Endpoints
# ---------------------------------------------------------------------------

@intelligence_router.get("/api/skills/crystallized", tags=["Skills"])
@require_role(Role.VIEWER)
async def get_crystallized_skills():
    """Retrieve all autonomously crystallized skills with attribution & win-rate metrics."""
    from analysis.memory.skill_crystallizer import SkillCrystallizer
    import yaml

    crystallizer = SkillCrystallizer()
    skills_dir = crystallizer.SKILLS_DIR
    skills = []

    async with AsyncSessionLocal() as session:
        # Load all DB attributions first
        cfgs = (
            await session.execute(
                select(SystemConfig).where(SystemConfig.key.like("skill_attribution_%"))
            )
        ).scalars().all()
        attr_map = {}
        for c in cfgs:
            if c.value:
                try:
                    data = json.loads(c.value)
                    attr_map[c.key.replace("skill_attribution_", "")] = data
                except Exception:
                    pass

        if skills_dir.exists():
            for f in skills_dir.glob("*.md"):
                try:
                    content = f.read_text(encoding="utf-8")
                    meta = {}
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            meta = yaml.safe_load(parts[1]) or {}

                    clean_name = f.stem.lower()
                    attr = attr_map.get(clean_name, {})
                    is_dep = (
                        meta.get("is_deprecated", False)
                        or meta.get("status") == "deprecated"
                        or attr.get("status") == "deprecated"
                    )

                    skills.append({
                        "name": meta.get("name", clean_name),
                        "file": f.name,
                        "symbol": meta.get("symbol") or clean_name.replace("crystallized_", "").split("_")[0].upper(),
                        "description": meta.get("description", ""),
                        "status": "deprecated" if is_dep else "active",
                        "is_deprecated": is_dep,
                        "deprecation_reason": meta.get("deprecation_reason") or attr.get("deprecation_reason"),
                        "win_count": meta.get("win_count", attr.get("wins_count", 0)),
                        "total_trades": attr.get("times_triggered", meta.get("win_count", 0)),
                        "win_rate": attr.get("win_rate", 1.0 if meta.get("win_count") else 0.0),
                        "recent_win_rate": attr.get("recent_win_rate"),
                        "total_pnl_usd": meta.get("total_pnl_usd", attr.get("total_pnl", 0.0)),
                        "avg_confidence": meta.get("avg_confidence"),
                        "last_crystallized_at": meta.get("last_crystallized_at"),
                    })
                except Exception as e:
                    logger.debug(f"Failed parsing skill file {f.name}: {e}")

    return {"skills": skills, "total": len(skills)}


@intelligence_router.get("/api/skills/{name}/stats", tags=["Skills"])
@require_role(Role.VIEWER)
async def get_skill_stats(name: str):
    """Retrieve live empirical attribution statistics for a crystallized skill."""
    clean_name = name.lower().replace(".md", "")
    reg_key = f"skill_attribution_{clean_name}"

    async with AsyncSessionLocal() as session:
        cfg = (
            await session.execute(
                select(SystemConfig).where(SystemConfig.key == reg_key)
            )
        ).scalar_one_or_none()

        if cfg and cfg.value:
            try:
                return json.loads(cfg.value)
            except Exception:
                pass

        return {
            "skill_name": clean_name,
            "times_triggered": 0,
            "wins_count": 0,
            "losses_count": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "recent_outcomes": [],
            "status": "active",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


@intelligence_router.post("/api/skills/curate", tags=["Skills"])
@require_role(Role.OPERATOR)
async def curate_crystallized_skills():
    """Evaluate and prune degraded crystallized skills whose win rate dropped below threshold."""
    from analysis.memory.skill_crystallizer import SkillCrystallizer

    crystallizer = SkillCrystallizer()
    async with AsyncSessionLocal() as session:
        pruned = await crystallizer.curate_and_prune_skills(session)
        await broadcast_live_event("skills_curated", {
            "pruned_count": len(pruned),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {"status": "curated", "pruned_skills": pruned, "pruned_count": len(pruned)}


@intelligence_router.post("/api/skills/{name}/deprecate", tags=["Skills"])
@require_role(Role.OPERATOR)
async def deprecate_crystallized_skill(name: str, payload: DeprecateSkillRequest):
    """Manually deprecate an underperforming or stale crystallized skill."""
    from analysis.memory.skill_crystallizer import SkillCrystallizer

    crystallizer = SkillCrystallizer()
    clean_name = name.lower().replace(".md", "")
    success = crystallizer.deprecate_skill(clean_name, reason=payload.reason or "Operator manual deprecation")

    async with AsyncSessionLocal() as session:
        reg_key = f"skill_attribution_{clean_name}"
        cfg = (
            await session.execute(
                select(SystemConfig).where(SystemConfig.key == reg_key)
            )
        ).scalar_one_or_none()
        if cfg and cfg.value:
            try:
                data = json.loads(cfg.value)
                data["status"] = "deprecated"
                data["deprecation_reason"] = payload.reason
                cfg.value = json.dumps(data)
                await session.commit()
            except Exception:
                pass

    await broadcast_live_event("skill_deprecated", {
        "skill_name": clean_name,
        "reason": payload.reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return {"status": "deprecated" if success else "failed", "skill_name": clean_name, "success": success}


@intelligence_router.post("/api/skills/crystallize", tags=["Skills"])
@require_role(Role.OPERATOR)
async def crystallize_skills_now(payload: Optional[CrystallizeSkillRequest] = None):
    """Trigger on-demand skill crystallization for a symbol or all resolved profitable setups."""
    from analysis.memory.skill_crystallizer import SkillCrystallizer

    crystallizer = SkillCrystallizer()
    sym = payload.symbol if payload else None
    async with AsyncSessionLocal() as session:
        new_skills = await crystallizer.evaluate_and_crystallize(session, symbol=sym)
        await broadcast_live_event("skills_crystallized", {
            "symbol": sym,
            "new_count": len(new_skills),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return {"status": "crystallized", "new_skills": new_skills, "count": len(new_skills)}

