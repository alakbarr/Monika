"""Shim module: monika.application.scheduler.trigger_checker."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.trigger_checker import *

_canonical = _importlib.import_module("monika.application.scheduler.trigger_checker")
_sys.modules[__name__] = _canonical
