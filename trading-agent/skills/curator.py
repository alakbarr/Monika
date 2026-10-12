"""Shim module: monika.application.skills.curator."""

import sys as _sys
import importlib as _importlib

from monika.application.skills.curator import *

_canonical = _importlib.import_module("monika.application.skills.curator")
_sys.modules[__name__] = _canonical
