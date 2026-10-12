"""Shim module: monika.application.analysis.calculators.leading_indicator_mapper."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.leading_indicator_mapper import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.leading_indicator_mapper")
_sys.modules[__name__] = _canonical
