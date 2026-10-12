"""Shim module: monika.application.benchmark.invoker."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.invoker import *

_canonical = _importlib.import_module("monika.application.benchmark.invoker")
_sys.modules[__name__] = _canonical
