"""Shim module: monika.application.agent.estop."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.estop import *

_canonical = _importlib.import_module("monika.application.agent.estop")
_sys.modules[__name__] = _canonical
