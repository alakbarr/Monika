"""Shim module: monika.application.analysis.tools.core.decorator."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.core.decorator import *

_canonical = _importlib.import_module("monika.application.analysis.tools.core.decorator")
_sys.modules[__name__] = _canonical
