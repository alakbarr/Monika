"""Shim module: monika.application.analysis.harness.trade_stop_gates."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.trade_stop_gates import *

_canonical = _importlib.import_module("monika.application.analysis.harness.trade_stop_gates")
_sys.modules[__name__] = _canonical
