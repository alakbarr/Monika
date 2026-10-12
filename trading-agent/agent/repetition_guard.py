"""Shim module: monika.application.agent.repetition_guard."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.repetition_guard")
_sys.modules[__name__] = _canonical
