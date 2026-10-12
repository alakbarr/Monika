"""Shim module: monika.application.harness.engine."""

import sys as _sys
import importlib as _importlib

from monika.application.harness.engine import *

_canonical = _importlib.import_module("monika.application.harness.engine")
_sys.modules[__name__] = _canonical
