"""Shim module: monika.application.analysis.memory.progressive_loader."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.progressive_loader import *

_canonical = _importlib.import_module("monika.application.analysis.memory.progressive_loader")
_sys.modules[__name__] = _canonical
