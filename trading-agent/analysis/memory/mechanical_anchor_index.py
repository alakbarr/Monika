"""Shim module: monika.application.analysis.memory.mechanical_anchor_index."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.mechanical_anchor_index import *

_canonical = _importlib.import_module("monika.application.analysis.memory.mechanical_anchor_index")
_sys.modules[__name__] = _canonical
