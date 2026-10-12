"""Shim module: monika.application.analysis.tools.tool_catalog."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.tool_catalog import *

_canonical = _importlib.import_module("monika.application.analysis.tools.tool_catalog")
_sys.modules[__name__] = _canonical
