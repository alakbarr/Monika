"""Shim module: monika.application.analysis.memory.memory_lifecycle_gc."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.memory_lifecycle_gc import *

_canonical = _importlib.import_module("monika.application.analysis.memory.memory_lifecycle_gc")
_sys.modules[__name__] = _canonical
