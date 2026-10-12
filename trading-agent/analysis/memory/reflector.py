"""Shim module: monika.application.analysis.memory.reflector."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.reflector import *

_canonical = _importlib.import_module("monika.application.analysis.memory.reflector")
_sys.modules[__name__] = _canonical
