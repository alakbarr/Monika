"""Shim module: monika.application.analysis.calculators.hmm_regime."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.hmm_regime import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.hmm_regime")
_sys.modules[__name__] = _canonical
