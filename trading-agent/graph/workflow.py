"""Shim module: monika.application.graph.workflow."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.graph.workflow")
_sys.modules[__name__] = _canonical
