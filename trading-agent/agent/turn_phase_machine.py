"""Shim module: monika.application.agent.turn_phase_machine."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.turn_phase_machine")
_sys.modules[__name__] = _canonical
