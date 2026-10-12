"""Shim module: monika.application.backtest.report_generator."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.report_generator import *

_canonical = _importlib.import_module("monika.application.backtest.report_generator")
_sys.modules[__name__] = _canonical
