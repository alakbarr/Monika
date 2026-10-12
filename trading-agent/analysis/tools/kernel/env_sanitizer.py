"""Shim module: monika.application.analysis.tools.kernel.env_sanitizer."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.kernel.env_sanitizer import *

_canonical = _importlib.import_module("monika.application.analysis.tools.kernel.env_sanitizer")
_sys.modules[__name__] = _canonical
