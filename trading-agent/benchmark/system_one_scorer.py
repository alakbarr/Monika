"""Shim module: monika.application.benchmark.system_one_scorer."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.system_one_scorer import *

_canonical = _importlib.import_module("monika.application.benchmark.system_one_scorer")
_sys.modules[__name__] = _canonical
