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


def extract_frontend_api_paths() -> Set[tuple[str, str]]:
    """Parse frontend/src/lib/api.ts and extract all (HTTP Method, relative URL path) tuples."""
    if not API_TS_PATH.exists():
        pytest.skip("frontend/src/lib/api.ts does not exist")

    content = API_TS_PATH.read_text(encoding="utf-8")
    calls: Set[tuple[str, str]] = set()

    # 1. Plain strings: get<...>('/path...'), post<...>("/path...")
    pattern_plain = re.compile(r"""(get|post|put|delete|patch)<[^>]*>\(\s*['"](/[^'"]+)['"]""")
    for verb, m in pattern_plain.findall(content):
        cleaned = m.split("?")[0].rstrip("/")
        if cleaned:
            calls.add((verb.upper(), cleaned))

    # 2. Template strings: get<...>(`/path...`)
    pattern_template = re.compile(r"""(get|post|put|delete|patch)<[^>]*>\(\s*`(/[^`\n\r]+)""")
    for verb, raw_line in pattern_template.findall(content):
        base = raw_line.split("?")[0]
        base = re.sub(r"\$\{[^}]*\?.*", "", base)
        base = re.sub(r"\$\{qs.*", "", base)
        norm = re.sub(r"\$\{[^}]+\}", "{param}", base).rstrip("`").rstrip("/")
        if norm:
            calls.add((verb.upper(), norm))

    return calls


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
    """Verify that every endpoint invoked in frontend/src/lib/api.ts maps to a registered backend route and method."""
    frontend_calls = extract_frontend_api_paths()

    # Collect registered (methods, normalized_path)
    backend_routes: dict[str, set[str]] = {}
    for route in extract_all_app_routes(app):
        norm = re.sub(r"\{[a-zA-Z0-9_]+\}", "{param}", route.path).rstrip("/")
        if norm not in backend_routes:
            backend_routes[norm] = set()
        backend_routes[norm].update(route.methods)

    unmatched_calls = []
    for verb, raw in frontend_calls:
        target = f"/api/v1{raw}".rstrip("/")
        target_norm = re.sub(r"\{[a-zA-Z0-9_]+\}", "{param}", target)

        if target_norm in backend_routes:
            if verb in backend_routes[target_norm]:
                continue
            unmatched_calls.append(
                (verb, raw, f"Method {verb} not allowed on route (Registered: {backend_routes[target_norm]})")
            )
            continue

        # Check if route with param matches
        matched_prefix = False
        for b_path, b_methods in backend_routes.items():
            if b_path.endswith("{param}") and target_norm.startswith(b_path[:-7]):
                if verb in b_methods:
                    matched_prefix = True
                    break
        if matched_prefix:
            continue

        unmatched_calls.append((verb, raw, f"Route {target_norm} does not exist on backend"))

    assert not unmatched_calls, f"Frontend calls unmatched endpoints on backend: {unmatched_calls}"


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
