"""Shim module: monika.application.scheduler.trailing_stop_manager."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.trailing_stop_manager import *

_canonical = _importlib.import_module("monika.application.scheduler.trailing_stop_manager")
_sys.modules[__name__] = _canonical
