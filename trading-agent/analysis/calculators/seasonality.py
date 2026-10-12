"""Shim module: monika.application.analysis.calculators.seasonality."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.seasonality import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.seasonality")
_sys.modules[__name__] = _canonical
