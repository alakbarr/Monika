"""Shim module: monika.application.benchmark.model_registry."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.model_registry import *

_canonical = _importlib.import_module("monika.application.benchmark.model_registry")
_sys.modules[__name__] = _canonical
