"""Shim module: monika.application.backtest.alpha_validation."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.alpha_validation import *

_canonical = _importlib.import_module("monika.application.backtest.alpha_validation")
_sys.modules[__name__] = _canonical
