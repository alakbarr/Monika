"""Shim module: monika.application.analysis.strategies.pretrade_gate."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.pretrade_gate import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.pretrade_gate")
_sys.modules[__name__] = _canonical
