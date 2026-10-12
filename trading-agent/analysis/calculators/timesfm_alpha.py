"""Shim module: monika.application.analysis.calculators.timesfm_alpha."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.timesfm_alpha import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.timesfm_alpha")
_sys.modules[__name__] = _canonical
