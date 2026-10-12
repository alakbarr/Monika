"""Shim module: monika.application.graph.nodes.risk.portfolio_synthesis."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.graph.nodes.risk.portfolio_synthesis")
_sys.modules[__name__] = _canonical
