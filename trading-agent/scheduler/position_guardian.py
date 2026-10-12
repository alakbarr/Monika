"""Shim module: monika.application.scheduler.position_guardian."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.position_guardian import *

_canonical = _importlib.import_module("monika.application.scheduler.position_guardian")
_sys.modules[__name__] = _canonical
