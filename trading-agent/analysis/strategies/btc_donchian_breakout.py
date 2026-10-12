"""Shim module: monika.application.analysis.strategies.btc_donchian_breakout."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.btc_donchian_breakout import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.btc_donchian_breakout")
_sys.modules[__name__] = _canonical
