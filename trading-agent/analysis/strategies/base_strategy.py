"""Shim module: monika.application.analysis.strategies.base_strategy."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.base_strategy import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.base_strategy")
_sys.modules[__name__] = _canonical
