"""Shim module: monika.application.scheduler.position_supervisor."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.position_supervisor import *

_canonical = _importlib.import_module("monika.application.scheduler.position_supervisor")
_sys.modules[__name__] = _canonical
