# ==============================================================================
# File: logging_observability/dashboard/rbac.py
# ==============================================================================

"""
Role-Based Access Control (RBAC) middleware and utilities for Dashboard API.

Roles:
  - VIEWER:   GET endpoints only (read all data, zero write/action access).
  - OPERATOR: + POST trigger-cycle, approve-trade, close-position, agent chat.
  - ADMIN:    + config editor, risk override, kill switch, full control.

Configuration via environment variables:
  DASHBOARD_API_KEYS=admin:sk-admin-xxx,operator:sk-ops-yyy,viewer:sk-view-zzz

  Backward-compatibility:
  If only DASHBOARD_API_KEY is set (singular), it maps to Role.ADMIN.
"""

from enum import Enum
from functools import wraps
import inspect
import logging
import os
import secrets
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request

logger = logging.getLogger("TradingAgent.DashboardRBAC")


class Role(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


# Role hierarchy weights: admin (2) > operator (1) > viewer (0)
ROLE_HIERARCHY: Dict[Role, int] = {
    Role.VIEWER: 0,
    Role.OPERATOR: 1,
    Role.ADMIN: 2,
}

# Standard endpoint mappings for role requirements
ENDPOINT_ROLES: Dict[str, Role] = {
    "GET": Role.VIEWER,
    "POST:/api/actions/trigger-cycle": Role.OPERATOR,
    "POST:/api/actions/approve-trade": Role.OPERATOR,
    "POST:/api/actions/close-position": Role.OPERATOR,
    "POST:/api/actions/override-risk": Role.ADMIN,
    "PUT:/api/config/settings": Role.ADMIN,
    "POST:/api/actions/kill": Role.ADMIN,
}


def resolve_role(api_key: str, is_localhost: bool = False) -> Role:
    """
    Resolve client API key to a Role.
    
    Supports:
    1. DASHBOARD_API_KEYS format: "admin:key1,operator:key2,viewer:key3"
    2. DASHBOARD_API_KEY fallback: single key mapped to Role.ADMIN (100% backward-compat)
    3. Unconfigured localhost dev mode: defaults to Role.ADMIN
    """
    clean_key = (api_key or "").strip()
    multi_keys = os.getenv("DASHBOARD_API_KEYS", "").strip()
    single_key = os.getenv("DASHBOARD_API_KEY", "").strip()

    # 1. Multi-key check
    if multi_keys and clean_key:
        for entry in multi_keys.split(","):
            entry = entry.strip()
            if not entry or ":" not in entry:
                continue
            role_part, key_part = entry.split(":", 1)
            role_part = role_part.strip().lower()
            key_part = key_part.strip()
            if secrets.compare_digest(key_part, clean_key):
                try:
                    return Role(role_part)
                except ValueError:
                    logger.warning(f"Unknown role '{role_part}' in DASHBOARD_API_KEYS, defaulting to VIEWER")
                    return Role.VIEWER

    # 2. Single-key check (Admin role)
    if single_key and clean_key:
        if secrets.compare_digest(single_key, clean_key):
            return Role.ADMIN

    # 3. Localhost fallback if no keys configured
    if not multi_keys and not single_key and is_localhost:
        return Role.ADMIN

    raise PermissionError("Invalid or missing API key")


def require_role(minimum: Role):
    """
    Decorator for FastAPI endpoint handlers.
    Rejects the request with HTTP 403 if the caller's role is below the minimum required role.
    """
    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)
        has_request_param = "request" in sig.parameters

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Optional[Request] = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request) or hasattr(arg, "state"):
                        request = arg
                        break

            if request is None:
                raise HTTPException(
                    status_code=403,
                    detail="Forbidden: Request context missing for RBAC validation"
                )

            role = getattr(request.state, "role", None)
            if role is None:
                is_localhost = getattr(request.state, "is_localhost", False)
                role = Role.ADMIN if is_localhost else None

            if role is None:
                raise HTTPException(status_code=401, detail="Unauthorized: Role not found or not authenticated")

            if isinstance(role, str):
                try:
                    role = Role(role)
                except ValueError:
                    role = Role.VIEWER

            if ROLE_HIERARCHY.get(role, -1) < ROLE_HIERARCHY.get(minimum, 0):
                raise HTTPException(
                    status_code=403,
                    detail=f"Forbidden: Action requires '{minimum.value}' role, current role is '{role.value}'"
                )

            call_kwargs = dict(kwargs)
            if not has_request_param and "request" in call_kwargs:
                del call_kwargs["request"]

            return await func(*args, **call_kwargs)

        if not has_request_param:
            new_params = list(sig.parameters.values()) + [
                inspect.Parameter("request", inspect.Parameter.KEYWORD_ONLY, annotation=Request)
            ]
            wrapper.__signature__ = sig.replace(parameters=new_params)
            if hasattr(wrapper, "__wrapped__"):
                del wrapper.__wrapped__

        return wrapper

    return decorator
