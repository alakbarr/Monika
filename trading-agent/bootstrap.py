"""Shim module: monika.application.bootstrap."""

import sys as _sys
import importlib as _importlib

from monika.application.bootstrap import *

_canonical = _importlib.import_module("monika.application.bootstrap")
_sys.modules[__name__] = _canonical
