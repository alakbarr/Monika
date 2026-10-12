"""Shim module: monika.application.analysis.tools.domain.code_execution_tool."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.domain.code_execution_tool import *

_canonical = _importlib.import_module("monika.application.analysis.tools.domain.code_execution_tool")
_sys.modules[__name__] = _canonical
