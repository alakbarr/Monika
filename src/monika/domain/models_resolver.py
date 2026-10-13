# ==============================================================================
# File: domain/models_resolver.py
# Monika Domain Database Model Dynamic Resolver
# ==============================================================================

"""
Dynamic model resolver for Domain layer.
Allows domain entities, indicators, and risk evaluators to reference database models
at runtime without introducing static compile-time import couplings to the infrastructure layer.
"""

from __future__ import annotations

import sys
from typing import Any


def resolve_model(name: str) -> Any:
    """Dynamically resolves a database model by class name from infrastructure."""
    mod = sys.modules.get("monika.infrastructure.database.models")
    if mod and hasattr(mod, name):
        return getattr(mod, name)
    try:
        import importlib

        mod = importlib.import_module("monika.infrastructure.database.models")
        return getattr(mod, name, None)
    except Exception:
        return None


__all__ = ["resolve_model"]
