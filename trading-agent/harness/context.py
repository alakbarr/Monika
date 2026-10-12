"""Shim module: monika.application.harness.context."""

import sys as _sys
import importlib as _importlib

from monika.application.harness.context import *

_canonical = _importlib.import_module("monika.application.harness.context")
_sys.modules[__name__] = _canonical
