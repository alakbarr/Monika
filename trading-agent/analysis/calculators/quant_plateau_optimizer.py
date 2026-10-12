"""Shim module: monika.application.analysis.calculators.quant_plateau_optimizer."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.quant_plateau_optimizer import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.quant_plateau_optimizer")
_sys.modules[__name__] = _canonical
