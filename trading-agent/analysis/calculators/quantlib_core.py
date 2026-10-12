"""Shim module: monika.application.analysis.calculators.quantlib_core."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.quantlib_core import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.quantlib_core")
_sys.modules[__name__] = _canonical
