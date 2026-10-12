"""Shim module: monika.application.agent.turn_phase_machine."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.turn_phase_machine import *

_canonical = _importlib.import_module("monika.application.agent.turn_phase_machine")
_sys.modules[__name__] = _canonical
