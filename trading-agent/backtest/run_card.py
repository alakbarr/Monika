"""Shim module: monika.application.backtest.run_card."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.run_card import *

_canonical = _importlib.import_module("monika.application.backtest.run_card")
_sys.modules[__name__] = _canonical
