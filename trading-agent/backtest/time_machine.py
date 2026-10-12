"""Shim module: monika.application.backtest.time_machine."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.time_machine import *

_canonical = _importlib.import_module("monika.application.backtest.time_machine")
_sys.modules[__name__] = _canonical
