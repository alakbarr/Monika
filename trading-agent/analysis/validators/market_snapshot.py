"""Shim module: monika.application.analysis.validators.market_snapshot."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.validators.market_snapshot import *

_canonical = _importlib.import_module("monika.application.analysis.validators.market_snapshot")
_sys.modules[__name__] = _canonical
