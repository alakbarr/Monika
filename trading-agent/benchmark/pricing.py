"""Shim module: monika.application.benchmark.pricing."""

import sys as _sys
import importlib as _importlib

from monika.application.benchmark.pricing import *

_canonical = _importlib.import_module("monika.application.benchmark.pricing")
_sys.modules[__name__] = _canonical
