"""Shim module: monika.application.analysis.tools.domain.computer_use_tool."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.domain.computer_use_tool import *

_canonical = _importlib.import_module("monika.application.analysis.tools.domain.computer_use_tool")
_sys.modules[__name__] = _canonical
