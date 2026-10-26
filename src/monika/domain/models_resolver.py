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

from collections.abc import Callable, Iterable
from typing import Any

_REGISTERED_MODELS: dict[str, Any] = {}
_MODEL_PROVIDER: Callable[[str], Any] | None = None
_BOUND_MODULE_GLOBALS: list[tuple[dict[str, Any], tuple[str, ...]]] = []


def _sync_bound_modules(updated_names: Iterable[str] | None = None) -> None:
    """Synchronize bound module global dictionaries with currently registered models."""
    filter_set = set(updated_names) if updated_names is not None else None
    for target_globals, names in _BOUND_MODULE_GLOBALS:
        for name in names:
            if filter_set is not None and name not in filter_set:
                continue
            resolved = resolve_model(name)
            if resolved is not None:
                target_globals[name] = resolved


def bind_module_models(target_globals: dict[str, Any], model_names: Iterable[str]) -> None:
    """Bind and auto-synchronize model references in a module's global namespace.

    Ensures that if domain modules are imported before infrastructure database models
    are registered, their module-level model attributes are automatically updated as
    soon as registration occurs.
    """
    names = tuple(model_names)
    for existing_globals, existing_names in _BOUND_MODULE_GLOBALS:
        if existing_globals is target_globals and existing_names == names:
            _sync_bound_modules(names)
            return
    _BOUND_MODULE_GLOBALS.append((target_globals, names))
    for name in names:
        resolved = resolve_model(name)
        if resolved is not None or name not in target_globals:
            target_globals[name] = resolved


def register_model(name: str, model_cls: Any) -> None:
    """Register a database model class into the domain registry."""
    _REGISTERED_MODELS[name] = model_cls
    _sync_bound_modules((name,))


def register_models(models_dict: dict[str, Any]) -> None:
    """Batch register model classes into the domain registry."""
    _REGISTERED_MODELS.update(models_dict)
    _sync_bound_modules(models_dict.keys())


def register_model_provider(provider: Callable[[str], Any]) -> None:
    """Register a provider callable (from outer layers) to lazily supply model classes."""
    global _MODEL_PROVIDER
    _MODEL_PROVIDER = provider
    _sync_bound_modules()


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
    "bind_module_models",
    "register_model",
    "register_models",
    "register_model_provider",
    "clear_registered_models",
]
