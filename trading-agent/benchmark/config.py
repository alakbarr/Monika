"""Shim module: monika.application.benchmark.config."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.config import *

_canonical = _importlib.import_module("monika.application.benchmark.config")
_sys.modules[__name__] = _canonical
