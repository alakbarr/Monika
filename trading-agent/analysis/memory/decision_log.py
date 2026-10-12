"""Shim module: monika.application.analysis.memory.decision_log."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.memory.decision_log import *

_canonical = _importlib.import_module("monika.application.analysis.memory.decision_log")
_sys.modules[__name__] = _canonical
