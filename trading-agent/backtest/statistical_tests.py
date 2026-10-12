"""Shim module: monika.application.backtest.statistical_tests."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.statistical_tests import *

_canonical = _importlib.import_module("monika.application.backtest.statistical_tests")
_sys.modules[__name__] = _canonical
