"""Shim module: monika.application.analysis.harness.message_repair."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.harness.message_repair import *

_canonical = _importlib.import_module("monika.application.analysis.harness.message_repair")
_sys.modules[__name__] = _canonical
