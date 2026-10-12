"""Shim module: monika.application.agent.deadline."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.deadline import *

_canonical = _importlib.import_module("monika.application.agent.deadline")
_sys.modules[__name__] = _canonical
