"""Shim module: monika.application.benchmark.runner."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.runner import *

_canonical = _importlib.import_module("monika.application.benchmark.runner")
_sys.modules[__name__] = _canonical
