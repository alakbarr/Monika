"""Shim module: monika.application.analysis.memory.prompt_cache_boundary."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.prompt_cache_boundary import *

_canonical = _importlib.import_module("monika.application.analysis.memory.prompt_cache_boundary")
_sys.modules[__name__] = _canonical
