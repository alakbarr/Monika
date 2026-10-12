"""Shim module: monika.application.analysis.calculators.taylor_rule."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.taylor_rule import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.taylor_rule")
_sys.modules[__name__] = _canonical
