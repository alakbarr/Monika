"""Shim module: monika.application.benchmark.prompt_evolution."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.prompt_evolution import *

_canonical = _importlib.import_module("monika.application.benchmark.prompt_evolution")
_sys.modules[__name__] = _canonical
