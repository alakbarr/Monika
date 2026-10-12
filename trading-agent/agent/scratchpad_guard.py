"""Shim module: monika.application.agent.scratchpad_guard."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.scratchpad_guard")
_sys.modules[__name__] = _canonical
