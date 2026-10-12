"""Shim module: monika.application.analysis.calculators.copula_tail_risk."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.copula_tail_risk import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.copula_tail_risk")
_sys.modules[__name__] = _canonical
