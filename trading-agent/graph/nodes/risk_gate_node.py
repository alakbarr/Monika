"""Shim module: monika.application.graph.nodes.risk_gate_node."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.graph.nodes.risk_gate_node")
_sys.modules[__name__] = _canonical
