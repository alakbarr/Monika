"""Shim module: monika.application.plugins.loader."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.loader import *

_canonical = _importlib.import_module("monika.application.plugins.loader")
_sys.modules[__name__] = _canonical
