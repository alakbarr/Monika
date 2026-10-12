"""Shim module: monika.application.analysis.tools.kernel.code_execution_rpc."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.kernel.code_execution_rpc import *

_canonical = _importlib.import_module("monika.application.analysis.tools.kernel.code_execution_rpc")
_sys.modules[__name__] = _canonical
