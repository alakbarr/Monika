"""Shim module: monika.application.analysis.calculators.stage1_priced_in."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.stage1_priced_in import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.stage1_priced_in")
_sys.modules[__name__] = _canonical
