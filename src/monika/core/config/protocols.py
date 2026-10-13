"""
Configuration Protocols and Decoupled Extensibility Hooks.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, runtime_checkable
from collections.abc import Callable


@runtime_checkable
class CredentialResolver(Protocol):
    """Protocol for resolving and updating credentials without hard-coupling to infrastructure."""

    base_cooldown_seconds: float
    max_cooldown_seconds: float


# Registry for decoupled configuration lifecycle listeners
_CONFIG_LISTENERS: list[Callable[[dict[str, Any]], None]] = []


def register_config_listener(listener: Callable[[dict[str, Any]], None]) -> None:
    """Register a callback that receives configuration updates."""
    if listener not in _CONFIG_LISTENERS:
        _CONFIG_LISTENERS.append(listener)


def notify_config_listeners(config: dict[str, Any]) -> None:
    """Notify all registered listeners about updated configuration."""
    for listener in _CONFIG_LISTENERS:
        try:
            listener(config)
        except Exception:
            pass
