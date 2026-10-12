"""Shim module: monika.application.harness.contract."""

import sys as _sys
import importlib as _importlib

from monika.application.harness.contract import *

_canonical = _importlib.import_module("monika.application.harness.contract")
_sys.modules[__name__] = _canonical
