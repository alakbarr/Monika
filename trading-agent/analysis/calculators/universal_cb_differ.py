"""Shim module: monika.application.analysis.calculators.universal_cb_differ."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.universal_cb_differ import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.universal_cb_differ")
_sys.modules[__name__] = _canonical
