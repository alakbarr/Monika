"""Shim module: monika.application.agent.turn_stop_gates."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.turn_stop_gates")
_sys.modules[__name__] = _canonical
