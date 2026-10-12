"""Shim package: monika.application.plugins.kernel."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.kernel import *

_canonical = _importlib.import_module("monika.application.plugins.kernel")
_sys.modules[__name__] = _canonical
