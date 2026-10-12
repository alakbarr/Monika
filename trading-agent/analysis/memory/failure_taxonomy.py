"""Shim module: monika.application.analysis.memory.failure_taxonomy."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.failure_taxonomy import *

_canonical = _importlib.import_module("monika.application.analysis.memory.failure_taxonomy")
_sys.modules[__name__] = _canonical
