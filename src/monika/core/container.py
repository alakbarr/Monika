# ==============================================================================
# Package: monika.core
# File: container.py
# ==============================================================================

"""
Dependency Injection / Service Container (I1).
Provides centralized registry for core system services and lifecycle resources.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger("TradingAgent.Container")
T = TypeVar("T")


class ServiceContainer:
    """Lightweight inversion of control (IoC) service container with hierarchical scoping."""

    def __init__(self, parent: Optional["ServiceContainer"] = None):
        self._parent: Optional["ServiceContainer"] = parent
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[["ServiceContainer"], Any]] = {}

    def register(self, name: str, instance: Any) -> None:
        """Register an existing singleton instance."""
        self._services[name] = instance
        logger.debug(f"[Container] Registered instance for '{name}'")

    register_instance = register
    provide = register

    def register_factory(self, name: str, factory: Callable[["ServiceContainer"], Any]) -> None:
        """Register a lazy factory for a service."""
        self._factories[name] = factory
        logger.debug(f"[Container] Registered factory for '{name}'")

    def get(self, name: str, default: Any = None) -> Any:
        """Resolve a service by name, walking parent chain if not present locally."""
        if name in self._services:
            return self._services[name]
        if name in self._factories:
            instance = self._factories[name](self)
            self._services[name] = instance
            return instance
        if self._parent is not None:
            return self._parent.get(name, default)
        return default

    def has(self, name: str) -> bool:
        """Check if service is registered in local container or any parent."""
        if name in self._services or name in self._factories:
            return True
        if self._parent is not None:
            return self._parent.has(name)
        return False

    def extend(self) -> "ServiceContainer":
        """Returns a child scope inheriting this container with scoped isolation."""
        return ServiceContainer(parent=self)

    def isolate(self, name: str) -> "ServiceContainer":
        """Returns an independent child bucket isolated under a namespace."""
        child = self.extend()
        child.register("_scope_name", name)
        return child

    def intercept(self, overrides: Dict[str, Any]) -> "ServiceContainer":
        """Returns a child scope with injected configuration or mock overrides."""
        child = self.extend()
        for k, v in overrides.items():
            child.register(k, v)
        return child

    def clear(self) -> None:
        """Clear all registered services in this container."""
        self._services.clear()
        self._factories.clear()

    # Typed convenience properties
    @property
    def settings(self) -> dict:
        return self.get("settings", {})

    @property
    def activity_logger(self) -> Any:
        return self.get("activity_logger")

    @property
    def event_store(self) -> Any:
        return self.get("event_store")

    @property
    def mt5_client(self) -> Any:
        return self.get("mt5_client")

    @property
    def plugin_manager(self) -> Any:
        return self.get("plugin_manager")


    _instance: Optional["ServiceContainer"] = None

    @classmethod
    def get_instance(cls) -> "ServiceContainer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None


# Backward compatibility alias for ServiceContainer
Context = ServiceContainer


def get_container() -> ServiceContainer:
    """Get the global ServiceContainer singleton."""
    return ServiceContainer.get_instance()


__all__ = [
    "ServiceContainer",
    "Context",
    "get_container",
]
