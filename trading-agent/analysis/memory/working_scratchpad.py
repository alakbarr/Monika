"""Shim module: monika.application.analysis.memory.working_scratchpad."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.working_scratchpad import *

_canonical = _importlib.import_module("monika.application.analysis.memory.working_scratchpad")
_sys.modules[__name__] = _canonical
