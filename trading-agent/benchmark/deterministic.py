"""Shim module: monika.application.benchmark.deterministic."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.deterministic import *

_canonical = _importlib.import_module("monika.application.benchmark.deterministic")
_sys.modules[__name__] = _canonical
