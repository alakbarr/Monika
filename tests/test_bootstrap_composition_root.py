# ==============================================================================
# File: tests/test_bootstrap_composition_root.py
# Description: Unit tests for Unified Application Composition Root & ServiceContainer
# ==============================================================================

import pytest
from unittest.mock import MagicMock, patch

from monika.application.bootstrap import (
    BootstrapRuntime,
    bootstrap_runtime,
    bootstrap_application,
    build_application_container,
)
from monika.core.container import ServiceContainer


def test_bootstrap_runtime_lifecycle():
    BootstrapRuntime.reset()
    assert not BootstrapRuntime.is_initialized()
    bootstrap_runtime()
    assert BootstrapRuntime.is_initialized()
    # Idempotent call
    bootstrap_runtime()
    assert BootstrapRuntime.is_initialized()


def test_build_application_container_default():
    settings = {
        "trading": {"symbols": ["EURUSD"]},
        "execution": {"mode": "paper"},
    }
    container = build_application_container(settings=settings)
    assert isinstance(container, ServiceContainer)

    # Core settings and registry
    assert container.get("settings") == settings
    assert container.get("event_bus") is not None
    assert container.get("task_registry") is not None
    assert container.get("activity_logger") is not None

    # Application services
    assert container.get("portfolio_service") is not None
    assert container.get("trading_service") is not None
    assert container.get("market_data_service") is not None
    assert container.get("system_status_service") is not None
    assert container.get("market_intel_service") is not None


def test_build_application_container_with_overrides():
    mock_mt5 = MagicMock()
    mock_risk = MagicMock()
    overrides = {
        "mt5_client": mock_mt5,
        "risk_gate": mock_risk,
        "custom_marker": "active",
    }
    container = build_application_container(
        settings={"env": "test"},
        overrides=overrides,
    )
    assert container.get("mt5_client") is mock_mt5
    assert container.get("risk_gate") is mock_risk
    assert container.get("custom_marker") == "active"


def test_bootstrap_application_one_shot():
    with patch("monika.application.bootstrap.bootstrap_runtime") as mock_boot:
        settings = {"test": True}
        container = bootstrap_application(settings=settings)
        mock_boot.assert_called_once()
        assert container.get("settings") == settings
