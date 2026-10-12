"""Shim module: monika.application.analysis.strategies.registry."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.registry import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.registry")
_sys.modules[__name__] = _canonical
