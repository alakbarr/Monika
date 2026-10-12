"""Shim module: monika.application.scheduler.position_exit_reviewer."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.position_exit_reviewer import *

_canonical = _importlib.import_module("monika.application.scheduler.position_exit_reviewer")
_sys.modules[__name__] = _canonical
