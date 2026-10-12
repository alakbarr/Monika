"""Shim module: monika.application.benchmark.token_drift_tracker."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.token_drift_tracker import *

_canonical = _importlib.import_module("monika.application.benchmark.token_drift_tracker")
_sys.modules[__name__] = _canonical
