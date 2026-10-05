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

    if allowed_ips and not is_localhost:
        import ipaddress
        ip_matched = False
        try:
            client_ip_obj = ipaddress.ip_address(client_host)
            for allowed in allowed_ips:
                try:
                    if "/" in allowed:
                        net = ipaddress.ip_network(allowed, strict=False)
                        if client_ip_obj in net:
                            ip_matched = True
                            break
                    elif client_host == allowed:
                        ip_matched = True
                        break
                except Exception:
                    if client_host == allowed:
                        ip_matched = True
                        break
        except Exception:
            ip_matched = (client_host in allowed_ips)

        if not ip_matched:
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
# Setup & Onboarding Wizard Routes
# ---------------------------------------------------------------------------

_SETUP_HTML_PATH = Path(__file__).parent / "static_setup.html"

@app.get("/setup", include_in_schema=False)
async def serve_setup_page():
    """Serve standalone Web Setup Wizard page."""
    if _SETUP_HTML_PATH.exists():
        return FileResponse(str(_SETUP_HTML_PATH))
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Setup page template not found")

@app.post("/api/setup/submit")
async def submit_setup_configuration(request: Request):
    """Receive and persist configuration submitted from Web Onboarding Wizard."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid JSON payload"})

    try:
        from utils.infra.env_file_manager import EnvFileManager
        from config.profile_applicator import ProfileApplicator
        from config.atomic_writer import AtomicConfigWriter

        env_updates: Dict[str, str] = {}

        # 1. Database
        db_type = data.get("db_type", "sqlite")
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if db_type == "sqlite":
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            db_file = os.path.join(data_dir, "monika.db").replace("\\", "/")
            db_url = f"sqlite+aiosqlite:///{db_file}"
        else:
            db_url = data.get("db_url") or "postgresql+asyncpg://postgres:postgres@localhost:5432/monika_trading"

        env_updates["DATABASE_URL"] = db_url
        os.environ["DATABASE_URL"] = db_url

        # 2. AI Keys
        gemini_keys = str(data.get("gemini_keys", "")).strip()
        if gemini_keys:
            env_updates["GEMINI_API_KEYS"] = gemini_keys
            first_key = [k.strip() for k in gemini_keys.split(",") if k.strip()][0]
            env_updates["GEMINI_API_KEY"] = first_key
            os.environ["GEMINI_API_KEYS"] = gemini_keys
            os.environ["GEMINI_API_KEY"] = first_key

        enable_9r = data.get("enable_9router", True)
        env_updates["ENABLE_9ROUTER"] = "true" if enable_9r else "false"

        for k, env_name in [
            ("openrouter_key", "OPENROUTER_API_KEY"),
            ("groq_key", "GROQ_API_KEY"),
            ("anthropic_key", "ANTHROPIC_API_KEY"),
            ("deepseek_key", "DEEPSEEK_API_KEY"),
        ]:
            val = str(data.get(k, "")).strip()
            if val:
                env_updates[env_name] = val
                os.environ[env_name] = val

        # 3. MT5 parameters
        mt5_acc = str(data.get("mt5_account", "")).strip()
        mt5_pwd = str(data.get("mt5_password", "")).strip()
        mt5_srv = str(data.get("mt5_server", "")).strip()
        mt5_pth = str(data.get("mt5_path", "")).strip()

        if mt5_acc:
            env_updates["MT5_ACCOUNT"] = mt5_acc
        if mt5_pwd:
            env_updates["MT5_PASSWORD"] = mt5_pwd
        if mt5_srv:
            env_updates["MT5_SERVER"] = mt5_srv
        if mt5_pth:
            clean_path = mt5_pth.replace("\\", "/")
            env_updates["MT5_PATH"] = clean_path

        # Write .env atomically
        EnvFileManager.update_env_values(env_updates)

        # 4. Apply 49 Task Roles according to chosen profile
        profile = data.get("profile", "low_latency_cheap")
        settings_path = _get_settings_path()

        provs = ProfileApplicator.detect_available_providers()
        ProfileApplicator.apply_profile_to_settings(settings_path, profile, provs)

        # 5. Paper trading setting
        trade_mode = data.get("trade_mode", "paper")
        is_paper = (trade_mode == "paper")
        AtomicConfigWriter.update_in_place(settings_path, {
            "paper_trading": {
                "enabled": is_paper,
            }
        })

        # 6. Initialize database tables
        try:
            from database.db import init_db
            await init_db()
        except Exception as dberr:
            logger.warning(f"Database init warning during web setup: {dberr}")

        return {"status": "ok", "message": "Konfigurasi Monika berhasil disimpan.", "profile": profile, "db": db_type}

    except Exception as e:
        logger.error(f"Error saving setup configuration: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


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
