"""Shim module: monika.application.agent.socket_lifecycle_guard."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.socket_lifecycle_guard")
_sys.modules[__name__] = _canonical
