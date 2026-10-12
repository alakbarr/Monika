"""Shim module: monika.application.analysis.calculators.macro_bias_filter."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.macro_bias_filter import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.macro_bias_filter")
_sys.modules[__name__] = _canonical
