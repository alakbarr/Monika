# ==============================================================================
# File: logging_observability/dashboard/routes/system.py
# Description: System Health, Metrics, Overview & Diagnostics Endpoints
# ==============================================================================

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from monika.interfaces.dashboard.rbac import Role
from monika.interfaces.dashboard.routes.common import _start_time
from monika.interfaces.dashboard.schemas import (
    ActionStatusResponse,
    AuthRoleResponse,
    HealthStatusResponse,
    PingResponse,
)

logger = logging.getLogger("TradingAgent.DashboardAPI.System")

router = APIRouter(prefix="/api/v1", tags=["System"])
system_router = router


def _parse_iso_datetime(val: Any) -> Optional[datetime]:
    """Parse raw string or datetime from DB into a UTC datetime object."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo is not None else val.replace(tzinfo=timezone.utc)
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time(), tzinfo=timezone.utc)
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


@router.get("/ping", response_model=PingResponse, tags=["System"])
async def ping():
    return {"status": "pong", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/metrics", tags=["Observability"])
async def get_metrics():
    """Prometheus metrics scrape endpoint."""
    from monika.core.telemetry.metrics_exporter import metrics

    uptime = int(time.time() - _start_time)
    metrics.set_gauge("agent_uptime_seconds", float(uptime))

    raw_prom = metrics.generate_prometheus_metrics()
    return PlainTextResponse(content=raw_prom, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/health", response_model=HealthStatusResponse, tags=["System"])
async def get_health():
    """Mengecek uptime, koneksi DB, dan status koneksi MT5 (Liveness Probe)."""
    from monika.infrastructure.database.db import get_engine

    engine = get_engine()

    db_ok = False
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text

            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")

    mt5_common = os.getenv("MT5_COMMON_FILES_PATH")
    if not mt5_common:
        if os.name == "nt":
            mt5_common = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files")
        else:
            mt5_common = "/root/.wine/drive_c/users/root/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
    ea_hb_file = Path(mt5_common) / "ea_heartbeat.txt"
    mt5_connected = False
    try:
        if ea_hb_file.exists():
            ts = int(ea_hb_file.read_text().strip())
            heartbeat_age = int(time.time()) - ts
            mt5_connected = heartbeat_age < 120
    except Exception:
        pass

    uptime = int(time.time() - _start_time)
    return {
        "status": "ok" if db_ok else "degraded",
        "uptime_seconds": uptime,
        "db_connected": db_ok,
        "mt5_connected": mt5_connected,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/diagnostics", tags=["System"])
async def get_health_diagnostics():
    """Diagnostik internal mendalam: kuota LLM, freshness data, heartbeat, biaya API."""
    from monika.infrastructure.database.db import get_engine

    engine = get_engine()

    db_ok = False
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text

            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")

    mt5_common = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files")
    ea_hb_file = Path(mt5_common) / "ea_heartbeat.txt"
    heartbeat_age: Optional[int] = None
    mt5_connected = False
    try:
        if ea_hb_file.exists():
            ts = int(ea_hb_file.read_text().strip())
            heartbeat_age = int(time.time()) - ts
            mt5_connected = heartbeat_age < 120
    except Exception:
        pass

    last_scraper = None
    last_cycle = None
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text

            scraper_res = await conn.execute(
                text("SELECT MAX(timestamp) FROM activity_log WHERE category = 'scraping'")
            )
            last_scraper = _parse_iso_datetime(scraper_res.scalar_one_or_none())

            cycle_res = await conn.execute(text("SELECT MAX(timestamp) FROM activity_log WHERE category = 'analysis'"))
            last_cycle = _parse_iso_datetime(cycle_res.scalar_one_or_none())
    except Exception as e:
        logger.warning(f"ActivityLog query failed: {e}")

    gemini_ok = bool(os.getenv("GEMINI_API_KEY"))

    api_cost = 0.0
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text

            cost_res = await conn.execute(text("SELECT value FROM system_config WHERE key = 'api_costs'"))
            cost_val = cost_res.scalar_one_or_none()
            if cost_val:
                cost_data = json.loads(cost_val)
                api_cost = cost_data.get("total_usd_ytd", 0.0)
    except Exception:
        pass

    uptime = int(time.time() - _start_time)

    data_freshness = {}
    try:
        async with engine.connect() as conn:
            from sqlalchemy import text

            now_dt = datetime.now(timezone.utc)
            now_ts = now_dt.timestamp()

            res = await conn.execute(text("SELECT MAX(fetched_at) FROM news_items"))
            n_dt = _parse_iso_datetime(res.scalar_one_or_none())
            data_freshness["news_hours_old"] = round((now_ts - n_dt.timestamp()) / 3600, 1) if n_dt else None

            res = await conn.execute(text("SELECT MAX(fetched_at) FROM economic_calendar"))
            c_dt = _parse_iso_datetime(res.scalar_one_or_none())
            data_freshness["calendar_hours_old"] = round((now_ts - c_dt.timestamp()) / 3600, 1) if c_dt else None

            res = await conn.execute(text("SELECT MAX(date) FROM vix_data"))
            v_dt = _parse_iso_datetime(res.scalar_one_or_none())
            data_freshness["vix_days_old"] = (now_dt.date() - v_dt.date()).days if v_dt else None

            res = await conn.execute(text("SELECT MAX(report_date) FROM cot_report"))
            cot_dt = _parse_iso_datetime(res.scalar_one_or_none())
            data_freshness["cot_days_old"] = (now_dt.date() - cot_dt.date()).days if cot_dt else None
    except Exception as e:
        logger.warning(f"Data freshness check failed: {e}")

    gemini_quota = {}
    try:
        from monika.infrastructure.database.db import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            from monika.infrastructure.api.gemini_rate_limiter import GeminiRateLimiter

            limiter = GeminiRateLimiter(session)
            gemini_quota["flash"] = await limiter.get_usage("flash")
            gemini_quota["flash_lite"] = await limiter.get_usage("flash_lite")
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "uptime_seconds": uptime,
        "db_connected": db_ok,
        "mt5_connected": mt5_connected,
        "heartbeat_age_seconds": heartbeat_age,
        "last_scraper_run": last_scraper.isoformat() if last_scraper else None,
        "last_analysis_cycle": last_cycle.isoformat() if last_cycle else None,
        "gemini_api_available": gemini_ok,
        "gemini_quota": gemini_quota,
        "data_freshness": data_freshness,
        "api_cost_ytd_usd": round(api_cost, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/gemini-quota", tags=["System"])
async def get_gemini_quota():
    """Cek kuota rate limiter API Gemini (harian)."""
    from monika.infrastructure.api.gemini_rate_limiter import GeminiRateLimiter
    from monika.infrastructure.database.db import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            limiter = GeminiRateLimiter(session)
            flash_usage = await limiter.get_usage("flash")
            lite_usage = await limiter.get_usage("flash_lite")

            return {
                "flash": {
                    **flash_usage,
                    "pct_used": round(flash_usage["used"] / max(flash_usage["max_rpd"], 1) * 100, 1),
                },
                "flash_lite": {
                    **lite_usage,
                    "pct_used": round(lite_usage["used"] / max(lite_usage["max_rpd"], 1) * 100, 1),
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    except Exception as e:
        logger.error(f"Failed to get gemini quota: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vix", tags=["Market Data"])
async def get_vix(limit: int = Query(default=30, ge=1, le=90)):
    """Data historis VIX untuk chart sparkline."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import VIXData

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(VIXData).order_by(VIXData.date.desc()).limit(limit))).scalars().all()

        return [
            {
                "date": (
                    r.date.date() if hasattr(r.date, "date") and callable(getattr(r.date, "date")) else r.date
                ).isoformat()
                if r.date
                else None,
                "close": round(r.close, 2) if r.close else None,
            }
            for r in reversed(rows)
        ]


@router.get("/brief", tags=["Analysis"])
async def get_brief():
    """Ringkasan Stage 1 (Fundamental Brief) paling baru."""
    from sqlalchemy import select

    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import FundamentalBrief

    async with AsyncSessionLocal() as session:
        brief = (
            await session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
        ).scalar_one_or_none()

        if not brief:
            return {"brief": None}

        structured = None
        if brief.structured_json:
            try:
                structured = json.loads(brief.structured_json)
            except Exception:
                pass

        return {
            "brief": {
                "id": brief.id,
                "generated_at": brief.generated_at.isoformat() if brief.generated_at else None,
                "valid_until": brief.valid_until.isoformat() if brief.valid_until else None,
                "content_markdown": brief.content_markdown or "",
                "structured": structured,
            }
        }


@router.get("/auth/role", response_model=AuthRoleResponse, tags=["Auth"])
async def get_auth_role(request: Request):
    """Retrieve authenticated caller's current role and environment status."""
    role = getattr(request.state, "role", Role.VIEWER) if request else Role.ADMIN
    is_localhost = getattr(request.state, "is_localhost", False) if request else True
    return {
        "role": role.value if isinstance(role, Role) else str(role),
        "authenticated": bool(getattr(request.state, "role", None)),
        "is_localhost": is_localhost,
    }


@router.post("/actions/shutdown", response_model=ActionStatusResponse, tags=["System"])
async def shutdown_system(request: Request):
    """Gracefully request system/daemon shutdown."""
    import asyncio

    from monika.application.agent.task_registry import mark_clean_shutdown

    logger.info("Shutdown requested via /api/actions/shutdown")
    try:
        mark_clean_shutdown()
    except Exception as e:
        logger.warning(f"Could not mark clean shutdown flag: {e}")

    async def _do_shutdown():
        await asyncio.sleep(0.5)
        ev = getattr(request.app.state, "shutdown_event", None)
        if ev and hasattr(ev, "set"):
            ev.set()
        server = getattr(request.app.state, "server", None)
        if server and hasattr(server, "should_exit"):
            server.should_exit = True
        else:
            import signal

            os.kill(os.getpid(), signal.SIGINT)

    asyncio.create_task(_do_shutdown())
    return {"status": "shutting_down", "message": "Graceful shutdown initiated"}
