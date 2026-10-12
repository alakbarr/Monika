"""Shim module: monika.application.harness.adapters.functional_adapter."""

import sys as _sys
import importlib as _importlib

from monika.application.harness.adapters.functional_adapter import *

_canonical = _importlib.import_module("monika.application.harness.adapters.functional_adapter")
_sys.modules[__name__] = _canonical
