"""Shim module: monika.application.benchmark.judge."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.judge import *

_canonical = _importlib.import_module("monika.application.benchmark.judge")
_sys.modules[__name__] = _canonical
