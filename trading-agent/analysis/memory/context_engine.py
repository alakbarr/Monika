"""Shim module: monika.application.analysis.memory.context_engine."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.context_engine import *

_canonical = _importlib.import_module("monika.application.analysis.memory.context_engine")
_sys.modules[__name__] = _canonical
