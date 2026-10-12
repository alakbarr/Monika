"""Shim module: monika.application.analysis.validators.cross_timeframe_gate."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.validators.cross_timeframe_gate import *

_canonical = _importlib.import_module("monika.application.analysis.validators.cross_timeframe_gate")
_sys.modules[__name__] = _canonical
