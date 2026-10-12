"""Shim module: monika.application.evals.hostile_market_probe."""

import sys as _sys
import importlib as _importlib

from monika.application.evals.hostile_market_probe import *

_canonical = _importlib.import_module("monika.application.evals.hostile_market_probe")
_sys.modules[__name__] = _canonical
