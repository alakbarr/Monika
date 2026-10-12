"""Shim module: monika.application.analysis.strategies.smc_fvg."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.smc_fvg import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.smc_fvg")
_sys.modules[__name__] = _canonical
