"""Shim module: monika.application.graph.nodes.debate.subgraph."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.graph.nodes.debate.subgraph")
_sys.modules[__name__] = _canonical
