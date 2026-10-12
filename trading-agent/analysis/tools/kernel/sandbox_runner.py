"""Shim module: monika.application.analysis.tools.kernel.sandbox_runner."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.kernel.sandbox_runner import *

_canonical = _importlib.import_module("monika.application.analysis.tools.kernel.sandbox_runner")
_sys.modules[__name__] = _canonical
