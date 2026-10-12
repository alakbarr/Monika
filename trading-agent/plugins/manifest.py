"""Shim module: monika.application.plugins.manifest."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.manifest import *

_canonical = _importlib.import_module("monika.application.plugins.manifest")
_sys.modules[__name__] = _canonical
