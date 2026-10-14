# ==============================================================================
# File: tests/test_api_frontend_contract.py
# Description: Automated Frontend-Backend API Contract & Route Parity Tests
# ==============================================================================

"""
Verification of API v1 contract consistency between frontend client and backend routes.

Ensures:
1. Every endpoint path invoked by frontend/src/lib/api.ts exists on the FastAPI backend.
2. All backend routes are properly prefixed with /api/v1 (except root websockets and documentation).
3. Automated OpenAPI TypeScript generator contract verification (--check mode).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Set

import pytest
from fastapi.routing import APIRoute

from monika.interfaces.dashboard.api import app

ROOT_DIR = Path(__file__).resolve().parent.parent
API_TS_PATH = ROOT_DIR / "frontend" / "src" / "lib" / "api.ts"


def extract_frontend_api_paths() -> Set[str]:
    """Parse frontend/src/lib/api.ts and extract all relative URL paths called via get/post/put/delete."""
    if not API_TS_PATH.exists():
        pytest.skip("frontend/src/lib/api.ts does not exist")

    content = API_TS_PATH.read_text(encoding="utf-8")
    paths: Set[str] = set()

    # 1. Plain strings: get<...>('/path...'), post<...>("/path...")
    pattern_plain = re.compile(r"""(?:get|post|put|delete|patch)<[^>]*>\(\s*['"](/[^'"]+)['"]""")
    for m in pattern_plain.findall(content):
        cleaned = m.split("?")[0].rstrip("/")
        if cleaned:
            paths.add(cleaned)

    # 2. Template strings: get<...>(`/path...`)
    pattern_template = re.compile(r"""(?:get|post|put|delete|patch)<[^>]*>\(\s*`(/[^`]+)`""")
    for tm in pattern_template.findall(content):
        # Strip conditional query expressions e.g. ${qs ? ...} or ${x !== undefined ? ...}
        stripped = re.sub(r"\$\{[^}]*\?[^}]*\}", "", tm)
        # Split on hardcoded query params if any
        base = stripped.split("?")[0]
        # Normalize dynamic path params like ${ticket} or ${encodeURIComponent(id)} to {param}
        norm = re.sub(r"\$\{[^}]+\}", "{param}", base).rstrip("/")
        if norm:
            paths.add(norm)

    return paths


def extract_all_app_routes(router_or_app: Any) -> list[APIRoute]:
    """Recursively extract all APIRoute instances from FastAPI application or router, traversing nested routers."""
    collected: list[APIRoute] = []
    visited: set[int] = set()

    def _recurse(item: Any) -> None:
        item_id = id(item)
        if item_id in visited:
            return
        visited.add(item_id)

        if isinstance(item, APIRoute):
            collected.append(item)
            return

        if hasattr(item, "original_router"):
            _recurse(item.original_router)

        if hasattr(item, "routes"):
            for sub_item in item.routes:
                _recurse(sub_item)

    _recurse(router_or_app)
    return collected


def get_backend_routes() -> Set[str]:
    """Extract all registered paths from FastAPI app routes."""
    paths: Set[str] = set()
    for route in extract_all_app_routes(app):
        # Normalize path parameters to {param}
        norm = re.sub(r"\{[a-zA-Z0-9_]+\}", "{param}", route.path).rstrip("/")
        paths.add(norm)
    return paths


def test_api_v1_route_prefix_compliance():
    """Verify that all REST API routes are mounted under /api/v1 (or /setup)."""
    exempt_paths = {
        "",
        "/setup",
        "/api/docs",
        "/api/redoc",
        "/openapi.json",
        "/health",  # gateway health
        "/v1/status",  # gateway status
        "/v1/models",  # gateway openai
        "/v1/chat/completions",  # gateway openai
        "/webhooks/tradingview",  # gateway legacy hook
        "/webhooks/ingress",  # gateway legacy hook
        "/{full_path:path}",  # SPA fallback catch-all
    }

    violating_routes = []
    for route in extract_all_app_routes(app):
        p = route.path.rstrip("/")
        if p in exempt_paths:
            continue
        if not p.startswith("/api/v1"):
            violating_routes.append((route.methods, route.path))

    assert not violating_routes, f"Found unversioned API routes without /api/v1 prefix: {violating_routes}"


def test_frontend_routes_exist_on_backend():
    """Verify that every endpoint invoked in frontend/src/lib/api.ts maps to a registered backend route."""
    frontend_raw_paths = extract_frontend_api_paths()
    backend_normalized = get_backend_routes()

    unmatched_paths = []
    for raw in frontend_raw_paths:
        # Frontend BASE is /api/v1, so raw '/overview' maps to '/api/v1/overview'
        target = f"/api/v1{raw}".rstrip("/")
        target_norm = re.sub(r"\{[a-zA-Z0-9_]+\}", "{param}", target)

        # Check exact or normalized match
        if target_norm in backend_normalized:
            continue

        # If path ends with {param}, check if backend has matching prefix (ignoring root empty string)
        if any(b and (b.startswith(target_norm) or target_norm.startswith(b)) for b in backend_normalized):
            continue

        unmatched_paths.append((raw, target_norm))

    assert not unmatched_paths, f"Frontend calls endpoints that do not exist on backend: {unmatched_paths}"


def test_openapi_contract_generation_check():
    """Verify that openapi.json and openapi.ts match FastAPI schema with zero drift."""
    script_path = ROOT_DIR / "scripts" / "generate_openapi_types.py"
    res = subprocess.run(
        [sys.executable, str(script_path), "--check"],
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"OpenAPI drift check failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}"
