"""Shim module: monika.application.benchmark.trade_trajectory_logger."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.trade_trajectory_logger import *

_canonical = _importlib.import_module("monika.application.benchmark.trade_trajectory_logger")
_sys.modules[__name__] = _canonical
