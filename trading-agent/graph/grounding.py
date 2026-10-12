"""Shim module: monika.application.graph.grounding."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.graph.grounding")
_sys.modules[__name__] = _canonical
