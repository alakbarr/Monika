"""Shim module: monika.application.benchmark.alpha_arena."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.alpha_arena import *

_canonical = _importlib.import_module("monika.application.benchmark.alpha_arena")
_sys.modules[__name__] = _canonical
