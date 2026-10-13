# ==============================================================================
# File: logging_observability/dashboard/routes/config.py
# Description: Configuration Management Endpoints (View, Schema, Hot-Update)
# ==============================================================================

import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import yaml
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from monika.interfaces.dashboard.rbac import Role, require_role
from monika.interfaces.dashboard.routes.common import (
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
        import monika.interfaces.dashboard.api as api

        if hasattr(api, "_get_settings_path"):
            return api._get_settings_path()
    except Exception:
        pass
    return default_get_settings_path()


class ConfigUpdateRequest(BaseModel):
    settings: Dict[str, Any] = Field(description="Full settings dictionary to validate and persist")
    reason: Optional[str] = Field(default="Config updated via Dashboard", description="Reason for activity audit log")


SENSITIVE_KEY_PATTERN = re.compile(
    r"(^|_)("
    r"api_key|secret_key|secret|password|credential|passwd|"
    r"private_key|auth_token|token|passphrase|webhook_url|webhook|"
    r"database_url|db_url|conn_str|connection_string"
    r")($|_)",
    re.IGNORECASE,
)

NON_SENSITIVE_KEYS = {
    "max_tokens",
    "token_limit",
    "max_output_tokens",
    "token_budget",
    "tokens",
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "total_tokens",
    "tokens_per_second",
    "tps",
    "token_coalescing_ms",
    "max_token_budget",
}


def _mask_sensitive_data(obj: Any) -> Any:
    """Recursively mask sensitive values in dicts, lists, or primitives with '********'."""
    if isinstance(obj, dict):
        masked = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in NON_SENSITIVE_KEYS:
                masked[k] = _mask_sensitive_data(v)
            elif isinstance(v, (int, float, bool)):
                # Never mask numerical configuration parameters or booleans
                masked[k] = v
            elif isinstance(k, str) and SENSITIVE_KEY_PATTERN.search(k):
                if isinstance(v, str) and v.strip():
                    masked[k] = "********"
                elif isinstance(v, dict):
                    masked[k] = _mask_sensitive_data(v)
                else:
                    masked[k] = "********"
            else:
                masked[k] = _mask_sensitive_data(v)
        return masked
    elif isinstance(obj, list):
        return [_mask_sensitive_data(item) for item in obj]
    return obj


def _mask_yaml_text(text: str) -> str:
    """Mask sensitive values in raw YAML string representation."""
    if not text:
        return text

    pattern = re.compile(
        r"^(\s*([\w\.\-_]+)\s*:\s*)(['\"]?)(.+?)\3(\s*(?:#.*)?)$",
        re.MULTILINE,
    )

    def _repl(match: re.Match) -> str:
        prefix = match.group(1)
        key_name = match.group(2).lower()
        quote = match.group(3)
        val = match.group(4)
        comment = match.group(5)

        # Skip non-sensitive tokens like max_tokens, token_budget
        if key_name in NON_SENSITIVE_KEYS or any(
            nsk in key_name for nsk in ("max_tokens", "token_budget", "tokens_per_")
        ):
            return match.group(0)

        # Check if sensitive pattern matches key_name
        if SENSITIVE_KEY_PATTERN.search(key_name):
            if not val.strip():
                return match.group(0)
            return f"{prefix}{quote}********{quote}{comment}"

        return match.group(0)

    masked_text = pattern.sub(_repl, text)
    try:
        from monika.core.security.credential_vault import vault

        masked_text = vault.redact(masked_text)
    except Exception:
        pass
    return masked_text


@router.get("/api/config/settings", tags=["Config"])
@require_role(Role.VIEWER)
async def get_config_settings(request: Request):
    """Return full settings.yaml as structured JSON along with raw YAML text with secrets masked."""
    from monika.core.config.settings import load_settings

    settings_path = _resolve_settings_path()
    settings = load_settings(settings_path)
    raw_yaml = ""
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                raw_yaml = f.read()
        except Exception as e:
            logger.warning(f"Failed reading raw settings yaml from {settings_path}: {e}")

    masked_settings = _mask_sensitive_data(settings)
    masked_yaml = _mask_yaml_text(raw_yaml)

    return {
        "status": "success",
        "settings": masked_settings,
        "raw_yaml": masked_yaml,
        "file_path": settings_path,
    }


@router.get("/api/config/schema", tags=["Config"])
@require_role(Role.VIEWER)
async def get_config_schema(request: Request):
    """Return Pydantic TradingAgentConfig as JSON Schema for form rendering."""
    try:
        from monika.core.config.schemas import TradingAgentConfig

        return TradingAgentConfig.model_json_schema()
    except Exception as e:
        logger.error(f"Failed generating TradingAgentConfig JSON schema: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.get("/api/config/plugins/schemas", tags=["Config"])
@require_role(Role.VIEWER)
async def get_all_plugin_config_schemas(request: Request):
    """Return dictionary of plugin_id -> JSON Schema for registered plugins."""
    from monika.application.harness.engine import get_plugin_engine

    engine = get_plugin_engine()
    schemas = {}
    if engine:
        for pid, plugin in engine.plugins.items():
            cfg_model = getattr(plugin, "config_model", None)
            if cfg_model is not None:
                try:
                    schemas[pid] = cfg_model.model_json_schema()
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
    from monika.application.harness.engine import get_plugin_engine

    engine = get_plugin_engine()
    if engine and plugin_id in engine.plugins:
        plugin = engine.plugins[plugin_id]
        cfg_model = getattr(plugin, "config_model", None)
        if cfg_model is not None:
            try:
                return cfg_model.model_json_schema()
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
    from monika.core.config.settings import validate_config, _deep_merge
    from monika.infrastructure.database.db import AsyncSessionLocal
    from monika.infrastructure.database.models import ActivityLog

    settings_path = _resolve_settings_path()
    existing_settings: Dict[str, Any] = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                existing_settings = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to read existing settings for merge: {e}")

    def _unmask_against_existing(incoming: Any, baseline: Any) -> Any:
        if isinstance(incoming, dict) and isinstance(baseline, dict):
            unmasked: Dict[str, Any] = {}
            for k, v in incoming.items():
                base_v = baseline.get(k)
                unmasked[k] = _unmask_against_existing(v, base_v)
            return unmasked
        elif isinstance(incoming, list) and isinstance(baseline, list):
            return [
                _unmask_against_existing(item, baseline[i] if i < len(baseline) else None)
                for i, item in enumerate(incoming)
            ]
        elif incoming == "********" and baseline is not None:
            return baseline
        return incoming

    clean_payload_settings = (
        _unmask_against_existing(payload.settings, existing_settings) if existing_settings else payload.settings
    )

    # Merge payload settings into existing settings to avoid wiping unmanaged sections
    merged_settings = (
        _deep_merge(existing_settings, clean_payload_settings) if existing_settings else clean_payload_settings
    )

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
        from monika.core.config.atomic_writer import AtomicConfigWriter

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
        from monika.core.config.config_manager import ConfigManager

        ConfigManager.get_instance().check_for_updates()
        reloaded = True
    except Exception as e:
        logger.debug(f"ConfigManager check_for_updates failed: {e}")

    try:
        async with AsyncSessionLocal() as session:
            session.add(
                ActivityLog(
                    category="system",
                    description=f"Configuration updated via Dashboard ({payload.reason})",
                    actor="dashboard_admin",
                )
            )
            await session.commit()
    except Exception as e:
        logger.debug(f"Failed writing activity log: {e}")

    await broadcast_live_event(
        "config_updated",
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": payload.reason,
            "reloaded": reloaded,
        },
    )

    return {
        "status": "success",
        "message": "Configuration validated, persisted to settings.yaml, and reloaded.",
        "backup_path": bak_path,
        "timestamped_backup": timestamped_bak,
        "reloaded": reloaded,
    }
