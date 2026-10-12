"""Shim module: monika.application.analysis.calculators.factor_ic."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.factor_ic import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.factor_ic")
_sys.modules[__name__] = _canonical
