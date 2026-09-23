# ==============================================================================
# File: logging_observability/dashboard/routes/plugins.py
# Description: Plugin Marketplace, Lifecycle & ON/OFF Management Endpoints
# ==============================================================================

import asyncio
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from logging_observability.dashboard.rbac import Role, require_role
from logging_observability.dashboard.routes.common import (
    broadcast_live_event,
    _get_settings_path,
)
from harness.installer import (
    validate_package_spec,
    run_pip_install,
    run_pip_uninstall,
    get_community_catalog,
    toggle_plugin_state,
    list_all_plugins_status,
)

logger = logging.getLogger("TradingAgent.DashboardAPI.Plugins")

router = APIRouter(tags=["Plugins"])
plugins_router = router


class PluginToggleRequest(BaseModel):
    plugin_id: str = Field(description="Unique ID of the plugin to toggle")
    category: str = Field(default="custom", description="Plugin category (e.g. analysis_pipeline, broker, scheduler)")
    enabled: bool = Field(description="Desired activation state")


class PluginInstallRequest(BaseModel):
    package_name: str = Field(description="Pip package name, GitHub URL, or .whl path")


class PluginUninstallRequest(BaseModel):
    package_name: str = Field(description="Package name to uninstall via pip")


@router.get("/api/plugins")
@require_role(Role.VIEWER)
async def get_plugins(request: Request) -> Dict[str, Any]:
    """Retrieve full list of registered, installed, and discovered plugins with current status."""
    try:
        plugins = list_all_plugins_status()
        return {
            "status": "ok",
            "count": len(plugins),
            "total": len(plugins),
            "plugins": plugins,
        }
    except Exception as e:
        logger.error(f"Error fetching plugins list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/plugins/catalog")
@require_role(Role.VIEWER)
async def get_plugin_catalog(request: Request) -> Dict[str, Any]:
    """Retrieve curated marketplace catalog of official and community plugins."""
    try:
        catalog = get_community_catalog()
        return {
            "status": "ok",
            "count": len(catalog),
            "catalog": catalog,
        }
    except Exception as e:
        logger.error(f"Error fetching plugin catalog: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/plugins/toggle")
@require_role(Role.ADMIN)
async def toggle_plugin(request: Request, body: PluginToggleRequest) -> Dict[str, Any]:
    """Dynamically enable or disable a plugin in settings.yaml and runtime."""
    success, msg = toggle_plugin_state(body.plugin_id, body.category, body.enabled)
    if not success:
        return {"status": "error", "message": msg}

    # Broadcast event to WebSocket subscribers
    try:
        await broadcast_live_event("plugin_state_changed", {
            "plugin_id": body.plugin_id,
            "category": body.category,
            "enabled": body.enabled,
        })
    except Exception as e:
        logger.debug(f"Broadcast error on plugin toggle: {e}")

    return {
        "status": "ok",
        "message": msg,
        "plugin_id": body.plugin_id,
        "enabled": body.enabled,
        "plugins": list_all_plugins_status(),
    }


@router.post("/api/plugins/install")
@require_role(Role.ADMIN)
async def install_plugin(request: Request, body: PluginInstallRequest) -> Dict[str, Any]:
    """Execute asynchronous pip install inside Monika's virtualenv."""
    is_valid, err_msg = validate_package_spec(body.package_name)
    if not is_valid:
        raise HTTPException(status_code=400, detail=err_msg)

    # Run pip install in worker thread to prevent blocking event loop
    success, output = await asyncio.to_thread(run_pip_install, body.package_name)

    # Broadcast install completion event
    try:
        await broadcast_live_event("plugin_installed", {
            "package_name": body.package_name,
            "success": success,
        })
    except Exception as e:
        logger.debug(f"Broadcast error on plugin install: {e}")

    return {
        "status": "ok" if success else "error",
        "package_name": body.package_name,
        "output": output,
        "plugins": list_all_plugins_status(),
    }


@router.post("/api/plugins/uninstall")
@require_role(Role.ADMIN)
async def uninstall_plugin(request: Request, body: PluginUninstallRequest) -> Dict[str, Any]:
    """Execute asynchronous pip uninstall."""
    success, output = await asyncio.to_thread(run_pip_uninstall, body.package_name)

    try:
        await broadcast_live_event("plugin_uninstalled", {
            "package_name": body.package_name,
            "success": success,
        })
    except Exception as e:
        logger.debug(f"Broadcast error on plugin uninstall: {e}")

    return {
        "status": "ok" if success else "error",
        "package_name": body.package_name,
        "output": output,
        "plugins": list_all_plugins_status(),
    }
