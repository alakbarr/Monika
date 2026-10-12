"""Shim module: monika.application.analysis.tools.core.definition."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.core.definition import *

_canonical = _importlib.import_module("monika.application.analysis.tools.core.definition")
_sys.modules[__name__] = _canonical
