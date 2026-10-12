"""Shim module: monika.application.benchmark.report."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.report import *

_canonical = _importlib.import_module("monika.application.benchmark.report")
_sys.modules[__name__] = _canonical
