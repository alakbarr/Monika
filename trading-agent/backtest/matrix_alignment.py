"""Shim module: monika.application.backtest.matrix_alignment."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.matrix_alignment import *

_canonical = _importlib.import_module("monika.application.backtest.matrix_alignment")
_sys.modules[__name__] = _canonical
