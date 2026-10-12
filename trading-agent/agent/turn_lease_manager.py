"""Shim module: monika.application.agent.turn_lease_manager."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.turn_lease_manager import *

_canonical = _importlib.import_module("monika.application.agent.turn_lease_manager")
_sys.modules[__name__] = _canonical
