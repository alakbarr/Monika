"""Shim module: monika.application.agent.moa_alternation."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.moa_alternation import *

_canonical = _importlib.import_module("monika.application.agent.moa_alternation")
_sys.modules[__name__] = _canonical
