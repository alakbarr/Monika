"""Shim module: monika.application.agent.turn_liveness."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.turn_liveness import *

_canonical = _importlib.import_module("monika.application.agent.turn_liveness")
_sys.modules[__name__] = _canonical
