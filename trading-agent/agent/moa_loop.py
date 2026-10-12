"""Shim module: monika.application.agent.moa_loop."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.moa_loop")
_sys.modules[__name__] = _canonical
