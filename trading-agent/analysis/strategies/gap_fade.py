"""Shim module: monika.application.analysis.strategies.gap_fade."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.gap_fade import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.gap_fade")
_sys.modules[__name__] = _canonical
