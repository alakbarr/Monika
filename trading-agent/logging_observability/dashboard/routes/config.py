# ==============================================================================
# File: logging_observability/dashboard/routes/config.py
# Description: Configuration Management Endpoints (View, Schema, Hot-Update)
# ==============================================================================

import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from logging_observability.dashboard.rbac import Role, require_role
from logging_observability.dashboard.routes.common import (
    _get_settings_path as default_get_settings_path,
    broadcast_live_event,
    get_dashboard_dependency,
)

logger = logging.getLogger("TradingAgent.DashboardAPI.Config")

router = APIRouter()
config_router = router


def _resolve_settings_path() -> str:
    """Resolve settings path, preferring patched api._get_settings_path if available."""
    try:
        import logging_observability.dashboard.api as api
        if hasattr(api, "_get_settings_path"):
            return api._get_settings_path()
    except Exception:
        pass
    return default_get_settings_path()


class ConfigUpdateRequest(BaseModel):
    settings: Dict[str, Any] = Field(description="Full settings dictionary to validate and persist")
    reason: Optional[str] = Field(default="Config updated via Dashboard", description="Reason for activity audit log")


@router.get("/api/config/settings", tags=["Config"])
@require_role(Role.VIEWER)
async def get_config_settings(request: Request):
    """Return full settings.yaml as structured JSON along with raw YAML text."""
    from config.settings import load_settings

    settings_path = _resolve_settings_path()
    settings = load_settings(settings_path)
    raw_yaml = ""
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                raw_yaml = f.read()
        except Exception as e:
            logger.warning(f"Failed reading raw settings yaml from {settings_path}: {e}")
    return {
        "status": "success",
        "settings": settings,
        "raw_yaml": raw_yaml,
        "file_path": settings_path,
    }


@router.get("/api/config/schema", tags=["Config"])
@require_role(Role.VIEWER)
async def get_config_schema(request: Request):
    """Return Pydantic TradingAgentConfig as JSON Schema for form rendering."""
    try:
        from config.schemas import TradingAgentConfig
        return TradingAgentConfig.model_json_schema()
    except Exception as e:
        logger.error(f"Failed generating TradingAgentConfig JSON schema: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.get("/api/config/plugins/schemas", tags=["Config"])
@require_role(Role.VIEWER)
async def get_all_plugin_config_schemas(request: Request):
    """Return dictionary of plugin_id -> JSON Schema for registered plugins."""
    from harness.engine import get_plugin_engine
    engine = get_plugin_engine()
    schemas = {}
    if engine:
        for pid, plugin in engine.plugins.items():
            if hasattr(plugin, "config_model") and plugin.config_model:
                try:
                    schemas[pid] = plugin.config_model.model_json_schema()
                    continue
                except Exception:
                    pass
            schemas[pid] = {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "title": f"{pid.capitalize()}Config",
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean", "default": True},
                },
                "additionalProperties": True,
            }
    return schemas


@router.get("/api/config/plugins/{plugin_id}/schema", tags=["Config"])
@require_role(Role.VIEWER)
async def get_plugin_config_schema(plugin_id: str, request: Request):
    """Return JSON Schema for a specific plugin configuration if available."""
    from harness.engine import get_plugin_engine
    engine = get_plugin_engine()
    if engine and plugin_id in engine.plugins:
        plugin = engine.plugins[plugin_id]
        if hasattr(plugin, "config_model") and plugin.config_model:
            try:
                return plugin.config_model.model_json_schema()
            except Exception:
                pass
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": f"{plugin_id.capitalize()}Config",
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean", "default": True},
        },
        "additionalProperties": True,
    }


@router.put("/api/config/settings", tags=["Config"])
@require_role(Role.ADMIN)
async def update_config_settings(payload: ConfigUpdateRequest, request: Request):
    """Validate payload, create .bak backup, write settings.yaml, trigger hot-reload, and log."""
    from config.settings import validate_config, _deep_merge
    from database.db import AsyncSessionLocal
    from database.models import ActivityLog

    settings_path = _resolve_settings_path()
    existing_settings: Dict[str, Any] = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                existing_settings = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to read existing settings for merge: {e}")

    # Merge payload settings into existing settings to avoid wiping unmanaged sections
    merged_settings = _deep_merge(existing_settings, payload.settings) if existing_settings else payload.settings

    try:
        validate_config(merged_settings)
    except Exception as e:
        return JSONResponse(
            status_code=422,
            content={"status": "validation_error", "message": f"Validation failed: {str(e)}"},
        )

    ts_suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    timestamped_bak = f"{settings_path}.{ts_suffix}.bak"
    bak_path = f"{settings_path}.bak"

    try:
        if os.path.exists(settings_path):
            shutil.copy2(settings_path, timestamped_bak)
            shutil.copy2(settings_path, bak_path)
    except Exception as e:
        logger.warning(f"Failed to create config backup: {e}")

    try:
        from config.atomic_writer import AtomicConfigWriter
        AtomicConfigWriter.write(settings_path, merged_settings, create_backup=False)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "write_error", "message": f"Failed writing settings file: {str(e)}"},
        )

    reloaded = False
    reloader = get_dashboard_dependency("risk_parameter_reloader")
    if reloader and hasattr(reloader, "check_and_reload"):
        try:
            reloaded = reloader.check_and_reload()
        except Exception as e:
            logger.warning(f"Reloader trigger failed: {e}")

    risk_gate = get_dashboard_dependency("risk_gate")
    if risk_gate and hasattr(risk_gate, "update_parameters"):
        try:
            risk_gate.update_parameters(merged_settings)
            reloaded = True
        except Exception as e:
            logger.warning(f"Risk gate parameter update failed: {e}")

    runtime_settings = get_dashboard_dependency("settings")
    if runtime_settings and isinstance(runtime_settings, dict):
        runtime_settings.clear()
        runtime_settings.update(merged_settings)

    try:
        async with AsyncSessionLocal() as session:
            session.add(ActivityLog(
                category="system",
                description=f"Configuration updated via Dashboard ({payload.reason})",
                actor="dashboard_admin",
            ))
            await session.commit()
    except Exception as e:
        logger.debug(f"Failed writing activity log: {e}")

    await broadcast_live_event("config_updated", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": payload.reason,
        "reloaded": reloaded,
    })

    return {
        "status": "success",
        "message": "Configuration validated, persisted to settings.yaml, and reloaded.",
        "backup_path": bak_path,
        "timestamped_backup": timestamped_bak,
        "reloaded": reloaded,
    }
