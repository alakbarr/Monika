"""Shim module: monika.application.analysis.calculators.economic_surprise."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.economic_surprise import *
from monika.application.analysis.calculators.economic_surprise import _parse_numeric

_canonical = _importlib.import_module("monika.application.analysis.calculators.economic_surprise")
_sys.modules[__name__] = _canonical
