"""Shim module: monika.application.agent.scratchpad_guard."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.scratchpad_guard import *

_canonical = _importlib.import_module("monika.application.agent.scratchpad_guard")
_sys.modules[__name__] = _canonical
