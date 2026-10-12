"""Shim module: monika.infrastructure.graph.checkpointers.dual_checkpointer."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.infrastructure.graph.checkpointers.dual_checkpointer")
_sys.modules[__name__] = _canonical
