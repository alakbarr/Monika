"""Shim module: monika.application.analysis.memory.layered_memory."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.layered_memory import *

_canonical = _importlib.import_module("monika.application.analysis.memory.layered_memory")
_sys.modules[__name__] = _canonical
