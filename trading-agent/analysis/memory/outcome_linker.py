"""Shim module: monika.application.analysis.memory.outcome_linker."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.outcome_linker import *

_canonical = _importlib.import_module("monika.application.analysis.memory.outcome_linker")
_sys.modules[__name__] = _canonical
