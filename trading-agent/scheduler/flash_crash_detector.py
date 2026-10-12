"""Shim module: monika.application.scheduler.flash_crash_detector."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.flash_crash_detector import *

_canonical = _importlib.import_module("monika.application.scheduler.flash_crash_detector")
_sys.modules[__name__] = _canonical
