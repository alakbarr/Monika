"""Shim module: monika.application.analysis.strategies.xti_pairs_readiness."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.xti_pairs_readiness import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.xti_pairs_readiness")
_sys.modules[__name__] = _canonical
