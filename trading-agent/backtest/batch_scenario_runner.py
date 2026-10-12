"""Shim module: monika.application.backtest.batch_scenario_runner."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.batch_scenario_runner import *

_canonical = _importlib.import_module("monika.application.backtest.batch_scenario_runner")
_sys.modules[__name__] = _canonical
