"""Shim module: monika.application.backtest.decision_memory."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.decision_memory import *

_canonical = _importlib.import_module("monika.application.backtest.decision_memory")
_sys.modules[__name__] = _canonical
