"""Shim module: monika.application.harness.lifecycle."""

import sys as _sys
import importlib as _importlib

from monika.application.harness.lifecycle import *

_canonical = _importlib.import_module("monika.application.harness.lifecycle")
_sys.modules[__name__] = _canonical
