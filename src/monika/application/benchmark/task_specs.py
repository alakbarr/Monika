# ==============================================================================
# File: application/benchmark/task_specs.py
# ==============================================================================

"""
Backward-compatible facade for benchmark task specifications.

All task definitions, builders, and registries have been decomposed into
focused modular submodules under `monika.application.benchmark.task_specs`.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import monika.application.benchmark.task_specs as _pkg
from monika.application.benchmark.task_specs import *
from monika.application.benchmark.task_specs import (
    base as base,
    chat_cases as chat_cases,
    debate_cases as debate_cases,
    macro_cases as macro_cases,
    news_cases as news_cases,
    reflex_cases as reflex_cases,
    registry as registry,
    risk_cases as risk_cases,
    specialist_cases as specialist_cases,
    stage2_cases as stage2_cases,
)


class _TaskSpecsFacadeModule(types.ModuleType):
    """Facade module proxy that propagates runtime attribute mutations to task_specs submodules."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if hasattr(_pkg, name):
            setattr(_pkg, name, value)
        for mod in (
            base,
            macro_cases,
            stage2_cases,
            specialist_cases,
            debate_cases,
            risk_cases,
            news_cases,
            chat_cases,
            reflex_cases,
            registry,
        ):
            if hasattr(mod, name):
                setattr(mod, name, value)


_current_mod = sys.modules.get(__name__)
if _current_mod is not None and not isinstance(_current_mod, _TaskSpecsFacadeModule):
    _facade = _TaskSpecsFacadeModule(__name__, __doc__)
    _facade.__dict__.update(_current_mod.__dict__)
    sys.modules[__name__] = _facade
