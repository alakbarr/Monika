"""Shim module: monika.application.analysis.strategies.xau_trend_engine."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.xau_trend_engine import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.xau_trend_engine")
_sys.modules[__name__] = _canonical
