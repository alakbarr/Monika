"""Shim module: monika.application.analysis.memory.background_review."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.background_review import *

_canonical = _importlib.import_module("monika.application.analysis.memory.background_review")
_sys.modules[__name__] = _canonical
