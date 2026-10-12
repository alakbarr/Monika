"""Shim module: monika.application.agent.startup_checks."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.startup_checks import *

_canonical = _importlib.import_module("monika.application.agent.startup_checks")
_sys.modules[__name__] = _canonical
