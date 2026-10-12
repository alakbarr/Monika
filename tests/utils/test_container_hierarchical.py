"""
Unit tests for ServiceContainer hierarchical scoping (extend, isolate, intercept) and Context alias.
"""
from utils.infra.container import ServiceContainer, Context


def test_service_container_hierarchical_extend():
    root = ServiceContainer()
    root.register("db_url", "postgresql://localhost:5432/monika")
    root.register("app_name", "Monika")

    child = root.extend()
    # Inherits from root
    assert child.get("db_url") == "postgresql://localhost:5432/monika"
    assert child.get("app_name") == "Monika"
    assert child.has("db_url") is True

    # Child override does not affect root
    child.register("app_name", "ChildMonika")
    assert child.get("app_name") == "ChildMonika"
    assert root.get("app_name") == "Monika"


def test_service_container_isolate_and_intercept():
    root = ServiceContainer()
    root.register("rate_limit", 100)

    # Isolate
    isolated = root.isolate("isolated_broker")
    assert isolated.get("_scope_name") == "isolated_broker"
    assert isolated.get("rate_limit") == 100

    # Intercept
    intercepted = root.intercept({"rate_limit": 50, "mock_mode": True})
    assert intercepted.get("rate_limit") == 50
    assert intercepted.get("mock_mode") is True
    assert root.get("rate_limit") == 100
    assert root.get("mock_mode") is None


def test_service_container_context_alias():
    ctx = Context()
    ctx.provide("service_a", {"status": "ok"})
    assert ctx.get("service_a") == {"status": "ok"}
