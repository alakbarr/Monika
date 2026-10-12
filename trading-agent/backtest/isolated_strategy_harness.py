"""Shim module: monika.application.backtest.isolated_strategy_harness."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.isolated_strategy_harness import *

_canonical = _importlib.import_module("monika.application.backtest.isolated_strategy_harness")
_sys.modules[__name__] = _canonical
