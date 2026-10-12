"""Shim module: monika.application.analysis.calculators.universal_macro_analyzer."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.universal_macro_analyzer import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.universal_macro_analyzer")
_sys.modules[__name__] = _canonical
