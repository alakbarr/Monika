"""Shim module: monika.application.analysis.tools.domain.position_handlers."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.domain.position_handlers import *

_canonical = _importlib.import_module("monika.application.analysis.tools.domain.position_handlers")
_sys.modules[__name__] = _canonical
