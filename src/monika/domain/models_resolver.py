# ==============================================================================
# File: domain/models_resolver.py
# Monika Domain Database Model Dynamic Resolver
# ==============================================================================

"""
Model resolver for Domain layer.
Provides decoupled access to database model schemas explicitly registered
by the composition root / infrastructure layer at application startup,
strictly preserving hexagonal domain isolation without static or dynamic imports
of infrastructure packages.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_REGISTERED_MODELS: dict[str, Any] = {}
_MODEL_PROVIDER: Callable[[str], Any] | None = None


def register_model(name: str, model_cls: Any) -> None:
    """Register a database model class into the domain registry."""
    _REGISTERED_MODELS[name] = model_cls


def register_models(models_dict: dict[str, Any]) -> None:
    """Batch register model classes into the domain registry."""
    _REGISTERED_MODELS.update(models_dict)


def register_model_provider(provider: Callable[[str], Any]) -> None:
    """Register a provider callable (from outer layers) to lazily supply model classes."""
    global _MODEL_PROVIDER
    _MODEL_PROVIDER = provider


def resolve_model(name: str) -> Any:
    """
    Resolves an explicitly registered database model by class name.
    Strictly isolated: does not dynamically inspect or import infrastructure packages.
    """
    if name in _REGISTERED_MODELS:
        return _REGISTERED_MODELS[name]
    if _MODEL_PROVIDER is not None:
        val = _MODEL_PROVIDER(name)
        if val is not None:
            _REGISTERED_MODELS[name] = val
            return val
    return None


def clear_registered_models() -> None:
    """Clears registered models (for testing)."""
    global _MODEL_PROVIDER
    _REGISTERED_MODELS.clear()
    _MODEL_PROVIDER = None


__all__ = [
    "resolve_model",
    "register_model",
    "register_models",
    "register_model_provider",
    "clear_registered_models",
]
