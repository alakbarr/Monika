"""Shim module: monika.application.analysis.strategies.tsm_momentum."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.tsm_momentum import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.tsm_momentum")
_sys.modules[__name__] = _canonical
