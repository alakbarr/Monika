"""Shim module: monika.application.analysis.calculators.evt_tail_calculator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.evt_tail_calculator import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.evt_tail_calculator")
_sys.modules[__name__] = _canonical
