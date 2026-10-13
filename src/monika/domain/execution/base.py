# ==============================================================================
# File: domain/execution/base.py
# Monika Domain Execution Base Facade (Deprecated)
# ==============================================================================

"""
Backward-compatibility facade for ExecutionService mixin base.
Canonical location: monika.application.execution.service.base
"""

from __future__ import annotations

from typing import Any

_ExecutionServiceMixinBase: Any


def __getattr__(name: str) -> Any:
    if name == "_ExecutionServiceMixinBase":
        import importlib

        mod = importlib.import_module("monika.application.execution.service.base")
        return getattr(mod, "_ExecutionServiceMixinBase")
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ["_ExecutionServiceMixinBase"]
