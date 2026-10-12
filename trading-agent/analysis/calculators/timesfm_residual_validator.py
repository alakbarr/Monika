"""Shim module: monika.application.analysis.calculators.timesfm_residual_validator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.timesfm_residual_validator import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.timesfm_residual_validator")
_sys.modules[__name__] = _canonical
