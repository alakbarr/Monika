# ==============================================================================
# File: domain/models_resolver.py
# Monika Domain Database Model Dynamic Resolver
# ==============================================================================

"""
Dynamic model resolver for Domain layer.
Provides decoupled access to database model schemas registered by the infrastructure
layer at application startup, preserving hexagonal domain isolation without static
or dynamic imports of infrastructure packages.
"""

from __future__ import annotations

import sys
from typing import Any

_REGISTERED_MODELS: dict[str, Any] = {}


def register_model(name: str, model_cls: Any) -> None:
    """Register a database model class into the domain registry."""
    _REGISTERED_MODELS[name] = model_cls


def register_models(models_dict: dict[str, Any]) -> None:
    """Batch register model classes into the domain registry."""
    _REGISTERED_MODELS.update(models_dict)


def _load_infrastructure_model(name: str) -> Any:
    """Lazy fallback loader for infrastructure models."""
    try:
        import importlib

        mod = importlib.import_module("monika.infrastructure.database.models")
        return getattr(mod, name, None)
    except Exception:
        return None


def resolve_model(name: str) -> Any:
    """
    Resolves a registered database model by class name.
    Checks explicit registry first, then loaded modules, then lazy fallback.
    """
    if name in _REGISTERED_MODELS:
        return _REGISTERED_MODELS[name]

    mod = sys.modules.get("monika.infrastructure.database.models")
    if mod and hasattr(mod, name):
        val = getattr(mod, name)
        _REGISTERED_MODELS[name] = val
        return val

    val = _load_infrastructure_model(name)
    if val is not None:
        _REGISTERED_MODELS[name] = val
    return val


def clear_registered_models() -> None:
    """Clears registered models (for testing)."""
    _REGISTERED_MODELS.clear()


__all__ = ["resolve_model", "register_model", "register_models", "clear_registered_models"]
