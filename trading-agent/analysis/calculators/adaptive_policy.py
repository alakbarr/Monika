"""Shim module: monika.application.analysis.calculators.adaptive_policy."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.adaptive_policy import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.adaptive_policy")
_sys.modules[__name__] = _canonical
