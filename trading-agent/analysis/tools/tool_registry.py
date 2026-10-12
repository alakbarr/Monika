"""Shim module: monika.application.analysis.tools.tool_registry."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.tool_registry import *

_canonical = _importlib.import_module("monika.application.analysis.tools.tool_registry")
_sys.modules[__name__] = _canonical
