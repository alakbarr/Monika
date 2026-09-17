# ==============================================================================
# File: logging_observability/dashboard/api.py
# ==============================================================================

"""
Dashboard API: FastAPI Backend for Observability and Control Dashboard.

Provides performance metrics, open positions, risk telemetry, and audit logs.
Modular architecture with decomposed sub-routers under routes/.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from logging_observability.dashboard.rbac import Role, resolve_role
from logging_observability.dashboard.routes import (
    ClosePositionRequest,
    OverrideRiskRequest,
    TriggerCycleRequest,
    _active_websockets,
    _build_graph_state_for_cycle,
    _dependencies,
    _get_settings_path as _default_get_settings_path,
    _safe_json,
    _start_time,
    all_routers,
    broadcast_live_event,
    config_router,
    get_dashboard_dependency,
    observability_router,
    set_dashboard_dependencies,
    system_router,
    tokens_router,
    trading_router,
    websocket_router,
)
from logging_observability.dashboard.routes.config import (
    get_config_schema,
    get_config_settings,
    update_config_settings,
)
from logging_observability.dashboard.routes.observability import (
    get_cycle_trace_summary,
    get_graph_state,
    get_playbook_tree,
    get_prompt_cache_metrics,
    get_tool_latencies,
    get_trace_tree,
    get_traces,
)
from logging_observability.dashboard.routes.system import (
    get_auth_role,
    get_brief,
    get_gemini_quota,
    get_health,
    get_health_diagnostics,
    get_metrics,
    get_vix,
    ping,
)
from logging_observability.dashboard.routes.tokens import (
    get_tokens_by_role,
    get_tokens_by_subsystem,
    get_tokens_by_symbol,
    get_tokens_recent,
    get_tokens_summary,
)
from logging_observability.dashboard.routes.trading import (
    action_approve_trade,
    action_close_position,
    action_emergency_kill,
    action_override_risk,
    action_trigger_cycle,
    get_activity,
    get_analysis,
    get_analysis_quality_realtime,
    get_debate_outcomes,
    get_decision_distribution,
    get_edge_metrics,
    get_factor_analysis,
    get_mt5_signals,
    get_orders,
    get_overview,
    get_paper_trading_stats,
    get_positions,
    get_risk,
    get_ssvp_health,
    get_trade_triggers,
)
from logging_observability.dashboard.routes.websocket import (
    get_session_messages,
    list_sessions,
    websocket_agent_chat,
    websocket_live_feed,
)

load_dotenv()
logger = logging.getLogger("TradingAgent.DashboardAPI")

_is_prod = os.getenv("ENVIRONMENT", "").lower() in ("production", "live")
_disable_docs = _is_prod or (os.getenv("DASHBOARD_DISABLE_DOCS", "false").lower() == "true")

app = FastAPI(
    title="AI Trading Agent — Dashboard API",
    description="Real-time observability dashboard for the AI Trading Agent.",
    version="1.0.0",
    docs_url=None if _disable_docs else "/api/docs",
    redoc_url=None if _disable_docs else "/api/redoc",
    openapi_url=None if _disable_docs else "/openapi.json",
)

_allowed_origins = [o.strip() for o in os.getenv("DASHBOARD_ALLOWED_ORIGINS", "").split(",") if o.strip()] or [
    "http://localhost:5173", "http://localhost:4173", "http://localhost:3000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    api_key = os.getenv("DASHBOARD_API_KEY", "").strip()
    multi_keys = os.getenv("DASHBOARD_API_KEYS", "").strip()
    allowed_ips_raw = os.getenv("DASHBOARD_ALLOWED_IPS", "")
    allowed_ips = [ip.strip() for ip in allowed_ips_raw.split(",") if ip.strip()]

    direct_ip = request.client.host if request.client else "unknown"
    trusted_proxies = ("127.0.0.1", "::1", "localhost", "testclient")
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded and direct_ip in trusted_proxies:
        ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
        client_host = ips[0] if ips else direct_ip
    else:
        client_host = direct_ip

    is_localhost = direct_ip in ("127.0.0.1", "::1", "localhost", "testclient") and not forwarded
    path = request.url.path

    if path == "/api/ping":
        return await call_next(request)

    if allowed_ips and not is_localhost and client_host not in allowed_ips:
        return JSONResponse(
            status_code=403,
            content={"detail": f"Forbidden: IP address {client_host} is not authorized."}
        )

    if not api_key and not multi_keys:
        if not is_localhost:
            return JSONResponse(
                status_code=403,
                content={"detail": "Forbidden: DASHBOARD_API_KEY must be configured for remote network access."}
            )
        request.state.role = Role.ADMIN
        request.state.is_localhost = True
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    bearer_key = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
    client_key = request.headers.get("X-API-Key") or bearer_key or request.query_params.get("token") or ""

    try:
        role = resolve_role(str(client_key), is_localhost=is_localhost)
        request.state.role = role
        request.state.is_localhost = is_localhost
    except PermissionError:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized: Invalid or missing API key in headers"})

    return await call_next(request)


# ---------------------------------------------------------------------------
# Mount Modular Routers
# ---------------------------------------------------------------------------

for router in all_routers:
    app.include_router(router)


# ---------------------------------------------------------------------------
# Backward Compatibility Helpers
# ---------------------------------------------------------------------------

def _get_settings_path() -> str:
    """Resolve path to settings.yaml (kept at top-level for test monkeypatching)."""
    return _default_get_settings_path()


# ---------------------------------------------------------------------------
# Static File Serving (React Frontend)
# ---------------------------------------------------------------------------

_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


def _mount_frontend():
    """Mount statis React build jika ada (fallback index.html)."""
    if _FRONTEND_DIST.exists():
        app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

        @app.get("/", include_in_schema=False)
        async def serve_index():
            return FileResponse(str(_FRONTEND_DIST / "index.html"))

        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(full_path: str):
            if full_path.startswith("api/"):
                from fastapi import HTTPException
                raise HTTPException(status_code=404)
            file_path = (_FRONTEND_DIST / full_path).resolve()
            dist_resolved = _FRONTEND_DIST.resolve()
            if file_path.is_file() and file_path.is_relative_to(dist_resolved):
                return FileResponse(str(file_path))
            return FileResponse(str(_FRONTEND_DIST / "index.html"))

        logger.info(f"React frontend served from {_FRONTEND_DIST}")
    else:
        logger.info(
            "Frontend dist not found — run `npm run build` in frontend/ to build. "
            "API still available at /api/*"
        )


_mount_frontend()


# ---------------------------------------------------------------------------
# Dashboard Run Entrypoints
# ---------------------------------------------------------------------------

def run_dashboard(host: Optional[str] = None, port: Optional[int] = None, reload: bool = False):
    """Start API server dari script main (sync mode)."""
    _host = host or os.getenv("DASHBOARD_HOST", "127.0.0.1")
    _port = port or int(os.getenv("DASHBOARD_PORT", 8000))
    logger.info(f"Starting Dashboard API on http://{_host}:{_port}")
    uvicorn.run(
        "logging_observability.dashboard.api:app",
        host=_host,
        port=_port,
        reload=reload,
        log_level="warning",
    )


async def run_dashboard_async(host: Optional[str] = None, port: Optional[int] = None, shutdown_event: Optional[asyncio.Event] = None):
    """Start API server di event loop yang ada (async mode)."""
    _host = host or os.getenv("DASHBOARD_HOST", "127.0.0.1")
    _port = port or int(os.getenv("DASHBOARD_PORT", 8000))
    config = uvicorn.Config(
        app=app,
        host=_host,
        port=_port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    setattr(server, "install_signal_handlers", lambda: None)

    try:
        if shutdown_event is not None:
            async def _sync_exit():
                await shutdown_event.wait()
                server.should_exit = True
            exit_task = asyncio.create_task(_sync_exit())
            try:
                await server.serve()
            finally:
                if not exit_task.done():
                    exit_task.cancel()
        else:
            await server.serve()
    except (SystemExit, OSError, Exception) as e:
        if shutdown_event and shutdown_event.is_set():
            return
        logger.warning(f"Uvicorn server exited on port {_port} ({type(e).__name__}): {e}")
        raise OSError(f"Failed to run dashboard server on port {_port}: {e}") from None


if __name__ == "__main__":
    run_dashboard()
