"""Shim module: monika.application.agent.moa_trace."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.moa_trace import *

_canonical = _importlib.import_module("monika.application.agent.moa_trace")
_sys.modules[__name__] = _canonical
