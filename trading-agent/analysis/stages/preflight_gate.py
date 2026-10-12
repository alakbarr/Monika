"""Shim module: monika.application.analysis.stages.preflight_gate."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.stages.preflight_gate import *

_canonical = _importlib.import_module("monika.application.analysis.stages.preflight_gate")
_sys.modules[__name__] = _canonical
