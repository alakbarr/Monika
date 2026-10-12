"""Shim module: monika.application.graph.team_compiler."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.graph.team_compiler")
_sys.modules[__name__] = _canonical
