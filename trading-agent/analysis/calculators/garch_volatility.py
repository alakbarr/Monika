"""Shim module: monika.application.analysis.calculators.garch_volatility."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.garch_volatility import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.garch_volatility")
_sys.modules[__name__] = _canonical
