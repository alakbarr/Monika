"""Shim module: monika.application.analysis.calculators.cointegration."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.cointegration import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.cointegration")
_sys.modules[__name__] = _canonical
