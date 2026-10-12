"""Shim module: monika.application.skills.unified_runtime."""

import sys as _sys
import importlib as _importlib

from monika.application.skills.unified_runtime import *

_canonical = _importlib.import_module("monika.application.skills.unified_runtime")
_sys.modules[__name__] = _canonical
