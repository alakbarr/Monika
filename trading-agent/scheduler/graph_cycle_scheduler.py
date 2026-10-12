"""Shim module: monika.application.scheduler.graph_cycle_scheduler."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.graph_cycle_scheduler import *

_canonical = _importlib.import_module("monika.application.scheduler.graph_cycle_scheduler")
_sys.modules[__name__] = _canonical
