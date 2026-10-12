"""Shim module: monika.application.backtest.engines.crypto_engine."""

import sys as _sys
import importlib as _importlib

from monika.application.backtest.engines.crypto_engine import *

_canonical = _importlib.import_module("monika.application.backtest.engines.crypto_engine")
_sys.modules[__name__] = _canonical
