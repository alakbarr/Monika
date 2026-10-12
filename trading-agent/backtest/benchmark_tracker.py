"""Shim module: monika.application.backtest.benchmark_tracker."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.benchmark_tracker import *

_canonical = _importlib.import_module("monika.application.backtest.benchmark_tracker")
_sys.modules[__name__] = _canonical
