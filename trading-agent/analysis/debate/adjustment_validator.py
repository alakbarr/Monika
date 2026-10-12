"""Shim module: monika.application.analysis.debate.adjustment_validator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.debate.adjustment_validator import *

_canonical = _importlib.import_module("monika.application.analysis.debate.adjustment_validator")
_sys.modules[__name__] = _canonical
