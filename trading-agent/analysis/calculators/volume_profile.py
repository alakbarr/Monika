"""Shim module: monika.application.analysis.calculators.volume_profile."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.volume_profile import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.volume_profile")
_sys.modules[__name__] = _canonical
