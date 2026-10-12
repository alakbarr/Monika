"""Shim module: monika.application.agent.bounded_response."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.bounded_response")
_sys.modules[__name__] = _canonical
