"""Shim module: monika.application.graph.reactive_graph."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.graph.reactive_graph")
_sys.modules[__name__] = _canonical
