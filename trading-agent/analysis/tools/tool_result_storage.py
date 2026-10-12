"""Shim module: monika.application.analysis.tools.tool_result_storage."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.tool_result_storage import *

_canonical = _importlib.import_module("monika.application.analysis.tools.tool_result_storage")
_sys.modules[__name__] = _canonical
