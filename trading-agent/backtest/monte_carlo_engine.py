"""Shim module: monika.application.backtest.monte_carlo_engine."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.monte_carlo_engine import *

_canonical = _importlib.import_module("monika.application.backtest.monte_carlo_engine")
_sys.modules[__name__] = _canonical
