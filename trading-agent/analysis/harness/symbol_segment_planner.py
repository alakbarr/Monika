"""Shim module: monika.application.analysis.harness.symbol_segment_planner."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.symbol_segment_planner import *

_canonical = _importlib.import_module("monika.application.analysis.harness.symbol_segment_planner")
_sys.modules[__name__] = _canonical
